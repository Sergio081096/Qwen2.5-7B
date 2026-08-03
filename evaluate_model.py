#!/usr/bin/env python3
"""Evalúa un adaptador Qwen GPSR sobre un benchmark etiquetado y reproducible."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path

# Matplotlib necesita un directorio escribible incluso en equipos sin entorno
# gráfico (servidores SSH, contenedores o la computadora remota con la GPU).
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from command_normalizer import get_default_normalizer
from dataset_evaluation import (
    DEFAULT_CLIPS_RULES,
    ClipsPlanValidator,
    evaluate_predictions,
    print_evaluation_report,
)
from goal_schema import semantic_slots, validate_goals
from inference import (
    ADAPTER_PATH,
    DEFAULT_DEVICE_MAP,
    ResourceTimer,
    configure_runtime_resources,
    default_cpu_threads,
    get_compute_dtype,
    load_model,
    load_tokenizer,
    translate,
)


DEFAULT_BENCHMARK = Path(__file__).with_name("model_evaluation_cases.jsonl")
DEFAULT_PLOTS_DIR = Path("evaluation_plots")


def load_benchmark(path, max_samples=0, families=None):
    """Carga y valida los casos antes de ocupar GPU con el modelo."""
    selected_families = set(families or ())
    rows = []
    seen_ids = set()
    seen_inputs = set()
    with open(path, "r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            case_id = str(row.get("id", "")).strip()
            command = row.get("input")
            goals = row.get("goals")
            meta = row.get("meta") or {}
            family = str(meta.get("family", "unknown"))

            if not case_id:
                raise ValueError(f"Línea {line_no}: falta id")
            if case_id in seen_ids:
                raise ValueError(f"Línea {line_no}: id duplicado {case_id!r}")
            if not isinstance(command, str) or not command.strip():
                raise ValueError(f"Línea {line_no}: input inválido")
            input_key = " ".join(command.casefold().split())
            if input_key in seen_inputs:
                raise ValueError(f"Línea {line_no}: input duplicado {command!r}")
            issues = validate_goals(goals if isinstance(goals, list) else [])
            if issues:
                raise ValueError(
                    f"Línea {line_no}: goals inválidos: "
                    + "; ".join(map(str, issues))
                )

            seen_ids.add(case_id)
            seen_inputs.add(input_key)
            if selected_families and family not in selected_families:
                continue
            rows.append(row)
            if max_samples > 0 and len(rows) >= max_samples:
                break
    if not rows:
        raise ValueError("El benchmark no contiene casos seleccionados")
    return rows


def prediction_payload(result):
    if isinstance(result, dict) and "prediction" in result:
        return result["prediction"]
    return result if isinstance(result, dict) else {}


def evaluate_cached_predictions(rows, results, clips_validator=None):
    by_input = {
        row["input"]: prediction_payload(result)
        for row, result in zip(rows, results)
    }
    report = evaluate_predictions(
        rows,
        predict=lambda command: by_input[command],
        clips_validator=clips_validator,
        max_samples=len(rows),
    )
    add_casefold_metrics(report, rows, results)
    return report


def _casefold_value(value):
    return " ".join(str(value).casefold().split())


def goals_equal_casefold(expected, predicted):
    """Compara goals conservando estructura pero ignorando solo capitalización."""
    return len(expected) == len(predicted) and all(
        _casefold_value(expected_goal) == _casefold_value(predicted_goal)
        for expected_goal, predicted_goal in zip(expected, predicted)
    )


def add_casefold_metrics(report, rows, results):
    """Añade métricas canónicas sin reemplazar el exact match estricto."""
    casefold_exact = 0
    case_only_differences = 0
    family_counts = {}
    slot_expected = 0
    slot_predicted = 0
    slot_correct = 0

    for row, result in zip(rows, results):
        prediction = prediction_payload(result)
        predicted_goals = prediction.get("goals", [])
        expected_goals = row["goals"]
        strict_exact = predicted_goals == expected_goals
        canonical_exact = goals_equal_casefold(expected_goals, predicted_goals)
        casefold_exact += int(canonical_exact)
        case_only_differences += int(canonical_exact and not strict_exact)

        family = str((row.get("meta") or {}).get("family", "unknown"))
        counts = family_counts.setdefault(
            family, {"casefold_exact": 0, "total": 0}
        )
        counts["casefold_exact"] += int(canonical_exact)
        counts["total"] += 1

        if validate_goals(predicted_goals):
            continue
        expected_slots = semantic_slots(expected_goals)
        predicted_slots = semantic_slots(predicted_goals)
        slot_expected += len(expected_slots)
        slot_predicted += len(predicted_slots)
        slot_correct += sum(
            _casefold_value(predicted_slots.get(key, ""))
            == _casefold_value(expected_value)
            for key, expected_value in expected_slots.items()
        )

    samples = len(rows)
    report["totals"]["casefold_exact"] = casefold_exact
    report["totals"]["casefold_exact_accuracy"] = (
        casefold_exact / samples if samples else 0.0
    )
    report["totals"]["case_only_differences"] = case_only_differences

    for family, counts in family_counts.items():
        family_report = report["families"].setdefault(family, {})
        family_report["casefold_exact"] = counts["casefold_exact"]
        family_report["casefold_accuracy"] = (
            counts["casefold_exact"] / counts["total"]
            if counts["total"]
            else 0.0
        )

    precision = slot_correct / slot_predicted if slot_predicted else 0.0
    recall = slot_correct / slot_expected if slot_expected else 0.0
    report["casefold_slots"] = {
        "correct": slot_correct,
        "expected": slot_expected,
        "predicted": slot_predicted,
        "precision": precision,
        "recall": recall,
        "f1": (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        ),
    }


def case_details(rows, results):
    details = []
    for row, result in zip(rows, results):
        prediction = prediction_payload(result)
        predicted_goals = prediction.get("goals", [])
        expected_goals = row["goals"]
        strict_exact = predicted_goals == expected_goals
        casefold_exact = goals_equal_casefold(expected_goals, predicted_goals)
        details.append(
            {
                "id": row["id"],
                "family": (row.get("meta") or {}).get("family", "unknown"),
                "input": row["input"],
                "normalized_input": result.get("normalized_input", row["input"]),
                "expected": expected_goals,
                "predicted": predicted_goals,
                "exact": strict_exact,
                "casefold_exact": casefold_exact,
                "case_only_difference": casefold_exact and not strict_exact,
                "elapsed_ms": result.get("_elapsed_ms"),
                "prediction_error": result.get("error"),
                "raw": result.get("raw"),
            }
        )
    return details


def print_case_details(details, show_all=False):
    for detail in details:
        if detail["exact"] and not show_all:
            continue
        status = (
            "OK"
            if detail["exact"]
            else "CASE-OK"
            if detail["case_only_difference"]
            else "ERROR"
        )
        print(f"\n[{status}] {detail['id']} | {detail['family']}")
        print(f"Input:       {detail['input']}")
        print(f"Normalizado: {detail['normalized_input']}")
        print("Esperado:   " + json.dumps(detail["expected"], ensure_ascii=False))
        print("Predicho:   " + json.dumps(detail["predicted"], ensure_ascii=False))
        if detail["prediction_error"]:
            print(f"Error:       {detail['prediction_error']}")
        if detail["raw"]:
            print(f"Raw:         {detail['raw']}")


def _save_figure(figure, path):
    """Guarda y cierra una figura para no acumular memoria entre gráficas."""
    figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def _plot_metric_overview(report, output_dir):
    """Resume las métricas globales más importantes en una sola escala 0-100%."""
    totals = report["totals"]
    metrics = [
        ("Exact estricto", totals.get("exact_accuracy", 0.0)),
        ("Exact sin mayúsculas", totals.get("casefold_exact_accuracy", 0.0)),
        ("Esquema válido", totals.get("schema_valid_rate", 0.0)),
        ("Slots F1", report.get("slots", {}).get("f1", 0.0)),
        ("Slots F1 canónico", report.get("casefold_slots", {}).get("f1", 0.0)),
    ]
    if "clips_planifiable_rate" in totals:
        metrics.append(("Planificable CLIPS", totals["clips_planifiable_rate"]))
    for kind in ("person", "object"):
        if kind in report.get("entity_kinds", {}):
            metrics.append(
                (f"kind={kind}", report["entity_kinds"][kind].get("accuracy", 0.0))
            )

    labels, values = zip(*metrics)
    figure, axis = plt.subplots(figsize=(11, 5.5))
    bars = axis.bar(labels, values, color="#2878B5")
    axis.set_ylim(0.0, 1.08)
    axis.set_ylabel("Proporción")
    axis.set_title("Resumen de calidad del parser semántico")
    axis.grid(axis="y", alpha=0.25)
    axis.tick_params(axis="x", rotation=30)
    for bar, value in zip(bars, values):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            min(value + 0.02, 1.055),
            f"{value:.1%}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    path = output_dir / "metrics_overview.png"
    _save_figure(figure, path)
    return path


def _plot_family_accuracy(report, output_dir):
    """Compara exact match estricto y canónico para cada familia del benchmark."""
    families = report.get("families", {})
    ordered = sorted(
        families,
        key=lambda family: (
            families[family].get("casefold_accuracy", 0.0),
            families[family].get("accuracy", 0.0),
            family,
        ),
    )
    strict = [families[family].get("accuracy", 0.0) for family in ordered]
    canonical = [families[family].get("casefold_accuracy", 0.0) for family in ordered]
    positions = list(range(len(ordered)))
    height = max(6.0, len(ordered) * 0.34)
    figure, axis = plt.subplots(figsize=(12, height))
    axis.barh(
        [position - 0.18 for position in positions],
        strict,
        height=0.34,
        label="Estricto",
        color="#D95319",
    )
    axis.barh(
        [position + 0.18 for position in positions],
        canonical,
        height=0.34,
        label="Sin distinguir mayúsculas",
        color="#2CA02C",
    )
    axis.set_yticks(positions, ordered)
    axis.set_xlim(0.0, 1.05)
    axis.set_xlabel("Exact match")
    axis.set_title("Exact match por familia")
    axis.grid(axis="x", alpha=0.25)
    axis.legend(loc="lower right")
    path = output_dir / "family_accuracy.png"
    _save_figure(figure, path)
    return path


def _percentile(values, percentile):
    """Percentil lineal sencillo; evita depender de NumPy para tres estadísticas."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _plot_outcomes_and_latency(report, details, output_dir):
    """Muestra tipos de resultado y distribución de latencia por comando."""
    totals = report["totals"]
    strict = totals.get("exact", 0)
    case_only = totals.get("case_only_differences", 0)
    errors = totals.get("samples", 0) - strict - case_only
    latencies = [
        float(detail["elapsed_ms"])
        for detail in details
        if isinstance(detail.get("elapsed_ms"), (int, float))
    ]

    figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    outcome_labels = ["Exacto", "Solo mayúsculas", "Error semántico"]
    outcome_values = [strict, case_only, errors]
    bars = axes[0].bar(
        outcome_labels,
        outcome_values,
        color=["#2CA02C", "#F0AD4E", "#D62728"],
    )
    axes[0].set_title("Resultados por caso")
    axes[0].set_ylabel("Número de comandos")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].tick_params(axis="x", rotation=20)
    for bar, value in zip(bars, outcome_values):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.15,
            str(value),
            ha="center",
        )

    if latencies:
        axes[1].hist(latencies, bins=min(12, max(4, len(latencies) // 4)), color="#2878B5")
        average = sum(latencies) / len(latencies)
        p50 = _percentile(latencies, 0.50)
        p95 = _percentile(latencies, 0.95)
        axes[1].axvline(average, color="#D95319", linestyle="--", label=f"media {average:.0f} ms")
        axes[1].axvline(p50, color="#2CA02C", linestyle=":", label=f"p50 {p50:.0f} ms")
        axes[1].axvline(p95, color="#9467BD", linestyle="-.", label=f"p95 {p95:.0f} ms")
        axes[1].legend()
    else:
        axes[1].text(0.5, 0.5, "Sin datos de latencia", ha="center", va="center")
    axes[1].set_title("Latencia de inferencia")
    axes[1].set_xlabel("Milisegundos por comando")
    axes[1].set_ylabel("Frecuencia")
    axes[1].grid(axis="y", alpha=0.25)

    path = output_dir / "outcomes_and_latency.png"
    _save_figure(figure, path)
    return path


def _write_case_csv(details, output_dir):
    """Exporta una tabla fácil de ordenar en LibreOffice, pandas o R."""
    path = output_dir / "case_results.csv"
    fields = [
        "id",
        "family",
        "exact",
        "casefold_exact",
        "case_only_difference",
        "elapsed_ms",
        "input",
        "normalized_input",
        "expected",
        "predicted",
        "prediction_error",
    ]
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for detail in details:
            row = {field: detail.get(field) for field in fields}
            row["expected"] = json.dumps(detail["expected"], ensure_ascii=False)
            row["predicted"] = json.dumps(detail["predicted"], ensure_ascii=False)
            writer.writerow(row)
    return path


def create_evaluation_artifacts(report, details, output_dir=DEFAULT_PLOTS_DIR):
    """Crea gráficas y CSV sin volver a ejecutar inferencia ni CLIPS."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return [
        _plot_metric_overview(report, output_dir),
        _plot_family_accuracy(report, output_dir),
        _plot_outcomes_and_latency(report, details, output_dir),
        _write_case_csv(details, output_dir),
    ]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", nargs="?", default=str(DEFAULT_BENCHMARK))
    parser.add_argument("--adapter-path", default=ADAPTER_PATH)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument(
        "--family",
        action="append",
        dest="families",
        help="Evalúa solo esta familia; se puede repetir.",
    )
    parser.add_argument("--show-all", action="store_true")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--plots-dir", default=str(DEFAULT_PLOTS_DIR))
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--require-perfect", action="store_true")
    parser.add_argument(
        "--strict-case",
        action="store_true",
        help="Hace que --require-perfect también exija mayúsculas idénticas.",
    )
    parser.add_argument("--no-clips", action="store_true")
    parser.add_argument("--clips-rules", default=str(DEFAULT_CLIPS_RULES))
    parser.add_argument("--device-map", default=DEFAULT_DEVICE_MAP)
    parser.add_argument("--max-memory", default="")
    parser.add_argument("--cpu-offload", action="store_true")
    parser.add_argument("--cpu-threads", type=int, default=default_cpu_threads())
    parser.add_argument("--no-tf32", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    rows = load_benchmark(args.benchmark, args.max_samples, args.families)
    print(f"Benchmark: {args.benchmark} | casos: {len(rows)}")
    print(f"Adaptador: {args.adapter_path}")

    configure_runtime_resources(
        cpu_threads=args.cpu_threads,
        allow_tf32=not args.no_tf32,
    )
    with ResourceTimer("carga tokenizer"):
        tokenizer = load_tokenizer(args.adapter_path)
    with ResourceTimer("carga modelo base y adaptador"):
        model = load_model(
            get_compute_dtype(),
            device_map=args.device_map,
            max_memory=args.max_memory or None,
            cpu_offload=args.cpu_offload,
            adapter_path=args.adapter_path,
        )

    normalizer = get_default_normalizer()
    results = []
    started = time.perf_counter()
    for index, row in enumerate(rows, start=1):
        case_started = time.perf_counter()
        result = translate(
            row["input"],
            model,
            tokenizer,
            normalizer=normalizer,
            return_normalized=True,
        )
        # Se guarda junto a la predicción para que las gráficas no tengan que
        # ejecutar el modelo una segunda vez.
        result["_elapsed_ms"] = (time.perf_counter() - case_started) * 1000.0
        results.append(result)
        print(f"\rInferencia {index}/{len(rows)}", end="", flush=True)
    elapsed = time.perf_counter() - started
    print()

    clips_validator = None
    try:
        if not args.no_clips:
            clips_validator = ClipsPlanValidator(args.clips_rules)
        report = evaluate_cached_predictions(rows, results, clips_validator)
    finally:
        if clips_validator is not None:
            clips_validator.close()

    details = case_details(rows, results)
    print_case_details(details, show_all=args.show_all)
    report["runtime"] = {
        "seconds": elapsed,
        "samples_per_second": len(rows) / elapsed if elapsed else 0.0,
    }
    if not args.no_plots:
        artifacts = create_evaluation_artifacts(report, details, args.plots_dir)
        report["artifacts"] = {"files": [str(path) for path in artifacts]}
        print("Artefactos de evaluación:")
        for path in artifacts:
            print(f"  {path}")
    print_evaluation_report(report, "Evaluación semántica del benchmark")

    if args.output_json:
        payload = {"report": report, "cases": details}
        with open(args.output_json, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        print(f"Reporte detallado guardado en {args.output_json}")

    exact_key = "exact" if args.strict_case else "casefold_exact"
    accepted_exact = report["totals"].get(exact_key, 0)
    if args.require_perfect and accepted_exact != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
