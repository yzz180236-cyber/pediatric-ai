import unittest
from langchain_openai import OpenAIEmbeddings
from config import get_llm_base_url, require_env

class EmbedTests(unittest.TestCase):
    def test_embeddings_generation(self) -> None:
        api_key = require_env("LLM_API_KEY")
        base_url = get_llm_base_url()

        embeddings = OpenAIEmbeddings(
            model="text-embedding-v3", 
            openai_api_key=api_key,
            openai_api_base=base_url
        )
        
        res = embeddings.embed_documents(["text1", "text2"])
        self.assertEqual(len(res), 2)
        self.assertEqual(len(res[0]), 1536)

if __name__ == "__main__":
    unittest.main()
