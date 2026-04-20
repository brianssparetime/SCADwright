"""Logging setup for scadwright.

Loggers follow the package hierarchy under `scadwright.*`. The library itself
never configures handlers at import time (best practice). Call `sc.set_verbose()`
to attach a stderr handler with a compact formatter for "show me what's happening."
"""

from __future__ import annotations

import logging
import sys
from typing import Final

_ROOT_NAME: Final = "scadwright"
_HANDLER_NAME: Final = "scadwright.stderr"


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the scadwright.* namespace."""
    if name == _ROOT_NAME:
        return logging.getLogger(name)
    if not name.startswith(f"{_ROOT_NAME}."):
        name = f"{_ROOT_NAME}.{name}"
    return logging.getLogger(name)


class _PrettyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # e.g. [scadwright.component INFO] built Widget in 2.3ms
        return f"[{record.name} {record.levelname}] {record.getMessage()}"


def set_verbose(level: int | bool = logging.INFO) -> None:
    """Configure the scadwright logger hierarchy for user-visible output.

    Idempotent: calling multiple times won't stack handlers.

    - True or INFO (default): show INFO-level events (build timings, emit boundaries).
    - DEBUG: also show per-primitive construction.
    - False or WARNING: only warnings and errors.
    - Any logging level: passed through.
    """
    if level is True:
        level = logging.INFO
    elif level is False:
        level = logging.WARNING

    root = logging.getLogger(_ROOT_NAME)
    root.setLevel(level)
    # Remove any existing handler we installed previously.
    for h in list(root.handlers):
        if getattr(h, "_scadwright_managed", False):
            root.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_PrettyFormatter())
    handler.setLevel(level)
    handler._scadwright_managed = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    # Prevent propagation to the root logger so we don't double-print if the
    # user also has root handlers configured.
    root.propagate = False
