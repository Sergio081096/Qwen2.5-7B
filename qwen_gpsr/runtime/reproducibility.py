"""Inventario de la inferencia cargada; no contiene credenciales."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

from qwen_gpsr.paths import CATALOG_DIR, REPO_ROOT


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def inventory(directory, patterns):
    directory = Path(directory).resolve()
    files = sorted({p for pattern in patterns for p in directory.glob(pattern) if p.is_file()})
    entries = [{'path': str(p.relative_to(directory)), 'sha256': file_sha256(p)} for p in files]
    encoded = json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()
    return {'method': 'sha256(sorted relative-path/sha256 inventory JSON)',
            'sha256': hashlib.sha256(encoded).hexdigest(), 'files': entries}


def metadata(adapter_path, inference, model, runtime):
    adapter = inventory(adapter_path, ['*.json', '*.safetensors', '*.bin', '*.txt', '*.model', '*.jinja'])
    catalogs = inventory(CATALOG_DIR, ['names/*.md', 'maps/*names.md', 'objects/objects.md'])
    sources = inventory(REPO_ROOT, ['qwen_gpsr/runtime/inference.py', 'qwen_gpsr/runtime/server.py',
                                  'qwen_gpsr/runtime/reproducibility.py', 'qwen_gpsr/runtime/resources.py', 'qwen_gpsr/paths.py',
                                  'qwen_gpsr/domain/*.py'])
    packages = {}
    for name in ('torch', 'transformers', 'peft', 'accelerate', 'bitsandbytes'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    result = {
        'schema_version': '1.0', 'base_model': json.loads((Path(adapter_path)/'adapter_config.json').read_text())['base_model_name_or_path'],
        'resource_measurement': {'method':'process CPU + sampled RSS/PyTorch allocator', 'interval_ms':50},
        'base_model_revision': getattr(model.config, '_commit_hash', None),
        'adapter_path': str(Path(adapter_path).resolve()), 'adapter_inventory': adapter,
        'normalizer_sha256': file_sha256(REPO_ROOT / 'qwen_gpsr/domain/command_normalizer.py'),
        'catalogs_inventory': catalogs, 'source_inventory': sources,
        'generation': {'do_sample': False, 'max_new_tokens': inference.MAX_NEW_TOKENS,
                       'repetition_penalty': 1.05},
        'model_generation_config': model.generation_config.to_dict(),
        'runtime': runtime, 'python': platform.python_version(), 'packages': packages,
        'raw_model_text_exposed': False,
    }
    result['effective_config_sha256'] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    return result
