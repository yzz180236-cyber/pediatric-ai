import sys
import asyncio
import base64
sys.path.append(".")
from agent.graph import build_graph

agent_app = build_graph()

async def main():
    # Construct exact payload from user's screenshot
    payload = {
        "messages": ["帮忙分析这份报告"], 
        "image_data": None,
        "history": [
            {"role": "assistant", "content": "你好，我是智慧儿科 AI 助手，请问宝宝今天有什么不适？"},
            {"role": "user", "content": "帮忙分析这份报告", "image": "private://example_upload.jpg"}
        ]
    }
    
    async for event in agent_app.astream_events(payload, version="v2"):
        if event["event"] == "on_chat_model_stream":
            if "chunk" in event["data"]:
                content = event["data"]["chunk"].content
                if content:
                    print(content, end="", flush=True)

asyncio.run(main())
print("\nDone")
