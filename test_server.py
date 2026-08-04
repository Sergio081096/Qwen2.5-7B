#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_COMMAND = "bring me the apple from the kitchen"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the local Qwen HTTP server.")
    parser.add_argument("command", nargs="?", default=DEFAULT_COMMAND)
    parser.add_argument("--url", default="http://127.0.0.1:8008")
    parser.add_argument("--api-key", default=os.environ.get("QWEN_API_KEY", ""))
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def read_json_response(response: Any) -> dict[str, Any]:
    body = response.read().decode("utf-8")
    if not body:
        return {}
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("server response is not a JSON object")
    return data


def request_json(url: str, *, api_key: str = "", payload: dict[str, Any] | None = None, timeout: float = 120.0):
    headers = {"Accept": "application/json"}
    data = None
    method = "GET"

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, read_json_response(response)
    except urllib.error.HTTPError as exc:
        return exc.code, read_json_response(exc)


def print_json(label: str, status: int, payload: dict[str, Any]) -> None:
    print(f"\n[{label}] HTTP {status}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    args = parse_args()
    base_url = args.url.rstrip("/")

    health_status, health_payload = request_json(
        f"{base_url}/health",
        timeout=args.timeout,
    )
    print_json("health", health_status, health_payload)
    if health_status != 200 or not health_payload.get("ok"):
        return 1

    started = time.perf_counter()
    translate_status, translate_payload = request_json(
        f"{base_url}/translate",
        api_key=args.api_key,
        payload={"command": args.command},
        timeout=args.timeout,
    )
    client_elapsed_ms = (time.perf_counter() - started) * 1000.0
    translate_payload["client_elapsed_ms"] = client_elapsed_ms
    print_json("translate", translate_status, translate_payload)

    return 0 if translate_status == 200 and translate_payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
