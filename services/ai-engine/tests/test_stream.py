import unittest
import asyncio
from agent.graph import build_graph

class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_astream_events(self) -> None:
        agent_app = build_graph()
        
        events = []
        async for event in agent_app.astream_events(
            {
                "messages": ["帮忙分析这份报告"], 
                "image_data": "private://example_upload.jpg",
                "history": [{"role": "assistant", "content": "你好"}]
            }, 
            config={"configurable": {"thread_id": "test-stream-thread"}},
            version="v2"
        ):
            events.append(event)
            
        self.assertGreater(len(events), 0)

if __name__ == "__main__":
    unittest.main()
