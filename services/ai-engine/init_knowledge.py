import os
import time
from pymilvus import MilvusClient, DataType
from langchain_openai import OpenAIEmbeddings
from config import get_llm_base_url, require_env

MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530")
COLLECTION_NAME = "pediatric_guidelines"
DIMENSION = 1536  # text-embedding-v3 dimension

def init_milvus():
    print(f"Connecting to Milvus at {MILVUS_URI}...")
    client = MilvusClient(uri=MILVUS_URI)
    
    if client.has_collection(COLLECTION_NAME):
        print(f"Collection {COLLECTION_NAME} already exists. Dropping it for fresh init...")
        client.drop_collection(COLLECTION_NAME)
        
    print(f"Creating Collection {COLLECTION_NAME}...")
    # Schema 定义
    schema = MilvusClient.create_schema(
        auto_id=True,
        enable_dynamic_field=True,
    )
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=DIMENSION)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
    schema.add_field(field_name="source_title", datatype=DataType.VARCHAR, max_length=512)
    schema.add_field(field_name="source_chapter", datatype=DataType.VARCHAR, max_length=512)
    
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        metric_type="COSINE",
        index_type="HNSW",
        params={"M": 8, "efConstruction": 64}
    )
    
    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params
    )
    
    print("Collection created. Loading data from real documents...")
    
    data_dir = os.path.join(os.path.dirname(__file__), "data", "raw")
    if not os.path.exists(data_dir):
        print(f"Error: 找不到文档目录 {data_dir}。")
        print("严禁硬编码数据，请将真实的医学指南 TXT 文件放入该目录后再试。")
        return

    txt_files = [f for f in os.listdir(data_dir) if f.endswith(".txt")]
    if not txt_files:
        print(f"Error: 在 {data_dir} 中未找到任何 txt 文件。")
        print("请放入真实的医学文档后再执行入库。")
        return
        
    try:
        from langchain_community.document_loaders import TextLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        print("Error: 请先安装依赖：pip install langchain-community langchain-text-splitters")
        return

    docs = []
    for filename in txt_files:
        file_path = os.path.join(data_dir, filename)
        loader = TextLoader(file_path, encoding='utf-8')
        docs.extend(loader.load())
        
    print(f"Loaded {len(docs)} document(s). Splitting...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""]
    )
    chunks = text_splitter.split_documents(docs)
    print(f"Split into {len(chunks)} chunk(s).")
    
    api_key = require_env("LLM_API_KEY")
    base_url = get_llm_base_url()
    embeddings = OpenAIEmbeddings(
        model="text-embedding-v3", 
        openai_api_key=api_key,
        openai_api_base=base_url,
        tiktoken_enabled=False,
        check_embedding_ctx_length=False
    )
    
    print("Computing embeddings...")
    texts = [chunk.page_content for chunk in chunks]
    vectors = embeddings.embed_documents(texts)
    
    data = []
    for i, chunk in enumerate(chunks):
        # 从 metadata 中提取来源文件名作为 title
        source_file = os.path.basename(chunk.metadata.get("source", "未知来源"))
        data.append({
            "vector": vectors[i],
            "text": chunk.page_content,
            "source_title": source_file,
            "source_chapter": f"Chunk-{i}"
        })
        
    res = client.insert(collection_name=COLLECTION_NAME, data=data)
    print(f"Insert completed. IDs: {res}")
    
    client.load_collection(COLLECTION_NAME)
    print("Database is ready and loaded with REAL data.")

if __name__ == "__main__":
    init_milvus()
