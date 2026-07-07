import os
import logging
from pydantic import BaseModel
from typing import Literal, Dict, List, Optional
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import base64
from urllib.parse import urlparse
from .state import GraphState
from .rag_milvus import PediatricRAG
from config import get_llm_base_url, require_env

logger = logging.getLogger(__name__)

_rag_engine = None

def get_rag_engine():
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = PediatricRAG()
    return _rag_engine

def get_llm(is_vision=False):
    """基于环境变量构建大语言模型实例"""
    api_key = require_env("LLM_API_KEY")
    base_url = get_llm_base_url()
    model = os.environ.get("LLM_VISION_MODEL_NAME", "qwen-vl-plus") if is_vision else os.environ.get("LLM_MODEL_NAME", "qwen3.6-plus")
    return ChatOpenAI(api_key=api_key, base_url=base_url, model=model)

class IntentResult(BaseModel):
    intent: Literal["medical", "report", "general"]
    confidence: float
    reasoning: str
    needs_web_search: bool
    search_query: str

def router_node(state: GraphState):
    """意图识别节点：使用 LLM 零样本分类识别用户意图"""
    trace_id = state.get("trace_id", "unknown")
    msg = state["messages"][-1] if state["messages"] else ""
    has_image = bool(state.get("image_data"))
    if not has_image:
        for h in state.get("history", []):
            if h.get("image"):
                has_image = True
                break

    # 强制带图片的默认进入 report 意图
    if has_image:
        logger.info(f"[{trace_id}] 检测到图片，直接路由为 report")
        return {"intent": "report", "intent_confidence": 1.0}

    llm = get_llm(is_vision=False).with_structured_output(IntentResult)
    classify_prompt = f"""你是一名儿科问诊系统的意图分类器。
根据用户输入，输出一个结构化的意图分类结果。

意图类型：
- medical: 用户描述宝宝的症状、询问疾病、寻求医疗建议
- report: 用户上传了检验报告/化验单，要求解读，或者提到报告
- general: 育儿日常咨询、喂养问题、非医疗问题

用户输入："{msg}"

请判断意图并给出置信度（0.0~1.0）。如果用户的问题需要查询最新的新闻、医学突破、政策、或者通识事实库，请将 needs_web_search 设为 true，并在 search_query 中填入搜索词。"""

    try:
        result: IntentResult = llm.invoke([HumanMessage(content=classify_prompt)])
        logger.info(f"[{trace_id}] 意图识别结果: {result.intent}, 置信度: {result.confidence}, 网搜: {result.needs_web_search}")
        return {
            "intent": result.intent, 
            "intent_confidence": result.confidence,
            "needs_web_search": getattr(result, "needs_web_search", False),
            "search_query": getattr(result, "search_query", "")
        }
    except Exception as e:
        logger.exception(f"[{trace_id}] router_node 异常")
        return {"intent": "general", "intent_confidence": 0.0, "needs_web_search": False, "search_query": ""}

def route_after_router(state: GraphState) -> str:
    """条件路由：根据意图走向"""
    if state.get("needs_web_search"):
        return "web_search"
    intent = state.get("intent", "general")
    if intent == "medical":
        return "slot_filling"
    if intent == "report":
        return "ocr"   # 报告分析先走 OCR 提取
    return "chat"

def web_search_node(state: GraphState):
    """真实互联网搜索节点"""
    trace_id = state.get("trace_id", "unknown")
    query = state.get("search_query", "")
    
    if not query:
        return {"web_search_context": ""}
        
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            
        context = "\n".join([f"标题: {r.get('title')}\n来源: {r.get('href')}\n摘要: {r.get('body')}" for r in results])
        logger.info(f"[{trace_id}] Web Search 完成: {query}")
        return {"web_search_context": context}
    except Exception as e:
        logger.exception(f"[{trace_id}] web_search_node 异常")
        return {"web_search_context": "搜索服务暂时不可用"}

def route_after_web_search(state: GraphState) -> str:
    """网搜之后的再次路由，走回原来的逻辑分支"""
    intent = state.get("intent", "general")
    if intent == "medical":
        return "slot_filling"
    if intent == "report":
        return "rag"
    return "chat"

class SlotStatus(BaseModel):
    is_complete: bool
    filled_slots: Dict[str, str]
    missing_slots: List[str]
    followup_question: Optional[str]
    # AI 动态生成的快捷选项（最多 5 个），方便家长快速点击回答
    followup_options: Optional[List[str]] = None

def slot_filling_node(state: GraphState):
    """槽位填充节点：自动化追问关键体征"""
    trace_id = state.get("trace_id", "unknown")
    all_messages = state.get("messages", [])
    existing_slots = state.get("slots", {})
    
    conversation_text = "\n".join([f"家长的陈述: {m}" for m in all_messages])
    
    llm = get_llm(is_vision=False).with_structured_output(SlotStatus)
    prompt = f"""分析以下完整的对话记录，提取儿科问诊关键信息。
必填信息：年龄/月龄、主诉症状
选填信息：体温、持续时长、精神状态、大小便情况

已知槽位信息（已从之前对话提取）：{existing_slots}

完整对话记录：
{conversation_text}

请判断是否已收集到足够信息（必填槽位均已填满）。
- 若信息不足，请给出一个温柔专业的追问句（followup_question）。
- 同时根据追问的内容，生成 3-5 个简洁的快捷回答选项（followup_options），方便家长直接点选。
  例如询问月龄时：["0-3个月", "4-6个月", "7-12个月", "1-3岁", "3岁以上"]
  例如询问体温时：["低热 37.3-38°C", "中热 38-39°C", "高热 39°C以上", "没有发烧"]
  选项必须是对追问的直接作答，不要出现与问题无关的内容。"""
    
    try:
        result: SlotStatus = llm.invoke([HumanMessage(content=prompt)])
        if result.is_complete:
            logger.info(f"[{trace_id}] 槽位已全部收集: {result.filled_slots}")
            return {"slots": {**existing_slots, **result.filled_slots, "status": "filled"}}
        else:
            logger.info(f"[{trace_id}] 槽位缺失: {result.missing_slots}, 需追问，选项: {result.followup_options}")
            # 返回结构化的追问卡片数据，main.py 的 SSE 处理器将把它作为 followup_card 事件下发给前端
            followup_card = {
                "question": result.followup_question or "请提供更多宝宝的信息，以便我给出更精准的建议。",
                "options": result.followup_options or []
            }
            return {
                "slots": {**existing_slots, **result.filled_slots, "status": "missing"},
                "followup_card": followup_card,
                "reply": result.followup_question  # 同时保留 reply 作为文字兜底
            }
    except Exception as e:
        logger.exception(f"[{trace_id}] slot_filling_node 异常")
        return {"slots": {"status": "error"}}

def route_after_slot_filling(state: GraphState) -> str:
    """条件路由：根据槽位状态走向"""
    status = state.get("slots", {}).get("status", "")
    if status == "missing":
        # 如果槽位缺失且已经生成了追问 reply，则提前结束 Graph
        return END
    return "rag"

def rag_node(state: GraphState):
    """指南检索 RAG 节点"""
    trace_id = state.get("trace_id", "unknown")
    # 使用完整症状描述做检索，而非只用最后一条消息
    query = state.get("slots", {}).get("symptom") or (state["messages"][-1] if state["messages"] else "")
    
    try:
        context, citations = get_rag_engine().search(query, top_k=5)
        logger.info(f"[{trace_id}] RAG 检索完成，召回 {len(citations)} 条指南")
        return {"context": context, "citations": citations}
    except Exception as e:
        logger.exception(f"[{trace_id}] rag_node 异常")
        return {"context": "知识库暂时不可用，将基于通用知识回答。", "citations": []}

def resolve_image(url_or_base64: str):
    """将私有文件标识转为大模型可读的 Base64"""
    if not url_or_base64: return None
    if url_or_base64.startswith("private://"):
        try:
            filename = url_or_base64.replace("private://", "", 1)
            filepath = os.path.join("private_uploads", filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                    ext = filename.split('.')[-1].lower()
                    mime = "image/jpeg" if ext in ['jpg', 'jpeg'] else f"image/{ext}"
                    return f"data:{mime};base64,{img_b64}"
        except Exception as e:
            logger.debug(f"[DEBUG] 解析本地图片失败: {e}")
    return url_or_base64

def ocr_extraction_node(state: GraphState):
    """专门用来抽取图片中化验单结构化指标的节点"""
    trace_id = state.get("trace_id", "unknown")
    image_data = state.get("image_data")
    if not image_data:
        return {}

    logger.info(f"[{trace_id}] 进入 ocr_extraction_node")
    llm = get_llm(is_vision=True)
    prompt = """请识别这张医学化验单，严格输出一段纯 JSON，不需要Markdown包裹，不需要解释：
{
  "hospitalName": "xxx医院",
  "date": "xxxx-xx-xx",
  "patientName": "姓名",
  "items": [
    {"name": "白细胞", "result": "10.0", "unit": "10^9/L", "referenceRange": "4.0-10.0", "isAbnormal": false}
  ]
}"""
    real_image = resolve_image(image_data)
    if not real_image: return {}

    try:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": real_image}}
        ]
        res = llm.invoke([HumanMessage(content=user_content)])
        content = res.content
        import re, json
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            ocr_json = json.loads(match.group(0))
            logger.info(f"[{trace_id}] OCR 提取成功")
            return {"ocr_result": ocr_json}
    except Exception as e:
        logger.exception(f"[{trace_id}] OCR 提取失败")
    
    return {}

def chat_node(state: GraphState):
    """最终答复节点"""
    trace_id = state.get("trace_id", "unknown")
    intent = state.get("intent", "general")
    msg = state["messages"][-1] if state["messages"] else ""
    context = state.get("context", "")
    feedback = state.get("reflection_feedback", "")
    image_data = state.get("image_data")
    history_data = state.get("history", [])
    
    logger.info(f"[{trace_id}] 进入 chat_node, intent: {intent}")
    
    # 判断是否在当前轮有图片需要直接传视觉模型
    has_image = bool(image_data)
    
    # ✅ 关键设计：双模型分工闭环
    # - 视觉模型（qwen-vl-plus）：仅负责 OCR，在 ocr_extraction_node 中已完成职责
    # - 推理模型（qwen3.6-plus）：负责 chat_node 的医学判断与建议生成
    # 因此：只要 OCR 已经提取出结构化数据，chat_node 必须使用推理模型
    # 只有当没有 OCR 数据且当前轮有图片时，才用视觉模型兜底理解图片
    ocr_already_done = bool(state.get("ocr_result"))
    use_vision_in_chat = has_image and not ocr_already_done
    llm = get_llm(is_vision=use_vision_in_chat)
    logger.info(f"[{trace_id}] chat_node 使用模型: {'视觉' if use_vision_in_chat else '推理文本'} (ocr_done={ocr_already_done}, has_image={has_image})")
    
    from datetime import datetime
    import pytz
    
    # 获取当前的北京时间
    tz = pytz.timezone('Asia/Shanghai')
    current_time = datetime.now(tz).strftime('%Y年%m月%d日 %H:%M:%S (北京时间)')

    web_search_context = state.get("web_search_context", "")
    if web_search_context:
        context_block = f"--- 互联网搜索结果 ---\n{web_search_context}\n\n--- 指南检索结果 ---\n{context}"
    else:
        context_block = f"--- 指南检索结果 ---\n{context}"

    # 【P0.1 患儿档案记忆】：从 state 中取出 BFF 注入的患儿档案摘要
    patient_profile = state.get("patient_profile", "").strip()
    # 如果档案不为空，则预备注入到 system_prompt 中作为医生的"病历本"
    patient_profile_block = f"\n\n{patient_profile}\n（请在所有分析和建议中充分利用以上档案信息，它们来自该患儿的历史问诊记录。）" if patient_profile else ""

    if intent == "report":
        system_prompt = f"""你是一名拥有 20 年临床经验的儿科主任医师，当前时间：{current_time}。
家长向你发送了一张儿科检验/检查报告单（可能是血常规、尿常规、生化、影像等），请你以专业、温暖的医生口吻进行权威解读。

## 你的回答必须严格遵循以下结构：

### 🔍 AI 临床推演过程（必填项，先写这部分）
在回答正式开始前，请务必先将你的临床推理与分析过程包裹在 `<think>` 和 `</think>` 标签内输出。这必须是你思考的第一步！
格式要求：
<think>
(这里一字一句流式写下你是如何依据数据、月龄、病史等进行分析的，不要省略)
</think>

⚠️ 极度重要：你必须写出 `</think>` 来结束思考，然后在 `</think>` 标签的外面（下方）开始输出【一、基本信息确认】及后续的所有正式建议内容！不要把正式建议写在思考框内！

---

### 一、基本信息确认
识别报告中的患儿姓名、年龄/月龄、检验项目名称、采样日期（若有）。

### 二、异常指标解读
逐一列出所有**超出参考范围**的指标：
- 指标名称（英文缩写）
- 实测值 vs 参考范围
- 临床意义（用非专业术语解释给家长听）
- 该月龄儿童的特殊生理特点（如有）

### 三、正常指标简述
用一句话概括哪些主要指标在正常范围内，给家长吃定心丸。

### 四、综合临床评估
结合所有指标，给出整体病情判断（如：目前无急性感染征象 / 存在轻度贫血 / 提示病毒感染可能等）。

### 五、家长行动建议
给出 2-3 条明确、可操作的建议（如：饮食调整、复查时间节点、是否需要就诊等）。

## 写作规范
- 语气专业但温柔，像一位耐心的儿科教授在解释
- 数字要精确，不要模糊表述
- 对于月龄较小的婴儿，需特别说明其生理正常值与成人不同
- 禁止编造报告中没有的数据
- 禁止给出具体药物名称和剂量（仅可建议就医咨询）

参考医疗指南与外部知识：
{context_block}
--------------------

> ⚠️ 免责声明：以上解读仅供医学参考，不能替代执业医师面诊，不作为最终诊断依据！如指标异常明显或患儿症状严重，请立即前往线下医院就诊。"""

    elif intent == "medical":
        system_prompt = f"""你是一名拥有 20 年临床经验的儿科主任医师，当前时间：{current_time}。
请以专业、严谨且温柔的医生口吻回答家长的问题。

## 回答要求
1. **先思考后回答**：在回答正式开始前，请务必先将你的临床推理与分析过程包裹在 `<think>` 和 `</think>` 标签内输出。这必须是你思考的第一步！格式为：
<think>
(这里一字一句流式写下你是如何依据数据、月龄、病史等进行分析的，不要省略)
</think>

---
2. **精准性**：给出有据可查的医学建议，不猜测、不模糊
3. **结构化**：用分点列举，便于家长理解和记忆
4. **年龄敏感**：必须考虑患儿月龄/年龄对症状判断和处理方式的影响
5. **安全红线**：对于需要立即就医的紧急情况（高热惊厥、呼吸困难、口唇发紫等），必须第一句话就告知家长
6. **用药谨慎**：不给出具体药物剂量，建议家长遵医嘱

参考医疗指南与外部知识：
{context_block}
--------------------

> ⚠️ 免责声明：以上内容仅供医学参考，不能替代执业医师面诊，不作为最终诊断依据！情况紧急请立即前往线下医院就医。"""

    else:
        system_prompt = f"""你是一名资深儿科医生，同时也是「智慧儿科」平台的 AI 健康助手，当前时间：{current_time}。

## 你的定位
- 以温柔、专业的口吻与家长沟通日常育儿问题
- 涉及医学问题时，始终保持专业严谨，不做无根据的猜测
- 鼓励家长提供更多信息（如宝宝月龄、具体症状），以便给出更精准的建议
- 对于非医学问题（如喂养、作息、早教等），给出有科学依据的建议

## 先思考后回答（必填）
在给出正式建议前，请务必先将你的临床推理与分析过程包裹在 `<think>` 和 `</think>` 标签内输出，格式为：
<think>
(流式写下你的分析依据和考量)
</think>

---

## 禁止行为
- 禁止给出确定性诊断结论
- 禁止推荐具体药物品牌和剂量
- 禁止对严重症状轻描淡写

参考医疗指南与外部知识：
{context_block}
--------------------
"""

    # 【P0.1】将患儿档案摘要注入 system_prompt 头部，作为医生的"病历本"
    if patient_profile_block:
        system_prompt = patient_profile_block + "\n\n---\n\n" + system_prompt

    if state.get("ocr_result"):
        import json
        ocr_str = json.dumps(state["ocr_result"], ensure_ascii=False)
        system_prompt += f"\n\n【附加医学数据】（这是系统提前提取出的化验单精确数据，请必须基于此数据进行解读）：\n{ocr_str}\n"

    if feedback and feedback != "PASS":
        system_prompt += f"\n\n【主任医师紧急驳回意见】：\n你刚才生成的回答不合格。请严格根据以下修改建议重新生成回答：\n{feedback}"


    # 组装上下文记忆
    history_data = state.get("history", [])
    history_messages = []
    for h in history_data:
        if h["role"] == "user":
            # 推理模型不接受图片 URL，将历史图片替换为文字说明
            if h.get("image") and use_vision_in_chat:
                real_image = resolve_image(h["image"])
                history_messages.append(HumanMessage(content=[
                    {"type": "text", "text": h["content"]},
                    {"type": "image_url", "image_url": {"url": real_image}}
                ]))
            elif h.get("image") and not use_vision_in_chat:
                # 推理模型：用文字说明代替图片，化验数据已在附加医学数据中
                text = h["content"] or "（用户上传了化验单，已由视觉识别模型提取为结构化数据）"
                history_messages.append(HumanMessage(content=text))
            else:
                history_messages.append(HumanMessage(content=h["content"]))
        else:
            history_messages.append(AIMessage(content=h["content"]))

    try:
        # 如果用户上传图片时没写文字，赋予默认引导语
        if not msg.strip():
            msg = "请你结合已提取的附加医学数据，为我详细解读这份报告并给出就医建议。"

        # 推理模型完全支持 SystemMessage，不需要把指令 hack 进 user 消息
        # 视觉模型才需要把指令折叠进 user 消息，但视觉模型现在只走 OCR 节点
        messages = [SystemMessage(content=system_prompt)] + history_messages
        
        if use_vision_in_chat and image_data:
            # 仅当本轮无 OCR 结果且有图片时，才将图片传给视觉模型
            real_current_image = resolve_image(image_data)
            user_content = [
                {"type": "text", "text": msg},
                {"type": "image_url", "image_url": {"url": real_current_image}}
            ]
            messages.append(HumanMessage(content=user_content))
        else:
            # 推理模型：纯文字，OCR 结构化数据已注入 system_prompt
            messages.append(HumanMessage(content=msg))
            
        response = llm.invoke(messages)
        content = response.content.strip()
        logger.info(f"[{trace_id}] chat_node 生成完毕，长度: {len(content)}")
        
        if not content:
            logger.warning(f"[{trace_id}] 大模型生成了空字符串，触发兜底！")
            content = "【系统提示】抱歉，当前模型未能生成诊断总结，请尝试用文字补充说明您的问题。"

        return {"reply": content}
    except Exception as e:
        logger.exception(f"[{trace_id}] chat_node 异常")
        return {"reply": "【系统提示】抱歉，系统暂时有些忙碌，未能生成回答，请稍后再试。"}

def reflection_node(state: GraphState):
    """自我审查节点：对生成的回答进行红线与合规审查"""
    trace_id = state.get("trace_id", "unknown")
    reply = state.get("reply", "")
    intent = state.get("intent", "general")
    count = state.get("reflection_count", 0)
    
    # 只有医疗问题才启动严格的自我审查，日常闲聊免检
    if intent != "medical":
        logger.info(f"[{trace_id}] 非医疗意图，跳过自我审查")
        return {"reflection_count": count + 1, "reflection_feedback": "PASS"}
        
    llm = get_llm(is_vision=False)
    prompt = f"""
    你现在的身份是严苛的【儿科主任医师兼合规审核员】。
    请极其严格地审查下面 AI 助手的草稿回答。

    审查标准：
    1. 【红线】回答最末尾是否明确附带了类似“免责声明”、“不能替代执业医师面诊”等警告字样？
    2. 【红线】是否编造了不存在的药物或过度治疗方案？
    3. 【体验】语气是否足够温柔、关切？

    待审查回答草稿：
    --------------------
    {reply}
    --------------------
    
    如果完全合格，请只输出 "PASS" 这四个字母，不要解释。
    如果有任何问题，请输出 "FAIL: [具体的不合格原因，并给出下一步如何修改的具体建议]"。
    """
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)]).content
        if res.strip().startswith("PASS"):
            logger.info(f"[{trace_id}] 自我审查 PASS")
            return {"reflection_count": count + 1, "reflection_feedback": "PASS"}
        else:
            logger.warning(f"[{trace_id}] 自我审查拦截成功! 意见: {res}")
            return {"reflection_count": count + 1, "reflection_feedback": res}
    except Exception as e:
        logger.exception(f"[{trace_id}] reflection_node 异常")
        return {"reflection_count": count + 1, "reflection_feedback": "PASS"}

def route_after_reflection(state: GraphState) -> str:
    """如果通过审查或者达到最大重试次数，则结束"""
    feedback = state.get("reflection_feedback", "")
    count = state.get("reflection_count", 0)
    
    # 设定最大循环重试次数为 2，防止死循环
    if feedback == "PASS" or count >= 2:
        return END
    return "chat"

def build_graph():
    """构建与编译拓扑图"""
    workflow = StateGraph(GraphState)
    
    workflow.add_node("router", router_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("slot_filling", slot_filling_node)
    workflow.add_node("ocr", ocr_extraction_node)
    workflow.add_node("rag", rag_node)
    workflow.add_node("chat", chat_node)
    workflow.add_node("reflection", reflection_node)
    
    # 设定起点
    workflow.set_entry_point("router")
    
    # 路由判断（medical → slot_filling，report → rag 直接，general → chat, 或走 web_search 前置）
    workflow.add_conditional_edges("router", route_after_router, {
        "web_search": "web_search",
        "slot_filling": "slot_filling",
        "rag": "rag",
        "ocr": "ocr",
        "chat": "chat"
    })
    
    workflow.add_conditional_edges("web_search", route_after_web_search, {
        "slot_filling": "slot_filling",
        "rag": "rag",
        "chat": "chat"
    })
    
    # 槽位判断
    workflow.add_conditional_edges("slot_filling", route_after_slot_filling, {
        "rag": "rag",
        END: END
    })
    
    workflow.add_edge("ocr", "rag")
    
    workflow.add_edge("rag", "chat")
    workflow.add_edge("chat", "reflection")
    workflow.add_conditional_edges("reflection", route_after_reflection, {
        "chat": "chat",
        END: END
    })
    
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    
    return workflow.compile(checkpointer=checkpointer)
