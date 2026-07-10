import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from agent.graph import calculate_pews, slot_filling_node
from agent.state import GraphState

class PearsEvaluationTests(unittest.TestCase):
    def test_calculate_pews_normal(self) -> None:
        slots = {
            "behavior": "精神状态良好，活泼好动",
            "cardiovascular": "皮肤红润",
            "respiratory": "呼吸平稳"
        }
        score, details = calculate_pews(slots)
        self.assertEqual(score, 0)
        self.assertEqual(details["behavior"], 0)
        self.assertEqual(details["cardiovascular"], 0)
        self.assertEqual(details["respiratory"], 0)

    def test_calculate_pews_mild(self) -> None:
        slots = {
            "behavior": "精神萎靡，爱哭闹",
            "cardiovascular": "面色苍白",
            "respiratory": "呼吸稍快，有气促"
        }
        score, details = calculate_pews(slots)
        self.assertEqual(score, 3)  # 1 + 1 + 1 = 3
        self.assertEqual(details["behavior"], 1)
        self.assertEqual(details["cardiovascular"], 1)
        self.assertEqual(details["respiratory"], 1)

    def test_calculate_pews_severe_individual(self) -> None:
        slots = {
            "behavior": "宝宝目前昏睡，唤不醒了",
            "cardiovascular": "手脚有一点凉",
            "respiratory": "呼吸平稳"
        }
        score, details = calculate_pews(slots)
        self.assertEqual(score, 5)  # 3 (behavior) + 2 (cv) + 0 (resp) = 5
        self.assertEqual(details["behavior"], 3)
        self.assertEqual(details["cardiovascular"], 2)

    def test_calculate_pews_with_negatives(self) -> None:
        slots = {
            "behavior": "宝宝今天精神很好，没有萎靡，没有烦躁",
            "cardiovascular": "面色红润，没有苍白",
            "respiratory": "呼吸非常平稳，未见呻吟，也未见呼吸急促，没有三凹征"
        }
        score, details = calculate_pews(slots)
        self.assertEqual(score, 0)
        self.assertEqual(details["behavior"], 0)
        self.assertEqual(details["cardiovascular"], 0)
        self.assertEqual(details["respiratory"], 0)

    def test_slot_filling_node_triggers_pews_emergency(self) -> None:
        state: GraphState = {
            "trace_id": "test-pews-emergency",
            "messages": ["宝宝高烧，目前神志不清，呼吸凹陷得很厉害，一直呻吟"],
            "slots": {
                "behavior": "神志不清",
                "respiratory": "吸气三凹征明显，且一直呻吟"
            },
            "patient_context": {"ageMonths": 18}
        }
        
        # 运行门面节点
        output = slot_filling_node(state)
        
        # 验证返回结构
        slots = output.get("slots", {})
        self.assertEqual(slots.get("status"), "missing")  # 强制 missing 确保路由到 END
        self.assertIn("pews_score", output)
        self.assertGreaterEqual(output["pews_score"], 5)
        
        # 验证分诊 assessment 与回复
        assessment = output.get("assessment", {})
        self.assertEqual(assessment.get("triageLevel"), "emergency_now")
        self.assertIn("意识不清或精神极度萎靡", assessment.get("triageReason", ""))
        self.assertIn("立即急诊", output.get("reply", ""))

if __name__ == "__main__":
    unittest.main()
