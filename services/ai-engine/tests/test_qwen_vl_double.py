import unittest
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from config import get_llm_base_url, require_env

class QwenVlDoubleTests(unittest.TestCase):
    def test_qwen_vl_double_messages(self) -> None:
        api_key = require_env("LLM_API_KEY")
        base_url = get_llm_base_url()
        llm = ChatOpenAI(api_key=api_key, base_url=base_url, model="qwen-vl-plus")

        b64_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD"
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
        
        res = llm.invoke(messages)
        self.assertIsNotNone(res.content)
        self.assertIn("李宏状", res.content)

if __name__ == "__main__":
    unittest.main()
