import os
import logging
from pymilvus import MilvusClient, DataType
from langchain_openai import OpenAIEmbeddings
from typing import TypedDict, List, Tuple
from config import get_llm_base_url, require_env

logger = logging.getLogger(__name__)

COLLECTION_NAME = "pediatric_guidelines"
MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530")
SIMILARITY_THRESHOLD = 0.70

class Citation(TypedDict):
    title: str
    chapter: str
    content: str
    sourceType: str

class PediatricRAG:
    def __init__(self):
        api_key = require_env("LLM_API_KEY")
        base_url = get_llm_base_url()
        
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-v3", 
            openai_api_key=api_key,
            openai_api_base=base_url,
            tiktoken_enabled=False,
            check_embedding_ctx_length=False
        )
        
        # 使用 URI 替代本地文件
        self.client = MilvusClient(uri=MILVUS_URI)
        self._load_collection_if_exists()

    def _load_collection_if_exists(self):
        """如果集合存在，则加载到内存中准备检索"""
        try:
            if self.client.has_collection(COLLECTION_NAME):
                self.client.load_collection(COLLECTION_NAME)
            else:
                logger.warning(f"Warning: Collection {COLLECTION_NAME} 不存在。请先运行数据灌库脚本。")
        except Exception as e:
            logger.error(f"RAG Collection Load Error: {e}")

    def search(self, query: str, top_k: int = 5) -> Tuple[str, List[Citation]]:
        try:
            if not self.client.has_collection(COLLECTION_NAME):
                return ("知识库尚未建立，请先运行数据预热入库脚本。", [])

            query_vector = self.embeddings.embed_query(query)
            res = self.client.search(
                collection_name=COLLECTION_NAME,
                data=[query_vector],
                limit=top_k,
                output_fields=["text", "source_title", "source_chapter"],
                search_params={"metric_type": "COSINE"}
            )
            
            citations: List[Citation] = []
            if res and len(res[0]) > 0:
                for hit in res[0]:
                    if hit.get("distance", 0) < SIMILARITY_THRESHOLD:
                        continue
                    citations.append({
                        "title": hit["entity"].get("source_title", "未知来源"),
                        "chapter": hit["entity"].get("source_chapter", "未知章节"),
                        "content": hit["entity"].get("text", ""),
                        "sourceType": "guideline",
                    })
                    
            context = "\n\n".join([c["content"] for c in citations]) if citations else "暂无相关指南数据。"
            return (context, citations)
            
        except Exception as e:
            logger.exception("Milvus 检索失败")
            return (f"检索失败: {str(e)}", [])
