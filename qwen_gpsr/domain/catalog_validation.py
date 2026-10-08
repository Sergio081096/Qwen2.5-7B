"""Validación de catálogos GPSR locales y externos.

CompetitionTemplate sigue siendo la fuente usada para generar el dataset. La
comparación externa permite detectar deriva con el catálogo semántico de
Justina sin copiar silenciosamente listas entre repositorios.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml


_JUSTINA_WS = Path(os.environ.get("JUSTINA_WS", Path.home() / "Justina"))
DEFAULT_JUSTINA_NAMES = _JUSTINA_WS / (
    "src/Knowledge/knowledge_bank/dictionaries/names.yaml"
)


@dataclass(frozen=True)
class CatalogIssue:
    """Problema estructurado que el generador puede imprimir o tratar como fatal."""

    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code}: {self.message}"


def _normalized(value: str) -> str:
    """Crea una identidad comparable sin depender de guiones bajos o mayúsculas."""
    return " ".join(value.replace("_", " ").casefold().split())


def _duplicates(values: Iterable[str]) -> list[str]:
    counts = Counter(_normalized(value) for value in values)
    return sorted(value for value, count in counts.items() if count > 1)


def _normalized_set(values: Iterable[str]) -> set[str]:
    return {_normalized(value) for value in values if value.strip()}


def validate_local_catalog(knowledge) -> list[CatalogIssue]:
    """Valida presencia, duplicados y colisiones del CompetitionTemplate."""
    groups = {
        "names": list(knowledge.names),
        "objects": list(knowledge.objects),
        "object_categories": list(knowledge.object_categories_singular),
        "locations": list(knowledge.locations),
        "rooms": list(knowledge.rooms),
    }
    issues: list[CatalogIssue] = []

    for group, values in groups.items():
        if not values:
            issues.append(CatalogIssue("error", "empty_catalog", group))
        duplicates = _duplicates(values)
        if duplicates:
            issues.append(
                CatalogIssue(
                    "warning",
                    "duplicates",
                    f"{group}: {', '.join(duplicates)}",
                )
            )

    names = _normalized_set(groups["names"])
    object_entities = _normalized_set(groups["objects"] + groups["object_categories"])
    collisions = sorted(names & object_entities)
    if collisions:
        issues.append(
            CatalogIssue(
                "error",
                "person_object_collision",
                ", ".join(collisions),
            )
        )

    unusual_object_case = sorted(
        value for value in groups["objects"] if value != value.casefold()
    )
    if unusual_object_case:
        issues.append(
            CatalogIssue(
                "warning",
                "object_case",
                "objetos con mayúsculas que no deben usarse para inferir tipo: "
                + ", ".join(unusual_object_case),
            )
        )
    return issues


def load_yaml_patterns(path: str | Path) -> list[str]:
    """Lee el formato ``patterns`` usado por los diccionarios de Justina."""
    with Path(path).open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    patterns = data.get("patterns", [])
    if not isinstance(patterns, list):
        raise ValueError(f"patterns must be a list in {path}")
    return [str(value).strip() for value in patterns if str(value).strip()]


def compare_name_catalogs(
    local_names: Iterable[str],
    external_path: str | Path = DEFAULT_JUSTINA_NAMES,
) -> list[CatalogIssue]:
    """Reporta deriva con Justina sin reemplazar automáticamente ninguna lista."""
    path = Path(external_path)
    if not path.exists():
        return [
            CatalogIssue(
                "warning",
                "external_catalog_missing",
                str(path),
            )
        ]

    external_names = load_yaml_patterns(path)
    local = _normalized_set(local_names)
    external = _normalized_set(external_names)
    issues: list[CatalogIssue] = []

    duplicates = _duplicates(external_names)
    if duplicates:
        issues.append(
            CatalogIssue(
                "warning",
                "external_duplicates",
                f"{path}: {', '.join(duplicates)}",
            )
        )

    only_local = sorted(local - external)
    only_external = sorted(external - local)
    if only_local or only_external:
        details = []
        if only_local:
            details.append("solo CompetitionTemplate=" + ", ".join(only_local))
        if only_external:
            details.append("solo Justina=" + ", ".join(only_external))
        issues.append(
            CatalogIssue(
                "warning",
                "name_catalog_drift",
                "; ".join(details),
            )
        )
    return issues


def validate_catalogs(
    knowledge,
    external_names_path: str | Path = DEFAULT_JUSTINA_NAMES,
) -> list[CatalogIssue]:
    """Combina errores locales y advertencias de sincronización con Justina."""
    return [
        *validate_local_catalog(knowledge),
        *compare_name_catalogs(knowledge.names, external_names_path),
    ]


def print_catalog_report(issues: Iterable[CatalogIssue]) -> None:
    """Presenta el reporte antes de que comience la generación costosa."""
    issues = list(issues)
    if not issues:
        print("Catálogos: sin inconsistencias detectadas.")
        return
    print("Catálogos:")
    for issue in issues:
        print(f"  {issue}")
