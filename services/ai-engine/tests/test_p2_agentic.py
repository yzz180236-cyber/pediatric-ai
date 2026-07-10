import os
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from agent.graph import (  # noqa: E402
    _apply_local_query_synonyms,
    _build_checkpointer,
    _build_user_fact_memory,
    _normalize_ocr_result,
    _truncate_history_for_model,
)


class QueryExpansionTests(unittest.TestCase):
    def test_local_query_synonyms_expand_parent_language(self) -> None:
        expanded = _apply_local_query_synonyms("宝宝拉稀像水一样")
        self.assertIn("腹泻", expanded)
        self.assertIn("补液盐", expanded)


class OcrFallbackTests(unittest.TestCase):
    def test_normalize_ocr_result_marks_low_confidence_items(self) -> None:
        payload = _normalize_ocr_result(
            {
                "items": [
                    {"name": "白细胞", "result": "10.0", "referenceRange": "4-10", "confidence": 0.92},
                    {"name": "中性粒细胞", "result": "75%", "referenceRange": "40-70%", "confidence": 0.5},
                ]
            }
        )
        self.assertFalse(payload["items"][0]["warningFlag"])
        self.assertTrue(payload["items"][1]["warningFlag"])
        self.assertTrue(payload["needsManualReview"])
        self.assertIn("中性粒细胞", payload["lowConfidenceItems"])


class MemoryWindowTests(unittest.TestCase):
    def test_truncate_history_window_keeps_recent_messages(self) -> None:
        previous = os.environ.get("CHAT_HISTORY_MAX_TOKENS")
        os.environ["CHAT_HISTORY_MAX_TOKENS"] = "200"
        history = [
            {"role": "user", "content": "a" * 2400},
            {"role": "assistant", "content": "b" * 2400},
            {"role": "user", "content": "最近这两天还是咳嗽得厉害"},
            {"role": "assistant", "content": "有发热吗？"},
        ]
        try:
            truncated = _truncate_history_for_model(history, "体温 38.5 度", "")
            self.assertLess(len(truncated), len(history))
            self.assertEqual(truncated[-1]["content"], "有发热吗？")
        finally:
            if previous is None:
                os.environ.pop("CHAT_HISTORY_MAX_TOKENS", None)
            else:
                os.environ["CHAT_HISTORY_MAX_TOKENS"] = previous

    def test_build_user_fact_memory_only_uses_structured_fields(self) -> None:
        memory = _build_user_fact_memory(
            {"status": "filled", "age": "8个月", "symptom": "咳嗽", "temperature": "38.5°C"},
            {"triageLevel": "visit_within_24h", "summaryText": "主诉：咳嗽；分诊结论：24小时内就医"},
        )
        self.assertIn("age=8个月", memory)
        self.assertIn("triage=visit_within_24h", memory)


class CheckpointerTests(unittest.TestCase):
    def test_build_checkpointer_falls_back_to_memory_without_dsn(self) -> None:
        previous = os.environ.pop("LANGGRAPH_POSTGRES_DSN", None)
        try:
            saver = _build_checkpointer()
            self.assertIn(saver.__class__.__name__, {"MemorySaver", "InMemorySaver"})
        finally:
            if previous is not None:
                os.environ["LANGGRAPH_POSTGRES_DSN"] = previous


if __name__ == "__main__":
    unittest.main()
