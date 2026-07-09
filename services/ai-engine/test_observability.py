import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.append(str(Path(__file__).resolve().parent))

from observability import build_langfuse_run_config  # noqa: E402


class ObservabilityTests(unittest.TestCase):
    def test_langfuse_config_returns_empty_when_disabled(self) -> None:
        previous = os.environ.pop("LANGFUSE_ENABLED", None)
        try:
            config = build_langfuse_run_config("trace-1", "session-1", "api/chat")
            self.assertEqual(config, {})
        finally:
            if previous is not None:
                os.environ["LANGFUSE_ENABLED"] = previous

    def test_langfuse_config_includes_callback_metadata_and_tags(self) -> None:
        callback_instance = Mock()
        with (
            patch("observability.get_langfuse_client", return_value=Mock(create_trace_id=lambda: "a" * 32)),
            patch("langfuse.langchain.CallbackHandler", return_value=callback_instance),
        ):
            config = build_langfuse_run_config("trace-1234", "session-1", "api/chat/stream")

        self.assertEqual(config["callbacks"], [callback_instance])
        self.assertEqual(config["metadata"]["session_id"], "session-1")
        self.assertIn("service:ai-engine", config["tags"])


if __name__ == "__main__":
    unittest.main()
