import sys
import asyncio
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from agent.graph import build_graph

class HistoryOnlyTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_only_flow(self) -> None:
        agent_app = build_graph()
        # 严格对齐包含历史记录的输入格式
        payload = {
            "messages": ["帮忙分析这份报告"], 
            "image_data": None,
            "history": [
                {"role": "assistant", "content": "你好，我是智慧儿科 AI 助手，请问宝宝今天有什么不适？"},
                {"role": "user", "content": "帮忙分析这份报告", "image": "private://example_upload.jpg"}
            ]
        }
        
        events = []
        async for event in agent_app.astream_events(
            payload, 
            config={"configurable": {"thread_id": "test-history-thread"}},
            version="v2"
        ):
            events.append(event)
            
        self.assertGreater(len(events), 0)

if __name__ == "__main__":
    unittest.main()
