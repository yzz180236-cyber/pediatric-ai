import os
from pathlib import Path
from typing import Iterable, List

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from pymilvus import DataType, MilvusClient

from config import get_llm_base_url, require_env

RAW_DATA_DIR = Path(__file__).resolve().parent / "data" / "raw"
COLLECTION_NAME = "pediatric_guidelines"
MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530")
EMBED_BATCH_SIZE = 20
INSERT_BATCH_SIZE = 100


def get_embeddings() -> OpenAIEmbeddings:
    api_key = require_env("LLM_API_KEY")
    base_url = get_llm_base_url()
    return OpenAIEmbeddings(
        model="text-embedding-v3",
        openai_api_key=api_key,
        openai_api_base=base_url,
        tiktoken_enabled=False,
        check_embedding_ctx_length=False,
    )


def discover_source_files(raw_dir: Path) -> List[Path]:
    files = [path for path in raw_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".pdf", ".txt"}]
    return sorted(files)


def load_documents(file_path: Path) -> List[Document]:
    if file_path.suffix.lower() == ".pdf":
        return PyPDFLoader(str(file_path)).load()
    return TextLoader(str(file_path), encoding="utf-8").load()


def split_documents(documents: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""],
    )
    return splitter.split_documents(documents)


def ensure_collection(client: MilvusClient, vector_dim: int) -> None:
    if client.has_collection(COLLECTION_NAME):
        print(f"Collection {COLLECTION_NAME} already exists. Dropping it for fresh rebuild...")
        client.drop_collection(COLLECTION_NAME)

    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=vector_dim)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
    schema.add_field(field_name="source_title", datatype=DataType.VARCHAR, max_length=512)
    schema.add_field(field_name="source_chapter", datatype=DataType.VARCHAR, max_length=512)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        metric_type="COSINE",
        index_type="HNSW",
        params={"M": 8, "efConstruction": 64},
    )

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
    )


def build_insert_rows(chunks: List[Document], vectors: List[List[float]]) -> List[dict]:
    rows: List[dict] = []
    for index, chunk in enumerate(chunks):
        source_path = Path(str(chunk.metadata.get("source", "未知来源")))
        page = chunk.metadata.get("page")
        chapter = f"Page {int(page) + 1}" if isinstance(page, int) else "正文片段"
        rows.append(
            {
                "vector": vectors[index],
                "text": chunk.page_content,
                "source_title": source_path.name,
                "source_chapter": chapter,
            }
        )
    return rows


def batch_iter(items: List[dict], batch_size: int) -> Iterable[List[dict]]:
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def ingest_data() -> None:
    print("========== 智慧儿科 RAG 灌库工具 ==========")
    print(f"Milvus URI: {MILVUS_URI}")
    print(f"扫描目录: {RAW_DATA_DIR}")

    if not RAW_DATA_DIR.exists():
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        print("未找到 data/raw 目录，已自动创建。请放入真实 PDF/TXT 医学资料后重试。")
        return

    source_files = discover_source_files(RAW_DATA_DIR)
    if not source_files:
        print("未发现任何 .pdf 或 .txt 来源文件，拒绝使用伪造知识片段灌库。")
        return

    all_documents: List[Document] = []
    for file_path in source_files:
        print(f"加载来源文件: {file_path.relative_to(RAW_DATA_DIR)}")
        all_documents.extend(load_documents(file_path))

    if not all_documents:
        print("来源文件已找到，但未解析出可入库文本。")
        return

    chunks = split_documents(all_documents)
    if not chunks:
        print("文档解析完成，但切片结果为空。")
        return

    embeddings = get_embeddings()
    probe_vector = embeddings.embed_query("儿科临床指南")
    vector_dim = len(probe_vector)
    print(f"Embedding 维度探测结果: {vector_dim}")

    client = MilvusClient(uri=MILVUS_URI)
    ensure_collection(client, vector_dim)

    texts = [chunk.page_content for chunk in chunks]
    vectors: List[List[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch_texts = texts[start:start + EMBED_BATCH_SIZE]
        vectors.extend(embeddings.embed_documents(batch_texts))
        print(f"Embedding 进度: {min(start + EMBED_BATCH_SIZE, len(texts))}/{len(texts)}")

    rows = build_insert_rows(chunks, vectors)
    inserted = 0
    for batch in batch_iter(rows, INSERT_BATCH_SIZE):
        result = client.insert(collection_name=COLLECTION_NAME, data=batch)
        inserted += int(result.get("insert_count", len(batch)))
    client.load_collection(COLLECTION_NAME)

    print(f"灌库完成，已写入 {inserted} 条切片。")
    print("现在可以使用 AI Engine 进行高置信度指南检索验证。")


if __name__ == "__main__":
    ingest_data()
