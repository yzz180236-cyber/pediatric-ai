import sys
import asyncio
import json
sys.path.append(".")
from agent.graph import build_graph

agent_app = build_graph()

async def main():
    async for event in agent_app.astream_events({
        "messages": ["帮忙分析这份报告"], 
        "image_data": "private://example_upload.jpg",
        "history": [{"role": "assistant", "content": "你好"}]
    }, version="v2"):
        if event["event"] == "on_chat_model_stream":
            if "chunk" in event["data"]:
                content = event["data"]["chunk"].content
                if content:
                    print(content, end="", flush=True)

asyncio.run(main())
print("\nDone")
