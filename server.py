#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import inference


class QwenHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class QwenBackend:
    def __init__(
        self,
        *,
        device_map: str,
        max_memory: str,
        cpu_offload: bool,
        cpu_threads: int,
        allow_tf32: bool,
    ) -> None:
        used_threads = inference.configure_runtime_resources(
            cpu_threads=cpu_threads,
            allow_tf32=allow_tf32,
        )
        print(f"Runtime: CPU threads={used_threads} | device_map={device_map}")

        print("Loading Qwen tokenizer...")
        with inference.ResourceTimer("server tokenizer load"):
            self.tokenizer = inference.load_tokenizer()

        print("Loading Qwen base model and LoRA adapter...")
        with inference.ResourceTimer("server model load"):
            self.model = inference.load_model(
                inference.get_compute_dtype(),
                device_map=device_map,
                max_memory=max_memory or None,
                cpu_offload=cpu_offload,
            )

        self.normalizer = inference.get_default_normalizer()
        self.lock = threading.Lock()
        self.started_at = time.time()
        print("Qwen HTTP backend ready.")

    def translate(self, command: str) -> dict[str, Any]:
        with self.lock:
            return inference.translate(
                command,
                self.model,
                self.tokenizer,
                normalizer=self.normalizer,
                return_normalized=True,
            )


class QwenRequestHandler(BaseHTTPRequestHandler):
    backend: QwenBackend
    api_key: str
    max_body_bytes: int

    def do_GET(self) -> None:
        if self._path() != "/health":
            self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")
            return
        self._send_json(
            {
                "ok": True,
                "status": "ready",
                "model_loaded": True,
                "uptime_s": time.time() - self.backend.started_at,
            }
        )

    def do_POST(self) -> None:
        if self._path() != "/translate":
            self._send_error(HTTPStatus.NOT_FOUND, "unknown endpoint")
            return
        if not self._authorized():
            self._send_error(HTTPStatus.UNAUTHORIZED, "unauthorized")
            return

        try:
            payload = self._read_json()
            command = str(payload.get("command", "")).strip()
            if not command:
                self._send_error(HTTPStatus.BAD_REQUEST, "missing command")
                return

            start = time.perf_counter()
            result = self.backend.translate(command)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if "error" in result:
                self._send_json(
                    {
                        "ok": False,
                        "error": result["error"],
                        "raw": result.get("raw", ""),
                        "normalized_input": result.get("normalized_input", command),
                        "elapsed_ms": elapsed_ms,
                    },
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )
                return

            self._send_json({"ok": True, "result": result, "elapsed_ms": elapsed_ms})
        except json.JSONDecodeError:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid JSON body")
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001 - return HTTP error to client.
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _authorized(self) -> bool:
        if not self.api_key:
            return True
        header = self.headers.get("Authorization", "")
        return hmac.compare_digest(header, f"Bearer {self.api_key}")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("missing JSON body")
        if length > self.max_body_bytes:
            raise ValueError(f"request body too large; limit is {self.max_body_bytes} bytes")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _path(self) -> str:
        return urlsplit(self.path).path

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Qwen GPSR inference over HTTP.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8008)
    parser.add_argument("--device-map", default=inference.DEFAULT_DEVICE_MAP)
    parser.add_argument("--max-memory", default="")
    parser.add_argument("--cpu-offload", action="store_true")
    parser.add_argument("--cpu-threads", type=int, default=inference.default_cpu_threads())
    parser.add_argument("--no-tf32", action="store_true")
    parser.add_argument("--api-key", default=os.environ.get("QWEN_API_KEY", ""))
    parser.add_argument("--max-body-bytes", type=int, default=8192)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    QwenRequestHandler.backend = QwenBackend(
        device_map=args.device_map,
        max_memory=args.max_memory,
        cpu_offload=args.cpu_offload,
        cpu_threads=args.cpu_threads,
        allow_tf32=not args.no_tf32,
    )
    QwenRequestHandler.api_key = args.api_key
    QwenRequestHandler.max_body_bytes = args.max_body_bytes

    server = QwenHTTPServer((args.host, args.port), QwenRequestHandler)
    print(f"Qwen HTTP server listening on http://{args.host}:{args.port}/translate")
    if not args.api_key:
        print("WARNING: no API key configured. Use --api-key or QWEN_API_KEY before exposing this server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping Qwen HTTP server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
