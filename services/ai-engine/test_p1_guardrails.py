import tempfile
import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from agent.graph import (
    _evaluate_reply_safety,
    _extract_first_json_object,
    _extract_citation_indices,
    emergency_guard_node,
)
from init_knowledge import discover_source_files


class JsonParserTests(unittest.TestCase):
    def test_extract_first_json_object_supports_markdown_fence(self) -> None:
        payload = """```json
        {"intent_type":"medical","confidence":0.92}
        ```"""
        parsed = _extract_first_json_object(payload)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["intent_type"], "medical")


class SafetyGuardrailTests(unittest.TestCase):
    def test_reply_safety_blocks_prescription_dosage(self) -> None:
        reply = (
            "可以口服阿莫西林 5ml 每天三次帮助控制感染。\n\n"
            "> ⚠️ 免责声明：以上内容仅供医学参考，不能替代执业医师面诊。"
        )
        violations = _evaluate_reply_safety(reply, citations=[], require_citation_protocol=True)
        self.assertTrue(any("药物名称与剂量" in item for item in violations))

    def test_reply_safety_blocks_invalid_citation_index(self) -> None:
        reply = (
            "根据指南建议，先补液观察[^3]。\n\n"
            "> ⚠️ 免责声明：以上内容仅供医学参考，不能替代执业医师面诊。"
        )
        citations = [{"title": "指南A", "chapter": "第一章", "content": "x", "sourceType": "guideline"}]
        violations = _evaluate_reply_safety(reply, citations=citations, require_citation_protocol=True)
        self.assertTrue(any("引用编号超出" in item for item in violations))
        self.assertEqual(_extract_citation_indices(reply), [3])

    def test_emergency_guard_skips_measurement_only_recent_messages(self) -> None:
        state = {
            "trace_id": "test-trace",
            "messages": ["8个月，9.2kg，72cm"],
            "history": [{"role": "user", "content": "7个月，8.8kg，71cm"}],
            "patient_context": {},
        }
        self.assertEqual(emergency_guard_node(state), {})


class KnowledgeInitTests(unittest.TestCase):
    def test_discover_source_files_finds_pdf_and_txt_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.txt").write_text("text", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "b.pdf").write_bytes(b"%PDF-1.4")
            (nested / "ignore.md").write_text("x", encoding="utf-8")

            files = discover_source_files(root)

            self.assertEqual([path.name for path in files], ["a.txt", "b.pdf"])


if __name__ == "__main__":
    unittest.main()
