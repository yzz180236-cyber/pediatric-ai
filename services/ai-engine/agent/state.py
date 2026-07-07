from typing import TypedDict, List, Annotated, Dict, Any
import operator
import time

def merge_slots(existing: Dict[str, Any], new_update: Dict[str, Any]) -> Dict[str, Any]:
    """合并或重置槽位。如果带有 _clear 标识或者距离上次更新超过一定时间，则重置"""
    if new_update.get("_clear") is True:
        return {}
    
    current_time = time.time()
    last_update = existing.get("_last_update", current_time) if existing else current_time
    
    # 超时重置机制 (例如 1800 秒 = 30 分钟无交互则清空)
    if current_time - last_update > 1800:
        existing = {}
        
    merged = existing.copy() if existing else {}
    merged.update(new_update)
    merged["_last_update"] = current_time
    return merged

class GraphState(TypedDict, total=False):
    """LangGraph 全局状态机模型定义"""
    # 使用 operator.add 使得每次流转都能将新的对话附加到列表，而不是覆盖
    messages: Annotated[List[str], operator.add]
    
    # 链路追踪 ID
    trace_id: str
    
    # 意图标记：'medical' | 'general' | 'report'
    intent: str
    intent_confidence: float
    
    # 提取的槽位实体 (age, symptoms, duration, temperature)
    slots: Annotated[Dict[str, Any], merge_slots]
    
    # RAG 检索返回的参考医学知识
    context: str
    citations: List[Dict[str, str]]
    
    # 最终回复
    reply: str
    
    # 联网搜索
    needs_web_search: bool
    search_query: str
    web_search_context: str
    
    # 深度审查反馈意见
    reflection_feedback: str
    
    # 打回重写次数统计，用于防止死循环
    reflection_count: int
    
    # 前端传来的多模态图片数据 (Base64 或 URL)
    image_data: str
    
    # 影像解析获得的结构化化验单指标 (OCR 结果)
    ocr_result: Dict[str, Any]
    
    # 前端传来的多轮对话历史记录
    history: List[dict]
    
    # 槽位追问卡片（当槽位缺失时由 slot_filling_node 填充，供前端渲染快捷选项卡）
    followup_card: Dict[str, Any]
    
    # 患儿档案摘要（由 BFF 从数据库读取后注入，包含月龄/过敏史/近期病史等跨会话记忆）
    patient_profile: str
