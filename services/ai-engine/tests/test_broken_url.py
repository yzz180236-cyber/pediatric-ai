import os
import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import get_llm_base_url, require_env

api_key = require_env("LLM_API_KEY")
base_url = get_llm_base_url()

llm = ChatOpenAI(
    api_key=api_key,
    base_url=base_url,
    model="qwen-vl-plus",
    temperature=0.7,
    max_tokens=512,
)

messages = [
    SystemMessage(content="你是一个专业、严谨且温柔的儿科AI医生助手。"),
    HumanMessage(content=[
        {"type": "text", "text": "帮忙分析一下这份报告"},
        {"type": "image_url", "image_url": {"url": "private://broken.jpg"}}
    ])
]

try:
    response = llm.invoke(messages)
    print("AI Response:", response.content)
except Exception as e:
    print("Error:", e)
