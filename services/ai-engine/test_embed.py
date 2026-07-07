import os
from langchain_openai import OpenAIEmbeddings
from config import get_llm_base_url, require_env

api_key = require_env("LLM_API_KEY")
base_url = get_llm_base_url()

embeddings = OpenAIEmbeddings(
    model="text-embedding-v3", 
    openai_api_key=api_key,
    openai_api_base=base_url
)

print(embeddings.embed_documents(["text1", "text2"]))
