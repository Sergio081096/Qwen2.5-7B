import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from command_constants import TEMPLATE_VARIANTS
from evaluate_model import (
    DEFAULT_BENCHMARK,
    case_details,
    create_evaluation_artifacts,
    evaluate_cached_predictions,
    load_benchmark,
)


class ModelBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_benchmark(DEFAULT_BENCHMARK)

    def test_benchmark_covers_every_generated_family(self):
        benchmark_families = {row["meta"]["family"] for row in self.rows}
        self.assertTrue(set(TEMPLATE_VARIANTS).issubset(benchmark_families))

    def test_perfect_cached_predictions_score_one(self):
        results = [
            {
                "normalized_input": row["input"],
                "prediction": {"goals": list(row["goals"])},
            }
            for row in self.rows
        ]
        report = evaluate_cached_predictions(self.rows, results)
        self.assertEqual(report["totals"]["exact"], len(self.rows))
        self.assertEqual(report["totals"]["exact_accuracy"], 1.0)
        self.assertEqual(report["totals"]["casefold_exact_accuracy"], 1.0)
        self.assertEqual(report["slots"]["f1"], 1.0)
        self.assertEqual(report["casefold_slots"]["f1"], 1.0)

    def test_case_only_difference_is_semantically_accepted(self):
        row = next(row for row in self.rows if row["id"] == "kind_object_01")
        result = {
            "normalized_input": "find water in the kitchen",
            "prediction": {
                "goals": ["go(kitchen)", "find(water, kind=object)"]
            },
        }
        report = evaluate_cached_predictions([row], [result])
        details = case_details([row], [result])
        self.assertEqual(report["totals"]["exact"], 0)
        self.assertEqual(report["totals"]["casefold_exact"], 1)
        self.assertEqual(report["totals"]["case_only_differences"], 1)
        self.assertTrue(details[0]["case_only_difference"])

    def test_details_expose_repeated_goal_regression(self):
        row = next(row for row in self.rows if row["id"] == "find_person_01")
        repeated = {"goals": row["goals"] + row["goals"]}
        details = case_details(
            [row],
            [{"normalized_input": row["input"], "prediction": repeated}],
        )
        self.assertFalse(details[0]["exact"])
        self.assertEqual(details[0]["predicted"], repeated["goals"])

    def test_default_benchmark_is_next_to_script(self):
        self.assertTrue(Path(DEFAULT_BENCHMARK).is_file())

    def test_evaluation_artifacts_are_created_from_cached_results(self):
        rows = self.rows[:3]
        results = [
            {
                "normalized_input": row["input"],
                "prediction": {"goals": list(row["goals"])},
                "_elapsed_ms": 1000.0 + index * 100.0,
            }
            for index, row in enumerate(rows)
        ]
        report = evaluate_cached_predictions(rows, results)
        details = case_details(rows, results)

        with TemporaryDirectory() as tmpdir:
            artifacts = create_evaluation_artifacts(report, details, tmpdir)
            self.assertEqual(len(artifacts), 4)
            self.assertTrue(all(path.is_file() for path in artifacts))
            self.assertEqual(
                {path.name for path in artifacts},
                {
                    "metrics_overview.png",
                    "family_accuracy.png",
                    "outcomes_and_latency.png",
                    "case_results.csv",
                },
            )


if __name__ == "__main__":
    unittest.main()
