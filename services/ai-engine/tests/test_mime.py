import unittest
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from config import get_llm_base_url, require_env

class QwenMimeTests(unittest.TestCase):
    def test_qwen_vl_mime(self) -> None:
        api_key = require_env("LLM_API_KEY")
        base_url = get_llm_base_url()
        llm = ChatOpenAI(api_key=api_key, base_url=base_url, model="qwen-vl-plus")

        # 使用虚拟的 base64 图像进行离线测试
        b64_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD"
        messages = [
            HumanMessage(content=[
                {"type": "text", "text": "描述一下这张图片"},
                {"type": "image_url", "image_url": {"url": b64_url}}
            ])
        ]
        
        res = llm.invoke(messages)
        self.assertIsNotNone(res.content)
        self.assertIn("李宏状", res.content)

if __name__ == "__main__":
    unittest.main()
