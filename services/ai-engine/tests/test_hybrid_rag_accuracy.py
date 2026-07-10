import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from agent.rag_milvus import PediatricRAG

class HybridRagAccuracyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 实例化 RAG
        cls.rag = PediatricRAG()

    def test_rag_search_returns_valid_citations(self) -> None:
        # 测试普通儿科问题查询
        query = "宝宝发热38.5度，精神萎靡，手足口有疱疹，怎么处理？"
        context, citations = self.rag.search(query, top_k=3)
        
        # 验证返回了 citations 列表和 context 文本
        self.assertIsInstance(citations, list)
        self.assertIsInstance(context, str)
        
        if citations:
            citation = citations[0]
            self.assertIn("title", citation)
            self.assertIn("content", citation)
            self.assertIn("score", citation)
            self.assertIn("retrievalConfidence", citation)
            # 确认分数值合法
            self.assertGreater(citation["score"], 0.0)

    def test_tokenize_method(self) -> None:
        # 测试单字清洗分词
        text = "手足口病！宝宝发热38.5度, 怎么办？"
        tokens = self.rag._tokenize(text)
        # 应该只保留中文字符和英文字母数字，且全部小写
        self.assertIn("手", tokens)
        self.assertIn("足", tokens)
        self.assertIn("口", tokens)
        self.assertIn("病", tokens)
        self.assertIn("3", tokens)
        self.assertIn("8", tokens)
        # 过滤了标点符号和空格
        self.assertNotIn("！", tokens)
        self.assertNotIn(",", tokens)
        self.assertNotIn("？", tokens)

if __name__ == "__main__":
    unittest.main()
