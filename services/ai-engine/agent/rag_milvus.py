import os
import logging
from pymilvus import MilvusClient, DataType
from langchain_openai import OpenAIEmbeddings
from typing import TypedDict, List, Tuple
from pathlib import Path
import json
import re
from config import get_llm_base_url, require_env

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

    def _char_overlap_score(self, query: str, text: str) -> float:
        query_chars = {char for char in query if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", char)}
        text_chars = {char for char in text if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", char)}
        if not query_chars or not text_chars:
            return 0.0
        return len(query_chars & text_chars) / len(query_chars)

    def _extract_query_terms(self, query: str) -> list[str]:
        lexicon = [
            "支原体", "手足口病", "百日咳", "麻疹", "风疹", "流感", "腹泻", "肺炎",
            "儿童", "婴幼儿", "呼吸道", "重症", "预警", "健康管理", "免疫规划",
            "慢阻肺", "人偏肺病毒", "hMPV", "社区获得性肺炎", "0～6岁", "0-6岁",
        ]
        return [term for term in lexicon if term.lower() in query.lower()]

    def _extract_primary_disease_terms(self, query: str) -> list[str]:
        disease_terms = [
            "支原体", "手足口病", "百日咳", "麻疹", "风疹", "流感",
            "人偏肺病毒", "hMPV", "腹泻", "肺炎",
        ]
        return [term for term in disease_terms if term.lower() in query.lower()]

    def _extract_strict_disease_terms(self, query: str) -> list[str]:
        strict_terms = [
            "支原体", "手足口病", "百日咳", "麻疹", "风疹", "流感", "人偏肺病毒", "hMPV",
        ]
        return [term for term in strict_terms if term.lower() in query.lower()]

    def _keyword_alignment_score(self, query: str, title: str, content: str) -> float:
        terms = self._extract_query_terms(query)
        if not terms:
            return 0.0
        haystack = f"{title}\n{content[:500]}".lower()
        matched = 0
        strong_mismatch = 0
        for term in terms:
            if term.lower() in haystack:
                matched += 1
            elif len(term) >= 3:
                strong_mismatch += 1
        return matched * 0.12 - strong_mismatch * 0.08

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
                limit=max(top_k * 4, 12),
                output_fields=["text", "source_title", "source_chapter"],
                search_params={"metric_type": "COSINE"}
            )
            
            citations: List[Citation] = []
            ranked_hits: list[tuple[float, Citation]] = []
            if res and len(res[0]) > 0:
                for hit in res[0]:
                    if hit.get("distance", 0) < SIMILARITY_THRESHOLD:
                        continue
                    raw_title = hit["entity"].get("source_title", "未知来源")
                    title = self._normalize_title(raw_title)
                    content = hit["entity"].get("text", "")
                    lexical_score = (
                        self._char_overlap_score(query, title) * 0.7
                        + self._char_overlap_score(query, content[:300]) * 0.3
                    )
                    keyword_score = self._keyword_alignment_score(query, title, content)
                    final_score = float(hit.get("distance", 0)) + lexical_score + keyword_score
                    ranked_hits.append((final_score, {
                        "title": title,
                        "chapter": self._normalize_chapter(
                            raw_title,
                            hit["entity"].get("source_chapter", "未知章节"),
                        ),
                        "content": content,
                        "sourceType": "guideline",
                    }))
            if ranked_hits:
                ranked_hits.sort(key=lambda item: item[0], reverse=True)
                primary_terms = self._extract_primary_disease_terms(query)
                strict_terms = self._extract_strict_disease_terms(query)
                if strict_terms:
                    strict_hits = []
                    non_strict_hits = []
                    for score, citation in ranked_hits:
                        haystack = f"{citation['title']}\n{citation['content'][:400]}".lower()
                        if all(term.lower() in haystack for term in strict_terms):
                            strict_hits.append((score, citation))
                        else:
                            non_strict_hits.append((score, citation))
                    if len(strict_hits) >= 3:
                        ranked_hits = strict_hits + non_strict_hits
                if primary_terms:
                    matched_hits = []
                    fallback_hits = []
                    for score, citation in ranked_hits:
                        haystack = f"{citation['title']}\n{citation['content'][:400]}".lower()
                        if any(term.lower() in haystack for term in primary_terms):
                            matched_hits.append((score, citation))
                        else:
                            fallback_hits.append((score, citation))
                    ranked_hits = matched_hits + fallback_hits
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
            
        except Exception as e:
            logger.exception("Milvus 检索失败")
            return (f"检索失败: {str(e)}", [])
