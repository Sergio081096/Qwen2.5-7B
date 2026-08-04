#!/usr/bin/env python3
"""Audita un JSONL GPSR por familia, tipo, slots y planificabilidad."""

from __future__ import annotations

import argparse
import json

from dataset_evaluation import (
    DEFAULT_CLIPS_RULES,
    ClipsPlanValidator,
    evaluate_dataset_rows,
    print_evaluation_report,
)


def iter_jsonl(path, max_samples=0):
    """Lee el JSONL de forma incremental para no cargarlo completo en RAM."""
    with open(path, "r", encoding="utf-8") as stream:
        for index, line in enumerate(stream, start=1):
            if max_samples > 0 and index > max_samples:
                break
            yield json.loads(line)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="dataset_gpsr.jsonl")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--clips-samples", type=int, default=200)
    parser.add_argument("--clips-rules", default=str(DEFAULT_CLIPS_RULES))
    parser.add_argument("--no-clips", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    clips_validator = None
    if not args.no_clips:
        clips_validator = ClipsPlanValidator(args.clips_rules)
    report = evaluate_dataset_rows(
        iter_jsonl(args.path, args.max_samples),
        clips_validator=clips_validator,
        max_clips_samples=args.clips_samples,
    )
    if clips_validator is not None:
        clips_validator.close()
    print_evaluation_report(report, f"Evaluación de {args.path}")
    totals = report["totals"]
    if totals.get("invalid", 0) or totals.get("clips_failed", 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
