import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from agent.graph import build_graph  # noqa: E402
import observability  # noqa: E402


class _CollectorHandler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        self.__class__.requests.append((self.path, payload))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):  # noqa: A003
        return


class LangfuseSmokeTests(unittest.TestCase):
    def test_graph_run_exports_spans_to_langfuse_otlp_endpoint(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _CollectorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        previous_env = {key: os.environ.get(key) for key in [
            "LANGFUSE_ENABLED",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_HOST",
            "LANGGRAPH_POSTGRES_DSN",
        ]}
        _CollectorHandler.requests = []
        observability._langfuse_client = None
        try:
            os.environ["LANGFUSE_ENABLED"] = "true"
            os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-test"
            os.environ["LANGFUSE_SECRET_KEY"] = "sk-test"
            os.environ["LANGFUSE_HOST"] = f"http://127.0.0.1:{server.server_port}"
            os.environ.pop("LANGGRAPH_POSTGRES_DSN", None)

            app = build_graph()
            app.invoke(
                {
                    "messages": ["孩子手足口病，高烧还抽搐怎么办"],
                    "history": [],
                    "patient_profile": "",
                    "patient_context": {"ageMonths": 18},
                    "trace_id": "trace-langfuse",
                },
                config={
                    "configurable": {"thread_id": "langfuse-smoke"},
                    **observability.build_langfuse_run_config("trace-langfuse", "langfuse-smoke", "smoke"),
                },
            )
            observability.flush_langfuse()
            time.sleep(0.5)

            self.assertTrue(_CollectorHandler.requests)
            self.assertTrue(any("/api/public/otel" in path for path, _ in _CollectorHandler.requests))
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            observability._langfuse_client = None


if __name__ == "__main__":
    unittest.main()
