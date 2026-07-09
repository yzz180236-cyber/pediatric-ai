import os
import argparse
import logging
from pymilvus import MilvusClient, DataType
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import get_llm_base_url, require_env

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

COLLECTION_NAME = "pediatric_guidelines"
MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530")
EMBED_BATCH_SIZE = 10

def init_collection(client: MilvusClient, dim: int):
    if client.has_collection(COLLECTION_NAME):
        logger.info(f"Collection {COLLECTION_NAME} already exists.")
        return

    logger.info(f"Creating Collection {COLLECTION_NAME} with dimension {dim}...")
    schema = MilvusClient.create_schema(
        auto_id=True,
        enable_dynamic_field=True,
    )
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
    schema.add_field(field_name="source_title", datatype=DataType.VARCHAR, max_length=255)
    schema.add_field(field_name="source_chapter", datatype=DataType.VARCHAR, max_length=255)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        metric_type="COSINE",
        index_type="HNSW",
        index_name="vector_index",
        params={"M": 8, "efConstruction": 64}
    )

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params
    )
    logger.info("Collection created successfully.")

def process_file(file_path: str, client: MilvusClient, embeddings: OpenAIEmbeddings):
    logger.info(f"Processing file: {file_path}")
    
    if file_path.endswith('.pdf'):
        loader = PyPDFLoader(file_path)
    elif file_path.endswith('.txt'):
        loader = TextLoader(file_path, encoding='utf-8')
    else:
        logger.warning(f"Unsupported file format: {file_path}")
        return

    documents = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_documents(documents)
    logger.info(f"Splitted into {len(chunks)} chunks.")

    if not chunks:
        return

    # Extract source title from filename
    source_title = os.path.basename(file_path)

    insert_data = []
    texts = [chunk.page_content for chunk in chunks]
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch_texts = texts[i:i + EMBED_BATCH_SIZE]
        vectors.extend(embeddings.embed_documents(batch_texts))

    for i, chunk in enumerate(chunks):
        insert_data.append({
            "vector": vectors[i],
            "text": chunk.page_content,
            "source_title": source_title,
            "source_chapter": f"Page {chunk.metadata.get('page', 0) + 1}"
        })

    # Batch insert to prevent payload too large
    batch_size = 100
    for i in range(0, len(insert_data), batch_size):
        batch = insert_data[i:i + batch_size]
        res = client.insert(
            collection_name=COLLECTION_NAME,
            data=batch
        )
        logger.info(f"Inserted batch {i//batch_size + 1}: {res}")

def main():
    parser = argparse.ArgumentParser(description="Pediatric AI Knowledge Base Import Tool")
    parser.add_argument("--dir", type=str, required=True, help="Directory containing PDF or TXT guidelines.")
    args = parser.parse_args()

    api_key = require_env("LLM_API_KEY")
    base_url = get_llm_base_url()
    
    embeddings = OpenAIEmbeddings(
        model="text-embedding-v3", 
        openai_api_key=api_key,
        openai_api_base=base_url,
        tiktoken_enabled=False,
        check_embedding_ctx_length=False
    )
    
    client = MilvusClient(uri=MILVUS_URI)
    
    # 阿里云 dashscope embedding-v3 默认维数为 1024
    init_collection(client, dim=1024)

    target_dir = args.dir
    if not os.path.exists(target_dir):
        logger.error(f"Directory not found: {target_dir}")
        return

    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.endswith(('.pdf', '.txt')):
                process_file(os.path.join(root, file), client, embeddings)
                
    logger.info("Knowledge base import completed.")

if __name__ == "__main__":
    main()
