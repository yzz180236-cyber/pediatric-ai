# AI Engine

本服务本地开发只读取：

- `services/ai-engine/.env`

模板文件：

- `services/ai-engine/.env.example`

## 最小必填配置

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL_NAME`
- `LLM_VISION_MODEL_NAME`
- `MILVUS_URI`

## 可选观测配置

- `LANGFUSE_ENABLED=true`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST`
- `LANGGRAPH_POSTGRES_DSN`

## 本地启动

```bash
cd services/ai-engine
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
