import hashlib
import logging
import os
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

_langfuse_client = None


def _env_flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_trace_id(trace_id: str | None) -> str | None:
    if not trace_id:
        return None
    cleaned = re.sub(r"[^0-9a-fA-F]", "", trace_id)
    if len(cleaned) >= 32:
        return cleaned[:32].lower()
    if cleaned:
        return hashlib.md5(cleaned.encode("utf-8")).hexdigest()
    return hashlib.md5(trace_id.encode("utf-8")).hexdigest()


def is_langfuse_enabled() -> bool:
    return _env_flag("LANGFUSE_ENABLED") and bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def get_langfuse_client():
    global _langfuse_client
    if not is_langfuse_enabled():
        return None
    if _langfuse_client is not None:
        return _langfuse_client
    try:
        from langfuse import Langfuse

        kwargs: Dict[str, Any] = {
            "public_key": os.environ.get("LANGFUSE_PUBLIC_KEY"),
            "secret_key": os.environ.get("LANGFUSE_SECRET_KEY"),
            "host": os.environ.get("LANGFUSE_HOST"),
            "environment": os.environ.get("LANGFUSE_ENVIRONMENT", "local"),
            "release": os.environ.get("LANGFUSE_RELEASE", "pediatric-ai"),
            "debug": _env_flag("LANGFUSE_DEBUG"),
            "tracing_enabled": True,
        }
        if os.environ.get("LANGFUSE_FLUSH_AT"):
            kwargs["flush_at"] = int(os.environ["LANGFUSE_FLUSH_AT"])
        if os.environ.get("LANGFUSE_FLUSH_INTERVAL"):
            kwargs["flush_interval"] = float(os.environ["LANGFUSE_FLUSH_INTERVAL"])
        _langfuse_client = Langfuse(**kwargs)
        logger.info("Langfuse tracing enabled")
        return _langfuse_client
    except Exception:
        logger.exception("初始化 Langfuse 失败，已降级为无 tracing")
        return None


def build_langfuse_run_config(
    trace_id: str,
    session_id: str,
    entrypoint: str,
) -> Dict[str, Any]:
    client = get_langfuse_client()
    if client is None:
        return {}
    try:
        from langfuse.langchain import CallbackHandler

        normalized_trace_id = _normalize_trace_id(trace_id) or client.create_trace_id()
        handler = CallbackHandler(trace_context={"trace_id": normalized_trace_id})
        return {
            "callbacks": [handler],
            "metadata": {
                "trace_id": trace_id,
                "session_id": session_id,
                "entrypoint": entrypoint,
            },
            "tags": [
                "service:ai-engine",
                f"entrypoint:{entrypoint}",
            ],
            "run_name": f"ai-engine:{entrypoint}",
        }
    except Exception:
        logger.exception("创建 Langfuse callback 失败，已跳过 tracing")
        return {}


def flush_langfuse() -> None:
    client = get_langfuse_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.exception("Langfuse flush 失败")
