import os
import mimetypes

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
import uuid
from prometheus_client import make_asgi_app
from agent.graph import build_graph

app = FastAPI(title="智慧儿科 AI Engine (LangGraph P1)")
PRIVATE_UPLOAD_DIR = "private_uploads"
INTERNAL_TOKEN = os.environ.get("AI_ENGINE_INTERNAL_TOKEN", "dev-internal-token")

# 添加 Prometheus 监控指标端点
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化私有影像存储目录
os.makedirs(PRIVATE_UPLOAD_DIR, exist_ok=True)

# 在启动时编译构建多智能体图结构
agent_app = build_graph()

from typing import List, Dict, Any
from pydantic import BaseModel

class ChatRequest(BaseModel):
    sessionId: str | None = None
    message: str
    image: str | None = None
    history: List[Dict[str, Any]] = []
    # 患儿档案摘要（由 BFF 读取后注入，包含月龄/过敏史/近期病史等）
    patientProfile: str | None = None

def verify_internal_token(request: Request) -> None:
    token = request.headers.get("x-internal-token")
    if token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid internal token")


@app.post("/internal/upload")
async def upload_image_internal(request: Request, userId: str = Form(...), file: UploadFile = File(...)):
    verify_internal_token(request)

    ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'jpg'
    filename = f"{userId}_{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(PRIVATE_UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"storageKey": filename}


@app.get("/internal/files/{storage_key}")
async def get_image_internal(storage_key: str, request: Request):
    verify_internal_token(request)
    filepath = os.path.join(PRIVATE_UPLOAD_DIR, storage_key)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    mime_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
    with open(filepath, "rb") as f:
        return Response(content=f.read(), media_type=mime_type)

@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    result = agent_app.invoke({
        "messages": [request.message], 
        "image_data": request.image,
        "history": request.history,
        "patient_profile": request.patientProfile or ""
    }, config={"configurable": {"thread_id": request.sessionId or "default"}})
    
    return {
        "reply": result["reply"],
        "intent": result["intent"],
        "status": "success"
    }

import json
from fastapi.responses import StreamingResponse

@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    async def generate():
        has_streamed_chunks = False
        final_reply = ""
        
        current_node = ""
        async for event in agent_app.astream_events({
            "messages": [request.message], 
            "image_data": request.image,
            "history": request.history,
            "patient_profile": request.patientProfile or ""
        }, version="v2", config={"configurable": {"thread_id": request.sessionId or "default"}}):
            # 监听节点结束事件以提取详细输出
            if event["event"] == "on_chain_end":
                node_name = event["name"]
                output = event["data"].get("output", {})
                
                # 记录图中产生的任何 reply，以备不时之需
                if isinstance(output, dict) and "reply" in output:
                    final_reply = output["reply"]
                
                if node_name == "rag":
                    citations = output.get("citations", [])
                    if citations:
                        # 提前下发来源
                        yield f"data: {json.dumps({'citations': citations}, ensure_ascii=False)}\n\n"
                        titles = [c['title'] for c in citations]
                        titles_str = "、".join(titles)
                        yield f"data: {json.dumps({'thought': f'检索完毕，参考文献: {titles_str}'}, ensure_ascii=False)}\n\n"
                        
                if node_name == "router":
                    intent = output.get("intent", "")
                    if intent:
                        yield f"data: {json.dumps({'thought': f'分析结果：意图归类为 [{intent}]'}, ensure_ascii=False)}\n\n"
                        
                if node_name == "slot_filling":
                    slots = output.get("slots", {})
                    status = slots.get("status", "")
                    if status == "missing":
                        yield f"data: {json.dumps({'thought': '病情特征缺失，需要主动追问家长...'}, ensure_ascii=False)}\n\n"
                        # 下发结构化追问卡片，触发前端 FollowupCard 渲染
                        followup_card = output.get("followup_card")
                        if followup_card:
                            yield f"data: {json.dumps({'followup_card': followup_card}, ensure_ascii=False)}\n\n"
                    elif status == "filled":
                        yield f"data: {json.dumps({'thought': '关键体征齐全，准备进行评估...'}, ensure_ascii=False)}\n\n"

                        
                if node_name == "reflection":
                    fb = output.get("reflection_feedback", "")
                    if fb == "PASS":
                        yield f"data: {json.dumps({'thought': '安全合规复核：通过 (无违禁/超纲回答)'}, ensure_ascii=False)}\n\n"
                    elif fb:
                        yield f"data: {json.dumps({'thought': f'安全合规拦截：触发医疗红线，正在重新生成...'}, ensure_ascii=False)}\n\n"
                        
                if node_name == "ocr":
                    ocr_res = output.get("ocr_result", {})
                    if ocr_res:
                        yield f"data: {json.dumps({'ocr_result': ocr_res}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'thought': '图像解析完成：已成功提取出化验单上的各体征指标。'}, ensure_ascii=False)}\n\n"

            if event["event"] == "on_chain_start":
                node_name = event["name"]
                if node_name in ["router", "slot_filling", "ocr", "rag", "reflection", "chat", "web_search"]:
                    current_node = node_name
                
                # 尝试从输入流中获取当前的状态字典，以实现更动态的“思考”内容
                state = event.get("data", {}).get("input", {})
                is_state_dict = isinstance(state, dict)
                
                if node_name == "router":
                    yield f"data: {json.dumps({'thought': '接收到请求，正在分析您的意图类型...'}, ensure_ascii=False)}\n\n"
                    
                if node_name == "slot_filling":
                    yield f"data: {json.dumps({'thought': '进入临床核查，正在比对缺失的医学体征...'}, ensure_ascii=False)}\n\n"
                    
                if node_name == "rag":
                    # 动态读取它将要去检索什么
                    if is_state_dict:
                        slots = state.get("slots", {})
                        query_term = slots.get("symptom") or "相关医学指南"
                    else:
                        query_term = "相关医学指南"
                    # 由于 query_term 可能比较长或者是一个大句子，可以截断一下
                    display_term = str(query_term)[:15] + "..." if len(str(query_term)) > 15 else str(query_term)
                    yield f"data: {json.dumps({'thought': f'正在医学知识库中检索关于「{display_term}」的临床路径...'}, ensure_ascii=False)}\n\n"
                    
                if node_name == "reflection":
                    yield f"data: {json.dumps({'thought': '草稿生成完毕，正在进行严苛的医疗安全红线复核...'}, ensure_ascii=False)}\n\n"
                    
                if node_name == "web_search":
                    try:
                        if is_state_dict:
                            query = state.get("search_query", "相关资讯")
                        else:
                            query = "相关资讯"
                        yield f"data: {json.dumps({'thought': f'🌐 正在联网搜索最新资讯: {query}'}, ensure_ascii=False)}\n\n"
                    except Exception:
                        yield f"data: {json.dumps({'thought': '🌐 正在联网搜索...'}, ensure_ascii=False)}\n\n"
                    
            if event["event"] == "on_chat_model_stream":
                if current_node != "chat":
                    continue
                
                chunk = event["data"]["chunk"].content
                if chunk:
                    has_streamed_chunks = True
                    # 使用 Server-Sent Events (SSE) 格式发送数据
                    yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
        
        # 循环结束后的终极兜底：如果一次流输出都没有过，说明是视觉模型之类不支持流的，我们在这里一次性推送它
        if final_reply and not has_streamed_chunks:
            yield f"data: {json.dumps({'chunk': final_reply}, ensure_ascii=False)}\n\n"

        # 结束标记
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
