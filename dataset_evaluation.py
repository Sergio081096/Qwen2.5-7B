"""Métricas semánticas y validación CLIPS para el dataset GPSR."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from goal_schema import (
    ParsedGoal,
    entity_kinds,
    goal_signature,
    parse_goals,
    semantic_slots,
    validate_goals,
)


_JUSTINA_WS = Path(os.environ.get("JUSTINA_WS", Path.home() / "Justina"))
DEFAULT_CLIPS_RULES = _JUSTINA_WS / (
    "src/Planning/clips/clips_node/clips_rules/goals_planning.clp"
)


@dataclass(frozen=True)
class ClipsValidationResult:
    """Resultado independiente del binding de CLIPS y fácil de serializar."""

    planifiable: bool
    message_count: int = 0
    reason: str = ""


def _runtime_value(value: str) -> str:
    return value.strip().strip("\"'").replace(" ", "_")


def _q(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _goal_destination(goal: ParsedGoal) -> str:
    for key in ("to", "at", "on", "in"):
        if key in goal.kwargs:
            return _runtime_value(goal.kwargs[key])
    if goal.name == "deliver" and len(goal.args) > 1:
        return _runtime_value(goal.args[1])
    return ""


def _goal_relation(goal: ParsedGoal) -> tuple[str, str]:
    for key in ("to", "at", "on", "in", "gesture", "pose", "wearing", "property"):
        if key in goal.kwargs:
            return key, _runtime_value(goal.kwargs[key])
    if goal.name == "deliver" and len(goal.args) > 1:
        return "to", _runtime_value(goal.args[1])
    return "", ""


def _goal_qualifier(goal: ParsedGoal) -> str:
    for key in ("gesture", "pose", "wearing", "property"):
        if key in goal.kwargs:
            return f"{key}:{_runtime_value(goal.kwargs[key])}"
    return ""


def goal_to_clips_fact(step: int, goal: ParsedGoal) -> str:
    """Construye el mismo hecho gpsr-goal que consume goals_planning.clp."""
    relation, value = _goal_relation(goal)
    kind = goal.entity_kind or "unknown"
    return (
        "(gpsr-goal "
        f"(step {step}) "
        f"(name {goal.name}) "
        f"(target {_q(_runtime_value(goal.target))}) "
        f"(kind {kind}) "
        f"(destination {_q(_goal_destination(goal))}) "
        f"(relation {_q(relation)}) "
        f"(value {_q(value)}) "
        f"(qualifier {_q(_goal_qualifier(goal))}))"
    )


class ClipsPlanValidator:
    """Carga una vez las reglas y reinicia el entorno para cada secuencia."""

    def __init__(self, rules_path: str | Path = DEFAULT_CLIPS_RULES):
        try:
            import clips
        except ImportError as exc:  # pragma: no cover - depende del entorno.
            raise RuntimeError("clipspy is not installed") from exc

        self._clips = clips
        self.rules_path = Path(rules_path)
        if not self.rules_path.exists():
            raise FileNotFoundError(self.rules_path)
        self._environment = clips.Environment()
        self._environment.load(str(self.rules_path))

    def close(self) -> None:
        environment = getattr(self, "_environment", None)
        if environment is not None:
            environment.clear()
            self._environment = None

    def __del__(self):  # pragma: no cover - limpieza defensiva del binding C.
        try:
            self.close()
        except Exception:
            pass

    def validate(self, goals: Sequence[str]) -> ClipsValidationResult:
        """Reinicia CLIPS, inserta una secuencia y exige su terminación completa."""
        if self._environment is None:
            return ClipsValidationResult(False, reason="CLIPS validator is closed")
        issues = validate_goals(goals)
        if issues:
            return ClipsValidationResult(False, reason="; ".join(map(str, issues)))

        try:
            self._environment.reset()
            for step, goal in enumerate(parse_goals(goals), start=1):
                self._environment.assert_string(goal_to_clips_fact(step, goal))
            self._environment.assert_string("(start (name action-planning))")
            self._environment.run()
        except self._clips.CLIPSError as exc:
            return ClipsValidationResult(False, reason=str(exc))

        # No basta con que CLIPS ejecute sin excepción: también se comprueba que
        # haya consumido todos los goals y publicado el marcador GPSR_DONE.
        facts = list(self._environment.facts())
        pending = [fact for fact in facts if fact.template.name == "gpsr-goal"]
        messages = [fact for fact in facts if fact.template.name == "ros-message"]
        done = any(
            fact.template.name == "plan-note" and str(fact["state"]) == "GPSR_DONE"
            for fact in facts
        )
        unsupported = any(
            fact.template.name == "ros-message"
            and str(fact["action"]) == "say"
            and "I do not know how to execute goal" in " ".join(map(str, fact["params"]))
            for fact in facts
        )
        if pending:
            return ClipsValidationResult(False, len(messages), "pending gpsr-goal facts")
        if unsupported:
            return ClipsValidationResult(False, len(messages), "unsupported goal rule fired")
        if not done:
            return ClipsValidationResult(False, len(messages), "GPSR_DONE was not produced")
        return ClipsValidationResult(True, len(messages))


def _family(row) -> str:
    meta = row.get("meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    return str(row.get("family") or meta.get("family") or "unknown")


def evaluate_dataset_rows(
    rows: Iterable[dict],
    clips_validator: ClipsPlanValidator | None = None,
    max_clips_samples: int = 0,
) -> dict:
    """Mide la calidad de labels existentes, sin ejecutar ningún modelo."""
    totals = Counter()
    families = Counter()
    kinds = Counter()
    signatures = Counter()
    family_signatures = defaultdict(Counter)
    surface_templates = defaultdict(Counter)
    slots = Counter()
    issue_codes = Counter()
    clips_by_family = defaultdict(Counter)

    for row in rows:
        totals["rows"] += 1
        family = _family(row)
        families[family] += 1
        meta = row.get("meta") or {}
        if isinstance(meta, dict):
            surface_id = meta.get("surface_template_id")
            if surface_id:
                surface_templates[family][str(surface_id)] += 1
        goals = row.get("goals", [])
        issues = validate_goals(goals)
        if issues:
            totals["invalid"] += 1
            issue_codes.update(issue.code for issue in issues)
        else:
            totals["valid"] += 1
            kinds.update(entity_kinds(goals))
            signature = " -> ".join(goal_signature(goals))
            signatures.update((signature,))
            family_signatures[family][signature] += 1
            slots.update(semantic_slots(goals).keys())

        should_check_clips = clips_validator is not None and (
            max_clips_samples <= 0 or totals["clips_checked"] < max_clips_samples
        )
        if should_check_clips and not issues:
            result = clips_validator.validate(goals)
            totals["clips_checked"] += 1
            totals["clips_planifiable" if result.planifiable else "clips_failed"] += 1
            clips_by_family[family]["ok" if result.planifiable else "failed"] += 1

    return {
        "totals": dict(totals),
        "families": dict(families),
        "entity_kinds": dict(kinds),
        "goal_signatures": dict(signatures),
        "family_goal_signatures": {
            family: dict(counts) for family, counts in family_signatures.items()
        },
        "surface_templates": {
            family: dict(counts) for family, counts in surface_templates.items()
        },
        "slot_coverage": dict(slots),
        "issues": dict(issue_codes),
        "clips_by_family": {key: dict(value) for key, value in clips_by_family.items()},
    }


def evaluate_predictions(
    rows: Iterable[dict],
    predict: Callable[[str], dict],
    clips_validator: ClipsPlanValidator | None = None,
    max_samples: int = 50,
) -> dict:
    """Compara predicciones por familia, tipo, slots, esquema y CLIPS.

    Las métricas de slots usan una clave que incluye posición y nombre de la
    acción; así un destino correcto colocado en el goal equivocado no cuenta
    accidentalmente como acierto.
    """
    totals = Counter()
    family_scores = defaultdict(Counter)
    kind_scores = defaultdict(Counter)
    slot_scores = Counter()

    for row in rows:
        if max_samples > 0 and totals["samples"] >= max_samples:
            break
        totals["samples"] += 1
        family = _family(row)
        expected = row.get("goals")
        if expected is None and "response" in row:
            expected = json.loads(row["response"])["goals"]

        predicted_payload = predict(row["input"])
        predicted = (
            predicted_payload.get("goals", [])
            if isinstance(predicted_payload, dict)
            else []
        )
        exact = predicted == expected
        totals["exact"] += int(exact)
        family_scores[family]["total"] += 1
        family_scores[family]["exact"] += int(exact)

        predicted_issues = validate_goals(predicted)
        totals["schema_valid"] += int(not predicted_issues)
        if predicted_issues:
            totals["schema_invalid"] += 1
            continue

        expected_slots = semantic_slots(expected)
        predicted_slots = semantic_slots(predicted)
        for key, expected_value in expected_slots.items():
            slot_scores["expected"] += 1
            matched = predicted_slots.get(key) == expected_value
            slot_scores["correct"] += int(matched)
            if key.endswith(".kind"):
                kind_scores[expected_value]["total"] += 1
                kind_scores[expected_value]["correct"] += int(matched)
        slot_scores["predicted"] += len(predicted_slots)

        if clips_validator is not None:
            result = clips_validator.validate(predicted)
            totals["clips_checked"] += 1
            totals["clips_planifiable"] += int(result.planifiable)

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else 0.0

    total_values = dict(totals)
    total_values["exact_accuracy"] = ratio(totals["exact"], totals["samples"])
    total_values["schema_valid_rate"] = ratio(
        totals["schema_valid"], totals["samples"]
    )
    if totals["clips_checked"]:
        total_values["clips_planifiable_rate"] = ratio(
            totals["clips_planifiable"], totals["clips_checked"]
        )

    family_values = {}
    for key, value in family_scores.items():
        family_values[key] = {
            **dict(value),
            "accuracy": ratio(value["exact"], value["total"]),
        }

    kind_values = {}
    for key, value in kind_scores.items():
        kind_values[key] = {
            **dict(value),
            "accuracy": ratio(value["correct"], value["total"]),
        }

    slot_values = dict(slot_scores)
    slot_values["recall"] = ratio(slot_scores["correct"], slot_scores["expected"])
    slot_values["precision"] = ratio(slot_scores["correct"], slot_scores["predicted"])
    precision = slot_values["precision"]
    recall = slot_values["recall"]
    slot_values["f1"] = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    return {
        "totals": total_values,
        "families": family_values,
        "entity_kinds": kind_values,
        "slots": slot_values,
    }


def print_evaluation_report(report: dict, title: str = "Evaluación GPSR") -> None:
    print(f"\n{title}")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
