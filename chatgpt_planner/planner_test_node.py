#!/usr/bin/env python3
"""Nodo independiente de pruebas GPSR. No publica acciones al robot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from jsonschema import Draft202012Validator

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent))
from goal_schema import parse_goal, validate_goals


def load_artifacts():
    prompt = (BASE / "system_prompt.md").read_text(encoding="utf-8")
    schema = json.loads((BASE / "response_schema.json").read_text(encoding="utf-8"))
    if not prompt.strip():
        raise ValueError("El prompt está vacío")
    Draft202012Validator.check_schema(schema)
    return prompt, schema


def validate_result(result, schema):
    """Comprueba contrato y goals; no demuestra equivalencia semántica con CLIPS."""
    Draft202012Validator(schema).validate(result)
    if result["status"] != "executable":
        if not result["message"].strip() or any(result[k] for k in ("goals", "plan", "start_note", "end_note")):
            raise ValueError("Una aclaración/rechazo requiere mensaje y plan vacío")
        return
    if result["message"] or not result["goals"] or not result["plan"]:
        raise ValueError("Un plan ejecutable requiere goals, plan y message vacío")
    if (result["start_note"], result["end_note"]) != ("GPSR_START", "GPSR_DONE"):
        raise ValueError("Marcadores de inicio/fin incorrectos")
    issues = validate_goals(result["goals"])
    if issues:
        raise ValueError(f"Goals inválidos: {issues}")
    if any(parse_goal(goal).name in {"drop", "talk"} for goal in result["goals"]):
        raise ValueError("Goals obsoletos: usa place en lugar de drop y tell en lugar de talk")
    plan = result["plan"]
    announcements = [s for s in plan if s["step"] < 1001]
    operations = [s for s in plan if s["step"] >= 1001]
    expected = list(range(1, len(announcements) + 1)) + list(range(1001, 1001 + len(operations)))
    if len(announcements) > 1000 or [s["step"] for s in plan] != expected:
        raise ValueError("Numeración desordenada, duplicada o con huecos")
    if any(s["action"] != "say" for s in announcements):
        raise ValueError("Los anuncios deben usar say")
    if any(len(s["params"]) != 1 or not s["params"][0].strip() for s in plan):
        raise ValueError("Cada paso requiere exactamente un parámetro no vacío")
    if not operations or (operations[-1]["action"], operations[-1]["params"]) != ("say", ["task completed"]):
        raise ValueError("Falta el cierre task completed")


def run_request(client, command, model, prompt, schema, output, max_output_tokens):
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": command, "requested_model": model,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
        "parameters": {"max_output_tokens": max_output_tokens, "store": False},
        "valid": False,
    }
    started = time.perf_counter()
    try:
        response = client.responses.create(
            model=model, store=False, max_output_tokens=max_output_tokens,
            input=[{"role": "system", "content": prompt}, {"role": "user", "content": command}],
            text={"format": {"type": "json_schema", "name": "gpsr_direct_plan", "strict": True, "schema": schema}},
        )
        record["raw_response"] = response.model_dump(mode="json")
        if response.status != "completed":
            raise ValueError(f"Respuesta no completada: {response.status}")
        refusals = [c.refusal for item in response.output for c in getattr(item, "content", []) if c.type == "refusal"]
        if refusals:
            raise ValueError("Rechazo de API: " + " ".join(refusals))
        result = json.loads(response.output_text)
        record["result"] = result
        validate_result(result, schema)
        record["valid"] = True
    except Exception as exc:
        # No guardar texto arbitrario de errores del SDK que pueda contener credenciales.
        record["error"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    finally:
        record["latency_seconds"] = round(time.perf_counter() - started, 4)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-local", action="store_true", help="Validar ejemplos sin API")
    mode.add_argument("--command", help="Comando GPSR en inglés")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""), help="Modelo/snapshot elegido manualmente")
    parser.add_argument("--output", type=Path, default=BASE / "runs" / "results.jsonl")
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    args = parser.parse_args()
    if args.max_output_tokens <= 0:
        parser.error("--max-output-tokens debe ser positivo")
    prompt, schema = load_artifacts()
    if args.validate_local:
        examples = [json.loads(line) for line in (BASE / "example_outputs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if not examples:
            raise ValueError("No hay ejemplos")
        for example in examples:
            validate_result(example["response"], schema)
        print(f"OK: prompt, esquema y {len(examples)} ejemplos válidos. Sin llamadas API.")
        return 0
    if not args.command.strip():
        parser.error("El comando no puede estar vacío")
    if not args.model.strip() or not os.getenv("OPENAI_API_KEY", "").strip():
        parser.error("Configura manualmente OPENAI_API_KEY y OPENAI_MODEL (o --model)")
    from openai import OpenAI
    with OpenAI(timeout=60.0, max_retries=0) as client:
        record = run_request(client, args.command, args.model, prompt, schema, args.output, args.max_output_tokens)
    print(json.dumps(record.get("result", {"error": record.get("error")}), ensure_ascii=False, indent=2))
    print(f"Validación: {record['valid']}. Registro: {args.output}", file=sys.stderr)
    if not record["valid"]:
        print(record["error"], file=sys.stderr)
    return 0 if record["valid"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
