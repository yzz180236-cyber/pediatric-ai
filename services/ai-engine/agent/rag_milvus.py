import os
import logging
from pymilvus import MilvusClient, DataType
from langchain_openai import OpenAIEmbeddings
from typing import TypedDict, List, Tuple
from pathlib import Path
import json
import re
from config import get_llm_base_url, require_env
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

COLLECTION_NAME = "pediatric_guidelines"
MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530")
SIMILARITY_THRESHOLD = 0.70
SOURCE_INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "_source_index.json"

class Citation(TypedDict):
    title: str
    chapter: str
    content: str
    sourceType: str
    sourcePath: str
    score: float
    retrievalConfidence: str

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
        self.source_meta_map = self._load_source_meta_map()
        self._load_collection_if_exists()

    def _load_source_meta_map(self) -> dict[str, dict[str, str]]:
        try:
            if not SOURCE_INDEX_PATH.exists():
                return {}
            payload = json.loads(SOURCE_INDEX_PATH.read_text(encoding="utf-8"))
            items = payload.get("items", [])
            mapping: dict[str, dict[str, str]] = {}
            for item in items:
                local_path = str(item.get("localPath", ""))
                title = str(item.get("title", "")).strip()
                if not local_path or not title:
                    continue
                filename = Path(local_path).name
                mapping[filename] = {
                    "title": title,
                    "localPath": local_path,
                }
            return mapping
        except Exception:
            logger.exception("加载 source index 失败")
            return {}

    def _normalize_title(self, raw_title: str) -> str:
        return self.source_meta_map.get(raw_title, {}).get("title", raw_title)

    def _normalize_chapter(self, raw_title: str, raw_chapter: str) -> str:
        local_path = self.source_meta_map.get(raw_title, {}).get("localPath", "")
        if local_path.endswith(".txt") and raw_chapter.startswith("Page "):
            return "正文片段"
        return raw_chapter

    def _resolve_source_path(self, raw_title: str) -> str:
        return self.source_meta_map.get(raw_title, {}).get("localPath", raw_title)

    def _to_confidence_label(self, score: float) -> str:
        if score >= 0.9:
            return "high"
        if score >= 0.78:
            return "medium"
        return "low"

    def _tokenize(self, text: str) -> List[str]:
        """中文单字分词 + 保留英文字符/数字"""
        return [char for char in text.lower() if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", char)]

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

            # 1. 向量检索：召回稍微多一点的候选集 (例如 top_k * 4)
            query_vector = self.embeddings.embed_query(query)
            res = self.client.search(
                collection_name=COLLECTION_NAME,
                data=[query_vector],
                limit=max(top_k * 4, 20),
                output_fields=["text", "source_title", "source_chapter"],
                search_params={"metric_type": "COSINE"}
            )
            
            citations: List[Citation] = []
            if not res or len(res[0]) == 0:
                return ("暂无相关指南数据。", [])
                
            hits = res[0]
            
            # 2. 向量得分过滤 (余弦相似度必须 >= 阈值，防严重幻觉)
            valid_hits = [hit for hit in hits if hit.get("distance", 0) >= SIMILARITY_THRESHOLD]
            if not valid_hits:
                return ("暂无相关指南数据。", [])
                
            # 3. 构造本地 BM25 索引进行双路检索打分
            corpus = [
                self._tokenize(f"{hit['entity'].get('source_title', '')} {hit['entity'].get('text', '')}") 
                for hit in valid_hits
            ]
            bm25 = BM25Okapi(corpus)
            query_tokens = self._tokenize(query)
            bm25_scores = bm25.get_scores(query_tokens)
            
            # 4. 混合打分融合 (Hybrid Score)
            max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 else 0.0
            min_bm25 = min(bm25_scores) if len(bm25_scores) > 0 else 0.0
            bm25_range = max_bm25 - min_bm25
            
            ranked_hits: List[Tuple[float, Citation]] = []
            alpha = 0.6  # 向量分权重 0.6，BM25 分权重 0.4
            
            for idx, hit in enumerate(valid_hits):
                vector_score = float(hit.get("distance", 0))
                bm25_score = float(bm25_scores[idx])
                
                # 归一化 BM25 分数
                norm_bm25_score = (
                    (bm25_score - min_bm25) / bm25_range 
                    if bm25_range > 0 else 0.0
                )
                
                # 混合打分
                final_score = alpha * vector_score + (1.0 - alpha) * norm_bm25_score
                
                raw_title = hit["entity"].get("source_title", "未知来源")
                title = self._normalize_title(raw_title)
                content = hit["entity"].get("text", "")
                
                ranked_hits.append((final_score, {
                    "title": title,
                    "chapter": self._normalize_chapter(
                        raw_title,
                        hit["entity"].get("source_chapter", "未知章节"),
                    ),
                    "content": content,
                    "sourceType": "guideline",
                    "sourcePath": self._resolve_source_path(raw_title),
                    "score": round(final_score, 4),
                    "retrievalConfidence": self._to_confidence_label(final_score),
                }))
                
            # 5. 排序、去重与截断
            ranked_hits.sort(key=lambda x: x[0], reverse=True)
            
            seen_keys: set[str] = set()
            deduped: list[Citation] = []
            for _, citation in ranked_hits:
                dedupe_key = f"{citation['title']}::{citation['content'][:120]}"
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                deduped.append(citation)
                if len(deduped) >= top_k:
                    break
                    
            citations = deduped
            context = "\n\n".join([c["content"] for c in citations]) if citations else "暂无相关指南数据。"
            return (context, citations)
            
        except Exception:
            logger.exception("Milvus 检索失败")
            return ("知识检索暂时失败，请基于保守的儿科安全原则回答，并提示线下就医。", [])
