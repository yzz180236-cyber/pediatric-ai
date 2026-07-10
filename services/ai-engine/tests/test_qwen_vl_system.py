import unittest
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import get_llm_base_url, require_env

class QwenVlSystemTests(unittest.TestCase):
    def test_qwen_vl_system_prompt(self) -> None:
        api_key = require_env("LLM_API_KEY")
        base_url = get_llm_base_url()
        llm = ChatOpenAI(api_key=api_key, base_url=base_url, model="qwen-vl-plus")

        b64_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD"
        system_prompt = "你是一个亲切的智慧儿科平台小助手。当前时间是：2026年07月02日 17:42:00 (北京时间)。请以温柔的语气和家长进行日常沟通。"
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=[
                {"type": "text", "text": "帮忙分析这份报告"},
                {"type": "image_url", "image_url": {"url": b64_url}}
            ])
        ]
        
        res = llm.invoke(messages)
        self.assertIsNotNone(res.content)
        self.assertIn("李宏状", res.content)

if __name__ == "__main__":
    unittest.main()
