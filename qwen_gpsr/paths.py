"""Rutas del checkout, independientes del directorio de trabajo."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CATALOG_DIR = DATA_DIR / "CompetitionTemplate"
DATASET_PATH = DATA_DIR / "datasets" / "dataset_gpsr.jsonl"
BENCHMARK_PATH = DATA_DIR / "benchmarks" / "model_evaluation_cases.jsonl"
DEVELOPMENT_DIR = DATA_DIR / "development"
MODEL_DIR = REPO_ROOT / "models" / "nl2cd_qwen7b"
REPORTS_DIR = REPO_ROOT / "reports"
