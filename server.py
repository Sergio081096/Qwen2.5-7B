#!/usr/bin/env python3
"""Entrada del servidor HTTP; implementación en qwen_gpsr.runtime."""

from qwen_gpsr.runtime.server import (
    QwenBackend,
    QwenHTTPServer,
    QwenRequestHandler,
    main,
    parse_args,
)

if __name__ == "__main__":
    main()
