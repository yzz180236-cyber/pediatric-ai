import os
import glob
import sys

# 将父级目录加入 path，以便可以读取环境变量等配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient, DataType
from config import get_llm_base_url, require_env

RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), '../data/raw')
DB_PATH = os.path.join(os.path.dirname(__file__), '../milvus_demo.db')
COLLECTION_NAME = "pediatric_guidelines"

def get_embeddings():
    api_key = require_env("LLM_API_KEY")
    base_url = get_llm_base_url()
    return OpenAIEmbeddings(
        model="text-embedding-v3", 
        openai_api_key=api_key,
        openai_api_base=base_url,
        tiktoken_enabled=False,
        check_embedding_ctx_length=False
    )

def ensure_collection(client):
    if not client.has_collection(COLLECTION_NAME):
        print(f"正在创建向量集合 {COLLECTION_NAME}...")
        schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=True)
        # 建立 Schema
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=2000)
        schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=500)
        
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="vector", metric_type="COSINE", index_type="FLAT")
        
        client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params
        )

def ingest_data():
    print(f"========== 智慧儿科 RAG 自动化灌库工具 ==========")
    print(f"扫描数据目录: {os.path.abspath(RAW_DATA_DIR)}")
    if not os.path.exists(RAW_DATA_DIR):
        os.makedirs(RAW_DATA_DIR)
        print("💡 目录不存在，已自动为您创建。")
        print("👉 请将您的医疗指南文档 (.pdf 或 .txt) 放入 data/raw 目录后，再重新运行此脚本。")
        return

    documents = []
    
    # 1. 加载 PDF 文件
    for filepath in glob.glob(os.path.join(RAW_DATA_DIR, "*.pdf")):
        print(f"📄 加载 PDF: {os.path.basename(filepath)}")
        loader = PyPDFLoader(filepath)
        documents.extend(loader.load())
        
    # 2. 加载 TXT 文件
    for filepath in glob.glob(os.path.join(RAW_DATA_DIR, "*.txt")):
        print(f"📝 加载 TXT: {os.path.basename(filepath)}")
        loader = TextLoader(filepath, encoding='utf-8')
        documents.extend(loader.load())

    if not documents:
        print("❌ 未在目录中找到任何文档，请确保放入了合法的 .pdf 或 .txt 文件。")
        return

    print(f"✅ 共解析得到 {len(documents)} 页/篇原始文档内容。")
    print("⏳ 正在进行智能文本切分...")
    
    # 3. 智能分块策略：每块 500 字符，保留 50 字符上下文重叠
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"✅ 切分完成，共产生 {len(chunks)} 个文本块 (Chunks)。")

    # 4. 初始化向量库
    client = MilvusClient(DB_PATH)
    ensure_collection(client)
    
    embeddings = get_embeddings()
    
    print("🚀 正在调用大模型进行文本向量化 (Embedding) 并写入本地数据库...")
    
    # 5. 分批嵌入与入库 (每批 50 条，防止超频截断)
    batch_size = 50
    total_inserted = 0
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i+batch_size]
        texts = [chunk.page_content for chunk in batch_chunks]
        sources = [chunk.metadata.get("source", "Unknown") for chunk in batch_chunks]
        
        try:
            # 获取向量
            vectors = embeddings.embed_documents(texts)
            
            # 组装数据
            data = [
                {"vector": vectors[j], "text": texts[j], "source": sources[j]} 
                for j in range(len(batch_chunks))
            ]
            
            res = client.insert(collection_name=COLLECTION_NAME, data=data)
            total_inserted += res.get('insert_count', len(batch_chunks))
            print(f"  -> 进度: {min(i+batch_size, len(chunks))}/{len(chunks)} 块处理完成...")
        except Exception as e:
            print(f"❌ 批次入库失败: {e}")

    print(f"🎉 灌库大功告成！本次成功存入 {total_inserted} 条知识库切片。")
    print("💡 您现在可以启动后端服务，在聊天中提出专业问题以测试 RAG 检索效果了！")

if __name__ == "__main__":
    ingest_data()
