import contextlib
import io
import unittest
from collections import Counter, defaultdict

from catalog_validation import validate_local_catalog
from command_constants import TEMPLATE_VARIANTS, validate_template_variants
from dataset_evaluation import ClipsPlanValidator
from generate_dataset import generate_balanced_dataset
from goal_schema import parse_goal, validate_goals
from gpsr_commands import CommandGenerator
from knowledge import parse_data


class GoalSchemaTests(unittest.TestCase):
    def test_explicit_kind_distinguishes_capitalized_object(self):
        goal = parse_goal("find(Water, kind=object)")
        self.assertEqual(goal.explicit_kind, "object")
        self.assertEqual(goal.target, "Water")
        self.assertEqual(validate_goals(["find(Water, kind=object)"]), [])

    def test_find_and_count_require_kind(self):
        find_issues = validate_goals(["find(Adel)"])
        count_issues = validate_goals(["count(person)"])
        self.assertIn("missing_kind", {issue.code for issue in find_issues})
        self.assertIn("missing_kind", {issue.code for issue in count_issues})

    def test_location_transport_uses_at_relation(self):
        goals = [
            "go(shelf)",
            "find(apple, kind=object)",
            "take(apple)",
            "place(apple, at=entrance)",
        ]
        self.assertEqual(validate_goals(goals), [])

    def test_redundant_navigation_is_rejected(self):
        issues = validate_goals(
            [
                "go(entrance)",
                "find(Anna, kind=person)",
                "go(entrance)",
                "find(Anna, kind=person)",
            ]
        )
        self.assertIn("redundant_navigation", {issue.code for issue in issues})


class DatasetGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.knowledge = parse_data("./CompetitionTemplate")
        generator = CommandGenerator(cls.knowledge, debug=False)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.rows = generate_balanced_dataset(generator, 500, 0.5, seed=42)

    def test_cardinality_and_deduplication(self):
        self.assertEqual(len(self.rows), 500)
        unique_inputs = {" ".join(row["input"].casefold().split()) for row in self.rows}
        self.assertEqual(len(unique_inputs), len(self.rows))
        self.assertEqual(
            Counter(row["meta"]["category"] for row in self.rows),
            {"people": 250, "objects": 250},
        )

    def test_all_rows_have_valid_labels_and_metadata(self):
        for row in self.rows:
            self.assertEqual(validate_goals(row["goals"]), [])
            self.assertIn("family", row["meta"])
            self.assertIn("category", row["meta"])
            self.assertIn("surface_template_id", row["meta"])
            self.assertIn("goal_signature", row["meta"])
            self.assertIn("entity_kinds", row["meta"])
            self.assertIn("slot_names", row["meta"])

    def test_every_family_has_three_to_five_surface_templates(self):
        self.assertTrue(TEMPLATE_VARIANTS)
        for family, variants in TEMPLATE_VARIANTS.items():
            self.assertGreaterEqual(len(variants), 3, family)
            self.assertLessEqual(len(variants), 5, family)
            self.assertEqual(len(variants), len(set(variants)), family)
        self.assertEqual(validate_template_variants(), [])

    def test_new_simple_and_compound_signatures_are_present(self):
        expected = {
            "findNameInRoom": ("go", "find"),
            "findObjectInRoomSimple": ("go", "find"),
            "greetNameInRoomSimple": ("go", "find", "greet"),
        }
        for family, signature in expected.items():
            rows = [row for row in self.rows if row["meta"]["family"] == family]
            self.assertTrue(rows, family)
            self.assertTrue(
                all(tuple(row["meta"]["goal_signature"]) == signature for row in rows),
                family,
            )

    def test_signatures_are_balanced_inside_each_family(self):
        counts = defaultdict(Counter)
        for row in self.rows:
            key = (row["meta"]["category"], row["meta"]["family"])
            counts[key][tuple(row["meta"]["goal_signature"])] += 1
        for key, signature_counts in counts.items():
            if len(signature_counts) > 1:
                self.assertLessEqual(
                    max(signature_counts.values()) - min(signature_counts.values()),
                    1,
                    key,
                )

    def test_generated_plans_do_not_repeat_the_same_navigation(self):
        for row in self.rows:
            goals = row["goals"]
            half = len(goals) // 2
            self.assertFalse(
                len(goals) % 2 == 0 and goals[:half] == goals[half:],
                row["input"],
            )

    def test_take_object_in_room_is_only_an_object_family(self):
        categories = {
            row["meta"]["category"]
            for row in self.rows
            if row["meta"]["family"] == "takeObjInRoom"
        }
        self.assertEqual(categories, {"objects"})

    def test_corrected_goal_sequences(self):
        tell_rows = [
            row for row in self.rows if row["meta"]["family"] == "tellPrsInfoInLoc"
        ]
        bring_rows = [
            row for row in self.rows if row["meta"]["family"] == "bringObjFromTo"
        ]
        self.assertTrue(tell_rows)
        self.assertTrue(bring_rows)
        for row in tell_rows:
            self.assertTrue(any(goal.startswith("save(") for goal in row["goals"]))
            self.assertIn("go(instruction_point)", row["goals"])
        for row in bring_rows:
            self.assertTrue(
                any(goal.startswith("place(") and ", at=" in goal for goal in row["goals"])
            )

    def test_catalog_validator_exposes_current_source_issues(self):
        codes = {issue.code for issue in validate_local_catalog(self.knowledge)}
        self.assertIn("duplicates", codes)
        self.assertIn("object_case", codes)

    def test_representative_rows_are_planifiable_in_clips(self):
        try:
            validator = ClipsPlanValidator()
        except (FileNotFoundError, RuntimeError) as exc:
            self.skipTest(str(exc))
        try:
            families_seen = set()
            for row in self.rows:
                family = row["meta"]["family"]
                if family in families_seen:
                    continue
                families_seen.add(family)
                result = validator.validate(row["goals"])
                self.assertTrue(result.planifiable, f"{family}: {result.reason}")
        finally:
            validator.close()


if __name__ == "__main__":
    unittest.main()
