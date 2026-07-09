import os
import mimetypes
import uuid

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from agent.graph import build_graph
from observability import build_langfuse_run_config, flush_langfuse

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
    traceId: str | None = None
    # 患儿档案摘要（由 BFF 读取后注入，包含月龄/过敏史/近期病史等）
    patientProfile: str | None = None
    patientContext: Dict[str, Any] | None = None

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
    trace_id = request.traceId or uuid.uuid4().hex
    session_id = request.sessionId or "default"
    config = {
        "configurable": {"thread_id": session_id},
        **build_langfuse_run_config(trace_id, session_id, "api/chat"),
    }
    try:
        result = agent_app.invoke({
            "messages": [request.message], 
            "image_data": request.image,
            "history": request.history,
            "patient_profile": request.patientProfile or "",
            "patient_context": request.patientContext or {},
            "trace_id": trace_id,
        }, config=config)
        
        return {
            "reply": result["reply"],
            "intent": result["intent"],
            "status": "success",
            "traceId": trace_id,
        }
    finally:
        flush_langfuse()

import json
from fastapi.responses import StreamingResponse

@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    trace_id = request.traceId or uuid.uuid4().hex
    session_id = request.sessionId or "default"
    async def generate():
        has_streamed_chunks = False
        final_reply = ""
        emitted_citations = False
        emitted_assessment = False
        config = {
            "configurable": {"thread_id": session_id},
            **build_langfuse_run_config(trace_id, session_id, "api/chat/stream"),
        }
        
        current_node = ""
        try:
            async for event in agent_app.astream_events({
                "messages": [request.message], 
                "image_data": request.image,
                "history": request.history,
                "patient_profile": request.patientProfile or "",
                "patient_context": request.patientContext or {},
                "trace_id": trace_id,
            }, version="v2", config=config):
                # 监听节点结束事件以提取详细输出
                if event["event"] == "on_chain_end":
                    node_name = event["name"]
                    output = event["data"].get("output", {})
                    
                    # 记录图中产生的任何 reply，以备不时之需
                    if isinstance(output, dict) and "reply" in output:
                        final_reply = output["reply"]

                    if isinstance(output, dict) and output.get("assessment") and not emitted_assessment:
                        emitted_assessment = True
                        yield f"data: {json.dumps({'assessment': output['assessment']}, ensure_ascii=False)}\n\n"

                    if isinstance(output, dict):
                        citations = output.get("citations", [])
                        if citations and not emitted_citations:
                            emitted_citations = True
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
                            yield f"data: {json.dumps({'slots': slots}, ensure_ascii=False)}\n\n"
                            yield f"data: {json.dumps({'thought': '关键体征齐全，准备进行评估...'}, ensure_ascii=False)}\n\n"

                    if node_name == "agentic_tools":
                        expanded_query = output.get("expanded_query")
                        if expanded_query:
                            yield f"data: {json.dumps({'thought': f'已将家长口语问题扩展为医学检索查询：{expanded_query}'}, ensure_ascii=False)}\n\n"
                        for trace in output.get("agent_tool_trace", []) or []:
                            yield f"data: {json.dumps({'thought': trace}, ensure_ascii=False)}\n\n"
                        if output.get("ocr_result"):
                            yield f"data: {json.dumps({'ocr_result': output['ocr_result']}, ensure_ascii=False)}\n\n"

                    if node_name == "emergency_guard" and output.get("assessment"):
                        yield f"data: {json.dumps({'thought': '检测到危险信号，已切换到紧急分诊模式。'}, ensure_ascii=False)}\n\n"

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
                    if node_name in ["router", "slot_filling", "agentic_tools", "reflection", "chat"]:
                        current_node = node_name
                    
                    if node_name == "router":
                        yield f"data: {json.dumps({'thought': '接收到请求，正在分析您的意图类型...'}, ensure_ascii=False)}\n\n"
                        
                    if node_name == "slot_filling":
                        yield f"data: {json.dumps({'thought': '进入临床核查，正在比对缺失的医学体征...'}, ensure_ascii=False)}\n\n"
                        
                    if node_name == "agentic_tools":
                        yield f"data: {json.dumps({'thought': '正在规划是否需要读取档案、检索指南、联网或解析报告...'}, ensure_ascii=False)}\n\n"
                        
                    if node_name == "reflection":
                        yield f"data: {json.dumps({'thought': '草稿生成完毕，正在进行严苛的医疗安全红线复核...'}, ensure_ascii=False)}\n\n"
                        
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

            yield "data: [DONE]\n\n"
        finally:
            flush_langfuse()

    return StreamingResponse(generate(), media_type="text/event-stream")
