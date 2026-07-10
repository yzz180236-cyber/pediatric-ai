import sys
sys.path.append(".")
from agent.graph import chat_node
from agent.state import GraphState

state = {
    "intent": "general",
    "messages": ["帮忙分析这份报告"],
    "history": [{"role": "assistant", "content": "你好"}],
    "image_data": "private://example_upload.jpg"
}

res = chat_node(state)
print("Response:", res)
