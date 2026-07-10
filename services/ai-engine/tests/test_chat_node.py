import unittest
import sys
sys.path.append(".")
from agent.graph import chat_node

class ChatNodeTests(unittest.TestCase):
    def test_chat_node_execution(self) -> None:
        state = {
            "intent": "general",
            "messages": ["帮忙分析这份报告"],
            "history": [{"role": "assistant", "content": "你好"}],
            "image_data": "private://example_upload.jpg"
        }
        res = chat_node(state)
        self.assertIsNotNone(res)
        self.assertIn("reply", res)

if __name__ == "__main__":
    unittest.main()
