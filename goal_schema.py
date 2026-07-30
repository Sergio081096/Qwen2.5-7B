"""Contrato canónico y validación de goals GPSR.

El dataset conserva goals como strings para mantener compatibilidad con el
modelo y con Justina. ``find`` y ``count`` deben declarar ``kind`` porque su
primer argumento puede representar una persona o un objeto.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


ENTITY_KINDS = frozenset({"person", "object"})
PERSON_QUALIFIERS = ("gesture", "pose", "wearing")
OBJECT_QUALIFIERS = ("property",)
QUALIFIERS = PERSON_QUALIFIERS + OBJECT_QUALIFIERS

SUPPORTED_GOALS = frozenset(
    {
        "go",
        "find",
        "take",
        "deliver",
        "place",
        "drop",
        "guide",
        "follow",
        "count",
        "tell",
        "talk",
        "save",
        "answer_question",
        "greet",
    }
)

_GOAL_RE = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)\s*$")
# Lista cerrada de slots aceptados por el contrato de entrenamiento y CLIPS.
# Rechazar slots desconocidos evita que el modelo aprenda etiquetas que el
# consumidor terminaría ignorando silenciosamente.
_ALLOWED_KWARGS = {
    "go": frozenset(),
    "find": frozenset({"kind", *QUALIFIERS}),
    "take": frozenset(),
    "deliver": frozenset({"to"}),
    "place": frozenset({"at", "in", "on", "to"}),
    "drop": frozenset({"at", "in", "on"}),
    "guide": frozenset({"to"}),
    "follow": frozenset({"to"}),
    "count": frozenset({"kind", *QUALIFIERS}),
    "tell": frozenset(QUALIFIERS),
    "talk": frozenset(),
    "save": frozenset(),
    "answer_question": frozenset(),
    "greet": frozenset(),
}


@dataclass(frozen=True)
class ParsedGoal:
    name: str
    args: tuple[str, ...]
    kwargs: Mapping[str, str]

    @property
    def target(self) -> str:
        return self.args[0] if self.args else ""

    @property
    def explicit_kind(self) -> str:
        return self.kwargs.get("kind", "")

    @property
    def entity_kind(self) -> str:
        if self.explicit_kind:
            return self.explicit_kind
        if self.name in {"take", "deliver", "place", "drop"}:
            return "object"
        if self.name in {"guide", "follow", "greet"}:
            return "person"
        return ""


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    goal_index: int | None = None

    def __str__(self) -> str:
        prefix = f"goal {self.goal_index}: " if self.goal_index is not None else ""
        return f"{prefix}{self.code}: {self.message}"


def _clean(value: str) -> str:
    return value.strip().strip("\"'")


def _split_top_level(body: str) -> list[str]:
    lexer = shlex.shlex(body, posix=True)
    lexer.whitespace = ","
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [token.strip() for token in lexer if token.strip()]


def parse_goal(raw_goal: str) -> ParsedGoal:
    match = _GOAL_RE.match(raw_goal)
    if not match:
        raise ValueError(f"invalid goal syntax: {raw_goal}")

    name = match.group(1).lower()
    args: list[str] = []
    kwargs: dict[str, str] = {}
    for token in _split_top_level(match.group(2)):
        if "=" in token:
            key, value = token.split("=", 1)
            key = _clean(key).lower()
            if not key:
                raise ValueError(f"empty slot name in goal: {raw_goal}")
            if key in kwargs:
                raise ValueError(f"duplicate slot {key!r} in goal: {raw_goal}")
            kwargs[key] = _clean(value)
        else:
            args.append(_clean(token))
    return ParsedGoal(name=name, args=tuple(args), kwargs=kwargs)


def parse_goals(goals: Iterable[str]) -> list[ParsedGoal]:
    return [parse_goal(goal) for goal in goals]


def validate_goals(goals: Sequence[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not goals:
        return [ValidationIssue("empty_goals", "the goal list is empty")]

    parsed: list[ParsedGoal] = []
    for index, raw_goal in enumerate(goals, start=1):
        if not isinstance(raw_goal, str) or not raw_goal.strip():
            issues.append(
                ValidationIssue("invalid_goal", "goal must be a non-empty string", index)
            )
            continue
        try:
            goal = parse_goal(raw_goal)
        except ValueError as exc:
            issues.append(ValidationIssue("invalid_syntax", str(exc), index))
            continue
        parsed.append(goal)
        issues.extend(_validate_parsed_goal(goal, index))

    issues.extend(_validate_sequence(parsed))
    return issues


def _validate_parsed_goal(goal: ParsedGoal, index: int) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if goal.name not in SUPPORTED_GOALS:
        return [ValidationIssue("unsupported_goal", goal.name, index)]

    allowed = _ALLOWED_KWARGS[goal.name]
    unexpected = sorted(set(goal.kwargs) - allowed)
    if unexpected:
        issues.append(
            ValidationIssue("unsupported_slots", ", ".join(unexpected), index)
        )

    requires_target = goal.name != "answer_question"
    if requires_target and not goal.target:
        issues.append(ValidationIssue("missing_target", goal.name, index))
    if goal.name == "answer_question" and (goal.args or goal.kwargs):
        issues.append(ValidationIssue("unexpected_arguments", goal.name, index))

    if goal.name in {"find", "count"}:
        kind = goal.explicit_kind
        if not kind:
            issues.append(ValidationIssue("missing_kind", goal.name, index))
        elif kind not in ENTITY_KINDS:
            issues.append(ValidationIssue("invalid_kind", kind, index))

        if kind == "person" and any(key in goal.kwargs for key in OBJECT_QUALIFIERS):
            issues.append(ValidationIssue("person_object_qualifier", goal.target, index))
        if kind == "object" and any(key in goal.kwargs for key in PERSON_QUALIFIERS):
            issues.append(ValidationIssue("object_person_qualifier", goal.target, index))

    if goal.name == "deliver" and len(goal.args) < 2 and "to" not in goal.kwargs:
        issues.append(ValidationIssue("missing_destination", goal.name, index))
    if goal.name in {"place", "drop"} and not any(
        key in goal.kwargs for key in ("at", "in", "on", "to")
    ):
        issues.append(ValidationIssue("missing_destination", goal.name, index))
    if goal.name == "guide" and "to" not in goal.kwargs:
        issues.append(ValidationIssue("missing_destination", goal.name, index))
    return issues


def _validate_sequence(goals: Sequence[ParsedGoal]) -> list[ValidationIssue]:
    """Comprueba coherencia entre tipos y dependencias temporales del plan."""
    issues: list[ValidationIssue] = []
    held_objects: set[str] = set()
    known_kinds: dict[str, str] = {}
    current_location = ""
    for index, goal in enumerate(goals, start=1):
        target = goal.target.casefold()

        if goal.name == "go":
            if target and target == current_location:
                issues.append(
                    ValidationIssue(
                        "redundant_navigation",
                        f"the robot is already at {goal.target}",
                        index,
                    )
                )
            current_location = target

        # follow/guide/place hacia la ubicación actual carece de efecto útil.
        # Se valida sobre los goals y no sobre las palabras de la plantilla.
        destination = ""
        if goal.name in {"follow", "guide"}:
            destination = goal.kwargs.get("to", "").casefold()
        elif goal.name in {"place", "drop"}:
            destination = next(
                (
                    goal.kwargs[key].casefold()
                    for key in ("at", "in", "on", "to")
                    if key in goal.kwargs
                ),
                "",
            )
        if destination and current_location and destination == current_location:
            issues.append(
                ValidationIssue(
                    "redundant_destination",
                    f"{goal.name} destination equals current location {destination}",
                    index,
                )
            )

        # Una entidad no puede cambiar de person a object dentro del mismo plan.
        if goal.name == "find" and target and goal.explicit_kind:
            previous = known_kinds.get(target)
            if previous and previous != goal.explicit_kind:
                issues.append(
                    ValidationIssue(
                        "kind_conflict",
                        f"{goal.target} was labeled as {previous} and {goal.explicit_kind}",
                        index,
                    )
                )
            known_kinds[target] = goal.explicit_kind

        required_kind = ""
        if goal.name in {"take", "deliver", "place", "drop"}:
            required_kind = "object"
        elif goal.name in {"guide", "follow", "greet"}:
            required_kind = "person"
        if target and required_kind and known_kinds.get(target) not in {None, required_kind}:
            issues.append(
                ValidationIssue(
                    "kind_action_conflict",
                    f"{goal.name} requires {required_kind}, but {goal.target} is "
                    f"{known_kinds[target]}",
                    index,
                )
            )

        # Las acciones de entrega/colocación requieren que el objeto haya sido
        # tomado antes. Esto detecta labels sintácticamente válidos pero inútiles.
        if goal.name == "take" and goal.target:
            held_objects.add(target)
        elif goal.name in {"deliver", "place", "drop"} and goal.target:
            if target not in held_objects:
                issues.append(
                    ValidationIssue(
                        "object_not_taken",
                        f"{goal.name}({goal.target}) has no preceding take",
                        index,
                    )
                )
            held_objects.discard(target)
    return issues


def goal_signature(goals: Sequence[str]) -> list[str]:
    return [parse_goal(goal).name for goal in goals]


def entity_kinds(goals: Sequence[str]) -> list[str]:
    return sorted({goal.entity_kind for goal in parse_goals(goals) if goal.entity_kind})


def slot_names(goals: Sequence[str]) -> list[str]:
    slots = {"target"}
    for goal in parse_goals(goals):
        slots.update(goal.kwargs)
        if len(goal.args) > 1:
            slots.add("destination")
    return sorted(slots)


def semantic_slots(goals: Sequence[str]) -> dict[str, str]:
    """Aplana una secuencia para comparar targets, tipos y slots por posición."""
    flattened: dict[str, str] = {}
    for index, goal in enumerate(parse_goals(goals), start=1):
        prefix = f"{index}.{goal.name}"
        flattened[f"{prefix}.target"] = goal.target
        for key, value in sorted(goal.kwargs.items()):
            flattened[f"{prefix}.{key}"] = value
        for arg_index, value in enumerate(goal.args[1:], start=2):
            flattened[f"{prefix}.arg{arg_index}"] = value
    return flattened
