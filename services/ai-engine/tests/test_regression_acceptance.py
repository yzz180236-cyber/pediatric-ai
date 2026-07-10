import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage

sys.path.append(str(Path(__file__).resolve().parent.parent))

from agent.graph import build_graph  # noqa: E402


class RegressionAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_dsn = os.environ.pop("LANGGRAPH_POSTGRES_DSN", None)

    def tearDown(self) -> None:
        if self.previous_dsn is not None:
            os.environ["LANGGRAPH_POSTGRES_DSN"] = self.previous_dsn

    def test_mycoplasma_guideline_flow_keeps_citations_and_assessment(self) -> None:
        invoke_counter = {"agentic_tools": 0}

        def fake_json(prompt: str, trace_id: str):
            if "儿科医学检索改写器" in prompt:
                return {"expanded_query": "支原体肺炎 儿童 重症预警"}
            if "负责儿科线上分诊" in prompt:
                return {
                    "triage_level": "visit_within_24h",
                    "triage_reason": "支原体肺炎需重点观察呼吸与精神状态。",
                    "trend_direction": "unknown",
                    "trend_reason": "缺少足够历史比较。",
                    "recommended_actions": ["观察呼吸频率", "若精神差尽快就医"],
                    "warning_signals": ["呼吸急促"],
                    "constraint_warnings": ["缺少线下血氧数据"],
                    "age_band": "1-3岁",
                }
            return None

        def fake_llm(llm, messages, trace_id: str, operation: str):
            if operation == "agentic_tools":
                invoke_counter["agentic_tools"] += 1
                if invoke_counter["agentic_tools"] == 1:
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {"name": "expand_medical_query", "args": {"raw_query": "宝宝咳嗽发烧，支原体肺炎有哪些重症预警？"}, "id": "tool-1"},
                            {"name": "search_guideline_rag", "args": {"query": "支原体肺炎 儿童 重症预警"}, "id": "tool-2"},
                        ],
                    )
                return AIMessage(content="")
            if operation == "chat":
                return SimpleNamespace(
                    content="根据指南，若呼吸急促或精神差，需要尽快线下评估[^1]。\n\n> ⚠️ 免责声明：以上内容仅供医学参考，不能替代执业医师面诊，不作为最终诊断依据。"
                )
            if operation == "reflection":
                return SimpleNamespace(content="PASS")
            raise AssertionError(f"unexpected operation: {operation}")

        with (
            patch("agent.graph._invoke_json_dict", side_effect=fake_json),
            patch("agent.graph._invoke_llm_with_retry", side_effect=fake_llm),
            patch(
                "agent.graph._perform_rag_search",
                return_value={
                    "context": "支原体肺炎重症预警包括呼吸急促、低氧和精神反应差。",
                    "citations": [
                        {
                            "title": "儿童肺炎支原体肺炎诊疗指南",
                            "chapter": "重症识别",
                            "content": "呼吸急促、精神反应差属于重症预警。",
                            "sourceType": "guideline",
                            "sourcePath": "guideline.pdf",
                            "score": 0.92,
                            "retrievalConfidence": "high",
                        }
                    ],
                },
            ),
        ):
            app = build_graph()
            result = app.invoke(
                {
                    "messages": ["宝宝咳嗽发烧，支原体肺炎有哪些重症预警？"],
                    "history": [],
                    "patient_profile": "",
                    "patient_context": {"ageMonths": 30},
                    "trace_id": "trace-mycoplasma",
                },
                config={"configurable": {"thread_id": "regression-1"}},
            )

        self.assertEqual(result["assessment"]["triageLevel"], "visit_within_24h")
        self.assertEqual(len(result["citations"]), 1)
        self.assertIn("[^1]", result["reply"])

    def test_hfmd_emergency_stops_before_normal_chat(self) -> None:
        app = build_graph()
        result = app.invoke(
            {
                "messages": ["孩子手足口病，高烧还抽搐怎么办"],
                "history": [],
                "patient_profile": "",
                "patient_context": {"ageMonths": 18},
                "trace_id": "trace-hfmd",
            },
            config={"configurable": {"thread_id": "regression-2"}},
        )

        self.assertEqual(result["assessment"]["triageLevel"], "emergency_now")
        self.assertIn("紧急就医提示", result["reply"])

    def test_growth_only_input_does_not_false_positive_emergency(self) -> None:
        def fake_json(prompt: str, trace_id: str):
            if "意图分类器" in prompt:
                return {"intent": "general", "confidence": 0.99, "needs_web_search": False, "search_query": ""}
            return None

        def fake_llm(llm, messages, trace_id: str, operation: str):
            if operation == "agentic_tools":
                return AIMessage(content="")
            if operation == "chat":
                return SimpleNamespace(
                    content="这更像是在补充生长记录，我先帮你记住月龄、体重和身高。\n\n> ⚠️ 免责声明：以上内容仅供医学参考，不能替代执业医师面诊，不作为最终诊断依据。"
                )
            raise AssertionError(f"unexpected operation: {operation}")

        with (
            patch("agent.graph._invoke_json_dict", side_effect=fake_json),
            patch("agent.graph._invoke_llm_with_retry", side_effect=fake_llm),
        ):
            app = build_graph()
            result = app.invoke(
                {
                    "messages": ["8个月，9.2kg，72cm"],
                    "history": [{"role": "user", "content": "7个月，8.8kg，71cm"}],
                    "patient_profile": "",
                    "patient_context": {},
                    "trace_id": "trace-growth",
                },
                config={"configurable": {"thread_id": "regression-3"}},
            )

        self.assertNotIn("紧急就医提示", result["reply"])
        self.assertEqual(result["intent"], "general")


if __name__ == "__main__":
    unittest.main()
