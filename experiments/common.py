"""Persistencia y trazabilidad sin dependencias de modelos ni ROS."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import uuid
from qwen_gpsr.runtime.resources import unavailable

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
INITIAL_STATE = {"location": "unknown", "holding": "nothing", "focus": False,
                 "manipulation_enabled": True}
TIMINGS = ("total_ms", "model_request_ms", "adaptation_ms", "planning_ms",
           "extraction_ms", "validation_ms")


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def object_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open(encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError('not an object')
            except (ValueError, TypeError) as exc:
                raise ValueError(f'{path.name}:{n}: JSONL inválido; conservar y revisar el archivo') from exc
            rows.append(row)
    return rows


def append_jsonl(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Do not append after an incomplete record left by power loss.
    if path.exists() and path.stat().st_size:
        with path.open('rb') as f:
            f.seek(-1, 2)
            if f.read(1) != b'\n':
                raise ValueError(f'{path.name}: última fila incompleta; requiere recuperación')
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


@contextmanager
def campaign_lock(directory):
    with (Path(directory) / '.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('La campaña está abierta por otro proceso') from exc
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def load_inputs(path):
    rows = read_jsonl(path)
    if not rows:
        raise ValueError('El conjunto de entradas está vacío')
    ids = set()
    for row in rows:
        for key in ('id', 'input'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f'Entrada sin {key} válido')
        if row['id'] in ids:
            raise ValueError(f'ID duplicado: {row["id"]}')
        ids.add(row['id'])
        if row.get('intent_id') is not None and (
            not isinstance(row['intent_id'], str) or not row['intent_id'].strip()
        ):
            raise ValueError('intent_id debe ser cadena no vacía o null')
    return rows


def new_record(manifest, config, case, repetition, attempt):
    return dict(schema_version='1.0', example_only=False,
                campaign_id=manifest['campaign_id'], run_id=str(uuid.uuid4()),
                case_id=case['id'], intent_id=case.get('intent_id'),
                architecture=config['architecture'], config_id=config['config_id'],
                condition_label=config.get('label',config['architecture']),
                resources={'client':unavailable('measurement_not_completed'),
                           'model_internal':unavailable('provider_does_not_expose_internal_resources' if config['architecture']=='gpt_direct'
                               else 'not_applicable' if config['architecture']=='reference_clips' else 'server_measurement_not_received')},
                repetition=repetition, attempt=attempt, started_at_utc=utc(),
                finished_at_utc=None, input_original=case['input'],
                execution_status=None, response_kind=None, goals_pred=None, plan=None,
                message=None, raw_output=None, raw_output_kind=None,
                timing=dict.fromkeys(TIMINGS),
                validation=dict(response_schema_valid=None, goals_schema_valid=None,
                                plan_contract_valid=None, issues=[]),
                error=None, qwen_clips=None, gpt=None, reference_clips=None)


class ExperimentError(Exception):
    """Error cuyo mensaje controlado puede guardarse sin exponer credenciales."""
    def __init__(self, kind, message):
        self.kind = kind
        super().__init__(message)


def error_info(exc, stage):
    # SDK exceptions may embed requests, URLs or credentials. Never log str(exc).
    return {'stage': stage, 'type': getattr(exc, 'kind', type(exc).__name__),
            'message': str(exc) if isinstance(exc, ExperimentError) else type(exc).__name__,
            'limit_ms': None}
