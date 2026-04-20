from __future__ import annotations

from .bootstrap import append_bootstrap_log, bootstrap_plugin

try:
    BOOTSTRAP_STATE = bootstrap_plugin(__file__)
    from .native_illustration_compiler import NativeIllustrationCompilerExtension
except Exception as exc:  # pragma: no cover - Krita runtime only
    append_bootstrap_log("Plugin bootstrap failed", exc)
    raise

__all__ = ["NativeIllustrationCompilerExtension", "BOOTSTRAP_STATE"]
