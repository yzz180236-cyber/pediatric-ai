import os
import base64
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from config import get_llm_base_url, require_env

api_key = require_env("LLM_API_KEY")
base_url = get_llm_base_url()
llm = ChatOpenAI(api_key=api_key, base_url=base_url, model="qwen-vl-plus")

filepath = "uploads/906f39bf6c29455fa3916271ea37ba7c.jpg"
with open(filepath, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()
    b64_url = f"data:image/jpeg;base64,{img_b64}"

messages = [
    AIMessage(content="你好，请问有什么可以帮您？"),
    HumanMessage(content=[
        {"type": "text", "text": "帮忙分析这份报告"},
        {"type": "image_url", "image_url": {"url": b64_url}}
    ]),
    HumanMessage(content=[
        {"type": "text", "text": "帮忙分析这份报告"},
        {"type": "image_url", "image_url": {"url": b64_url}}
    ])
]

try:
    print("Calling Qwen-VL-Plus with double messages...")
    res = llm.invoke(messages)
    print("Response:", res.content)
except Exception as e:
    print("Error:", e)
