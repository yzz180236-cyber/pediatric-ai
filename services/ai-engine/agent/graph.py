import os
import logging
import re
from pydantic import BaseModel, Field
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


class AssessmentResult(BaseModel):
    triage_level: Literal["home_observation", "visit_within_24h", "clinic_soon", "emergency_now"]
    triage_reason: str
    trend_direction: Literal["worsening", "improving", "fluctuating", "stable", "unknown"] = "unknown"
    trend_reason: str = ""
    recommended_actions: List[str] = Field(default_factory=list)
    warning_signals: List[str] = Field(default_factory=list)
    constraint_warnings: List[str] = Field(default_factory=list)
    age_band: str = ""


def _build_assessment_payload(result: AssessmentResult) -> Dict[str, object]:
    return {
        "triageLevel": result.triage_level,
        "triageReason": result.triage_reason,
        "trendDirection": result.trend_direction,
        "trendReason": result.trend_reason,
        "recommendedActions": result.recommended_actions,
        "warningSignals": result.warning_signals,
        "constraintWarnings": result.constraint_warnings,
        "ageBand": result.age_band,
    }


def _get_age_band(patient_context: Dict[str, object]) -> str:
    age_months = patient_context.get("ageMonths")
    if not isinstance(age_months, int):
        return "年龄信息不足"
    if age_months <= 3:
        return "0-3个月"
    if age_months <= 6:
        return "4-6个月"
    if age_months <= 12:
        return "7-12个月"
    if age_months <= 36:
        return "1-3岁"
    return "3岁以上"


def _build_constraint_warnings(patient_context: Dict[str, object], latest_message: str) -> List[str]:
    warnings: List[str] = []
    age_months = patient_context.get("ageMonths")
    weight = patient_context.get("latestWeightKg")
    allergens = patient_context.get("knownAllergens") or []
    lower_text = latest_message.lower()

    if age_months is None:
        warnings.append("缺少准确月龄信息，涉及护理或用药建议时应先补充年龄。")
    elif isinstance(age_months, int) and age_months < 3:
        warnings.append("3个月内婴儿属于高敏感年龄段，任何发热或精神反应差都应更谨慎处理。")

    if weight is None:
        warnings.append("缺少近期体重信息，涉及剂量或喂养强度判断时需线下医生确认。")

    if isinstance(allergens, list) and allergens:
        warnings.append(f"已知过敏史：{'、'.join(str(item) for item in allergens)}，避免给出相关食物或成分建议。")

    if any(keyword in lower_text for keyword in ["药", "退烧", "抗生素", "布洛芬", "对乙酰氨基酚"]):
        warnings.append("涉及药物时仅能给出原则性提醒，不能替代医生面诊和处方。")

    return warnings


def _detect_symptom_category(text: str) -> str:
    if re.search(r"发烧|发热|体温|高热|低热", text):
        return "fever"
    if re.search(r"咳嗽|咳痰|喉咙|喘|鼻塞|流鼻涕", text):
        return "cough"
    if re.search(r"腹泻|拉肚子|呕吐|吐奶|便稀|大便", text):
        return "gastro"
    if re.search(r"皮疹|起疹子|红点|红疹|荨麻疹|湿疹", text):
        return "rash"
    return "general"


SYMPTOM_TEMPLATES: Dict[str, List[Dict[str, object]]] = {
    "fever": [
        {"slot": "age", "question": "宝宝现在大概多大了？", "options": ["0-3个月", "4-6个月", "7-12个月", "1-3岁", "3岁以上"]},
        {"slot": "temperature", "question": "目前测到的最高体温大概是多少？", "options": ["37.3-38°C", "38-39°C", "39°C以上", "还没量体温"]},
        {"slot": "duration", "question": "发热大概持续多久了？", "options": ["刚开始半天内", "1天左右", "2-3天", "3天以上"]},
        {"slot": "mental_state", "question": "宝宝精神状态怎么样？", "options": ["精神还可以", "有点蔫", "明显嗜睡/反应差"]},
    ],
    "cough": [
        {"slot": "age", "question": "宝宝现在大概多大了？", "options": ["0-3个月", "4-6个月", "7-12个月", "1-3岁", "3岁以上"]},
        {"slot": "duration", "question": "咳嗽持续多久了？", "options": ["刚开始半天内", "1-2天", "3-5天", "超过5天"]},
        {"slot": "breathing_state", "question": "咳嗽时呼吸情况如何？", "options": ["只是偶尔咳", "夜里咳得多", "有喘或呼吸急", "呼吸很费力"]},
        {"slot": "mental_state", "question": "宝宝精神和吃奶/进食情况如何？", "options": ["精神食欲都还可以", "食欲一般", "精神差/吃得很少"]},
    ],
    "gastro": [
        {"slot": "age", "question": "宝宝现在大概多大了？", "options": ["0-3个月", "4-6个月", "7-12个月", "1-3岁", "3岁以上"]},
        {"slot": "duration", "question": "腹泻或呕吐持续多久了？", "options": ["刚开始半天内", "1天左右", "2-3天", "3天以上"]},
        {"slot": "frequency", "question": "这期间大概有多频繁？", "options": ["1-2次", "3-5次", "6次以上", "说不清"]},
        {"slot": "hydration", "question": "宝宝进食和尿量情况如何？", "options": ["吃奶/喝水正常，尿量正常", "吃得少一些", "尿量变少", "喝不进去/一直吐"]},
    ],
    "rash": [
        {"slot": "age", "question": "宝宝现在大概多大了？", "options": ["0-3个月", "4-6个月", "7-12个月", "1-3岁", "3岁以上"]},
        {"slot": "duration", "question": "皮疹出现多久了？", "options": ["今天刚出现", "1-2天", "3-5天", "超过5天"]},
        {"slot": "distribution", "question": "皮疹主要长在哪里？", "options": ["面部", "躯干", "四肢", "全身都有"]},
        {"slot": "fever_with_rash", "question": "起疹子同时有发热或精神差吗？", "options": ["没有", "有低热", "有高热", "精神明显差"]},
    ],
}


def _extract_template_slots(text: str, existing_slots: Dict[str, str]) -> Dict[str, str]:
    slots = dict(existing_slots)

    age_match = re.search(r"(\d+)\s*(个?月|岁)", text)
    if age_match and "age" not in slots:
        slots["age"] = f"{age_match.group(1)}{age_match.group(2)}"

    temp_match = re.search(r"([3-4]\d(?:\.\d)?)\s*(?:度|℃|c)", text, re.IGNORECASE)
    if temp_match and "temperature" not in slots:
        slots["temperature"] = f"{temp_match.group(1)}°C"

    duration_match = re.search(r"(半天|一天|1天|2天|3天|[一二三四五六七八九十\d]+天|[一二三四五六七八九十\d]+周)", text)
    if duration_match and "duration" not in slots:
        slots["duration"] = duration_match.group(1)

    if re.search(r"精神.*(好|可以)|精神还行|精神尚可", text) and "mental_state" not in slots:
        slots["mental_state"] = "精神还可以"
    elif re.search(r"精神差|反应差|蔫|嗜睡", text) and "mental_state" not in slots:
        slots["mental_state"] = "精神差"

    if re.search(r"呼吸困难|喘不上气|喘|呼吸急|呼吸费力", text) and "breathing_state" not in slots:
        slots["breathing_state"] = "有喘或呼吸费力"

    if re.search(r"尿量减少|尿少|半天没尿|一天没尿", text) and "hydration" not in slots:
        slots["hydration"] = "尿量变少"

    if re.search(r"呕吐.*(\d+)[次遍]", text) and "frequency" not in slots:
        slots["frequency"] = re.search(r"呕吐.*(\d+)[次遍]", text).group(1) + "次"

    return slots


def _build_structured_summary(
    category: str,
    slots: Dict[str, str],
    latest_message: str,
    assessment: Dict[str, object],
) -> str:
    chief_complaint = slots.get("symptom") or latest_message[:60]
    duration = slots.get("duration", "未明确")
    age = slots.get("age", assessment.get("ageBand", "年龄信息不足"))
    warning_signals = assessment.get("warningSignals", []) or []
    triage_label = assessment.get("triageLevel", "visit_within_24h")
    trend_direction = assessment.get("trendDirection", "unknown")
    trend_reason = assessment.get("trendReason", "")
    triage_map = {
        "home_observation": "居家观察",
        "visit_within_24h": "24小时内就医",
        "clinic_soon": "尽快门诊",
        "emergency_now": "立即急诊",
    }
    trend_map = {
        "worsening": "较前加重",
        "improving": "较前缓解",
        "fluctuating": "反复波动",
        "stable": "暂无明显变化",
        "unknown": "趋势暂不明确",
    }

    summary_parts = [
        f"主诉：{chief_complaint}",
        f"年龄分层：{age}",
        f"病程：{duration}",
        f"症状类别：{category}",
        f"分诊结论：{triage_map.get(str(triage_label), '24小时内就医')}",
        f"病程趋势：{trend_map.get(str(trend_direction), '趋势暂不明确')}",
    ]
    if trend_reason:
        summary_parts.append(f"趋势依据：{trend_reason}")
    if warning_signals:
        summary_parts.append(f"危险信号：{'、'.join(str(item) for item in warning_signals)}")
    return "；".join(summary_parts)


def _build_evidence_layers(
    assessment: Dict[str, object],
    citations: List[Dict[str, object]],
) -> List[Dict[str, str]]:
    layers: List[Dict[str, str]] = []

    if citations:
        top_refs = []
        for citation in citations[:2]:
            title = str(citation.get("title", "指南来源"))
            chapter = str(citation.get("chapter", "") or "")
            ref = f"{title} / {chapter}" if chapter else title
            top_refs.append(ref)
        layers.append({
            "sourceType": "guideline",
            "title": "指南引用",
            "content": "；".join(top_refs),
        })

    safety_bits: List[str] = []
    if assessment.get("warningSignals"):
        safety_bits.append(f"危险信号：{'、'.join(str(item) for item in assessment['warningSignals'])}")
    if assessment.get("constraintWarnings"):
        safety_bits.extend(str(item) for item in assessment["constraintWarnings"][:2])
    if safety_bits:
        layers.append({
            "sourceType": "safety_rule",
            "title": "安全规则",
            "content": "；".join(safety_bits),
        })

    inference_bits: List[str] = []
    if assessment.get("triageReason"):
        inference_bits.append(f"分诊判断：{assessment['triageReason']}")
    if assessment.get("trendReason"):
        inference_bits.append(f"趋势判断：{assessment['trendReason']}")
    if inference_bits:
        layers.append({
            "sourceType": "model_inference",
            "title": "模型推断",
            "content": "；".join(inference_bits),
        })

    return layers


def _infer_trend_from_history(history: List[dict], latest_message: str) -> Dict[str, str]:
    previous_user_texts = [
        str(item.get("content", "")).strip()
        for item in history
        if item.get("role") == "user" and str(item.get("content", "")).strip()
    ]
    if not previous_user_texts:
        return {"trend_direction": "unknown", "trend_reason": "缺少足够的历史问诊描述，无法比较前后变化。"}

    merged_previous = "\n".join(previous_user_texts[-3:])
    current_text = latest_message

    worsening_markers = ["加重", "更严重", "越来越重", "反而更差", "还是高烧", "精神更差", "尿更少", "咳得更厉害"]
    improving_markers = ["好转", "缓解", "退烧了", "精神好多了", "比昨天好", "症状轻了", "咳得少了"]
    fluctuating_markers = ["反复", "一会好一会差", "时好时坏", "退了又烧", "反复发烧"]

    if any(marker in current_text for marker in fluctuating_markers):
        return {"trend_direction": "fluctuating", "trend_reason": "当前描述提示症状存在反复或时好时坏。"}
    if any(marker in current_text for marker in worsening_markers):
        return {"trend_direction": "worsening", "trend_reason": "当前描述明确提到较前加重或出现更差表现。"}
    if any(marker in current_text for marker in improving_markers):
        return {"trend_direction": "improving", "trend_reason": "当前描述明确提到较前缓解或整体好转。"}

    if any(marker in merged_previous for marker in ["发烧", "发热"]) and any(marker in current_text for marker in ["已经退烧", "退烧了", "不烧了"]):
        return {"trend_direction": "improving", "trend_reason": "历史中有发热描述，而当前表示已退热。"}
    if any(marker in merged_previous for marker in ["咳嗽", "腹泻", "呕吐", "皮疹"]) and any(marker in current_text for marker in ["还是", "仍然", "没有缓解"]):
        return {"trend_direction": "stable", "trend_reason": "历史已有相同症状描述，当前反馈为仍持续存在。"}

    return {"trend_direction": "unknown", "trend_reason": "历史与当前描述不足以支持明确的加重或缓解判断。"}


EMERGENCY_RULES = [
    {
        "signal": "惊厥或抽搐",
        "patterns": [r"惊厥", r"抽搐", r"抽风", r"高热惊厥"],
        "reason": "描述中出现惊厥或抽搐，属于儿科急症，需要立即线下急救评估。",
    },
    {
        "signal": "呼吸困难或发绀",
        "patterns": [r"呼吸困难", r"喘不上气", r"口唇发紫", r"嘴唇发紫", r"发绀", r"憋气", r"三凹征", r"胸凹"],
        "reason": "出现呼吸困难、缺氧或发绀描述，可能提示呼吸衰竭风险。",
    },
    {
        "signal": "意识差或持续嗜睡",
        "patterns": [r"叫不醒", r"意识不清", r"嗜睡", r"反应差", r"昏睡"],
        "reason": "存在意识状态异常或反应差，需尽快排除严重感染或神经系统问题。",
    },
    {
        "signal": "明显脱水或尿量减少",
        "patterns": [r"半天没尿", r"一天没尿", r"尿量减少", r"哭.*没眼泪", r"前囟.*凹陷"],
        "reason": "尿量明显减少或脱水体征提示循环容量不足风险，需要尽快线下补液评估。",
    },
    {
        "signal": "持续高热",
        "patterns": [r"高烧不退", r"持续高热", r"40[度℃]", r"39\.5", r"39\.6", r"39\.7", r"39\.8", r"39\.9"],
        "reason": "持续高热或超高热属于高风险表现，需要尽快线下评估感染及并发症。",
    },
    {
        "signal": "反复呕吐",
        "patterns": [r"反复呕吐", r"一直吐", r"喷射性呕吐", r"吐了好多次"],
        "reason": "持续或喷射性呕吐可能提示脱水、颅压问题或严重胃肠道疾病。",
    },
]

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
        return "emergency_guard"
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
        return "emergency_guard"
    if intent == "report":
        return "rag"
    return "chat"


def emergency_guard_node(state: GraphState):
    """危险信号前置熔断：命中急症信号时不再继续普通问诊链路"""
    trace_id = state.get("trace_id", "unknown")
    patient_context = state.get("patient_context", {}) or {}
    text_parts = list(state.get("messages", []))
    for history_item in state.get("history", []):
        content = history_item.get("content")
        if content:
            text_parts.append(str(content))
    merged_text = "\n".join(text_parts)

    matched_signals: List[str] = []
    matched_reasons: List[str] = []
    for rule in EMERGENCY_RULES:
        if any(re.search(pattern, merged_text, re.IGNORECASE) for pattern in rule["patterns"]):
            matched_signals.append(rule["signal"])
            matched_reasons.append(rule["reason"])

    if not matched_signals:
        return {}

    logger.warning(f"[{trace_id}] 命中危险信号熔断: {matched_signals}")
    assessment = _build_assessment_payload(
        AssessmentResult(
            triage_level="emergency_now",
            triage_reason="；".join(matched_reasons),
            recommended_actions=[
                "请立即前往最近的儿科急诊或呼叫急救，不要继续等待线上问诊结论。",
                "途中持续观察呼吸、意识和抽搐情况，避免自行口服复杂药物。",
                "尽量保留体温变化、呕吐次数和既往病史，便于急诊医生快速判断。",
            ],
            warning_signals=matched_signals,
            constraint_warnings=_build_constraint_warnings(patient_context, merged_text),
            age_band=_get_age_band(patient_context),
        )
    )
    reply = (
        "### 紧急就医提示\n"
        "- 当前分诊级别：**立即急诊**\n"
        f"- 触发原因：{'；'.join(matched_signals)}\n"
        "- 建议：请立即前往最近的儿科急诊或呼叫急救，不建议继续等待线上问诊。\n\n"
        "> ⚠️ 免责声明：以上内容仅供医学参考，不能替代执业医师面诊，不作为最终诊断依据。"
    )
    return {"assessment": assessment, "reply": reply}


def route_after_emergency_guard(state: GraphState) -> str:
    assessment = state.get("assessment")
    if isinstance(assessment, dict) and assessment.get("triageLevel") == "emergency_now":
        return END
    return "slot_filling"

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
    latest_message = all_messages[-1] if all_messages else ""
    category = _detect_symptom_category(conversation_text)
    template_slots = _extract_template_slots(conversation_text, existing_slots)

    if category in SYMPTOM_TEMPLATES:
        updated_slots = {**template_slots, "symptom_category": category}
        for template in SYMPTOM_TEMPLATES[category]:
            slot_name = str(template["slot"])
            if not updated_slots.get(slot_name):
                logger.info(f"[{trace_id}] 命中模板化追问: {category}, 缺失 {slot_name}")
                followup_card = {
                    "question": template["question"],
                    "options": template["options"],
                }
                return {
                    "slots": {**updated_slots, "status": "missing"},
                    "followup_card": followup_card,
                    "reply": str(template["question"]),
                }

        if category != "general":
            if "symptom" not in updated_slots:
                updated_slots["symptom"] = latest_message[:80]
            logger.info(f"[{trace_id}] 模板化追问已补齐核心字段: {category}")
            return {"slots": {**updated_slots, "status": "filled"}}
    
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


def triage_assessment_node(state: GraphState):
    """结构化分诊与档案约束评估节点"""
    trace_id = state.get("trace_id", "unknown")
    patient_context = state.get("patient_context", {}) or {}
    slots = state.get("slots", {}) or {}
    latest_message = state["messages"][-1] if state.get("messages") else ""
    context = state.get("context", "")
    citations = state.get("citations", []) or []
    category = str(slots.get("symptom_category") or _detect_symptom_category(latest_message))
    history = state.get("history", []) or []
    trend_hint = _infer_trend_from_history(history, latest_message)

    llm = get_llm(is_vision=False).with_structured_output(AssessmentResult)
    prompt = f"""你是一名负责儿科线上分诊的资深医生，请根据用户描述、已提取槽位和档案信息，输出结构化分诊结论。

分诊级别定义：
- home_observation: 可先居家观察
- visit_within_24h: 建议 24 小时内线下就医
- clinic_soon: 建议尽快去门诊，不建议继续拖延
- emergency_now: 建议立即急诊

用户本轮问题：{latest_message}
已提取槽位：{slots}
患儿结构化上下文：{patient_context}
参考知识：{context[:1500]}

要求：
1. triage_reason 必须说明为什么分到该级别
2. trend_direction 输出 worsening / improving / fluctuating / stable / unknown
3. trend_reason 说明你为什么判断为该趋势，可参考这个规则提示：{trend_hint}
4. recommended_actions 给出 2-4 条可执行建议
5. warning_signals 填写当前已知的危险信号，没有则留空数组
6. constraint_warnings 必须考虑年龄、体重、过敏史不足或高风险因素
7. age_band 输出类似“0-3个月 / 4-6个月 / 7-12个月 / 1-3岁 / 3岁以上 / 年龄信息不足”
"""

    try:
        result: AssessmentResult = llm.invoke([HumanMessage(content=prompt)])
        payload = _build_assessment_payload(result)
        if not payload["constraintWarnings"]:
            payload["constraintWarnings"] = _build_constraint_warnings(patient_context, latest_message)
        if not payload["trendReason"]:
            payload["trendDirection"] = trend_hint["trend_direction"]
            payload["trendReason"] = trend_hint["trend_reason"]
        payload["symptomCategory"] = category
        payload["summaryText"] = _build_structured_summary(category, slots, latest_message, payload)
        payload["evidenceLayers"] = _build_evidence_layers(payload, citations)
        logger.info(f"[{trace_id}] 结构化分诊完成: {payload['triageLevel']}")
        return {"assessment": payload}
    except Exception:
        logger.exception(f"[{trace_id}] triage_assessment_node 异常")
        fallback = _build_assessment_payload(
            AssessmentResult(
                triage_level="visit_within_24h",
                triage_reason="当前信息不足以完成高置信度分诊，建议结合线下儿科医生进一步评估。",
                trend_direction=trend_hint["trend_direction"], 
                trend_reason=trend_hint["trend_reason"],
                recommended_actions=[
                    "继续补充体温、持续时间、精神状态和进食尿量信息。",
                    "若症状持续或加重，请在 24 小时内线下就医。",
                ],
                warning_signals=[],
                constraint_warnings=_build_constraint_warnings(patient_context, latest_message),
                age_band=_get_age_band(patient_context),
            )
        )
        fallback["symptomCategory"] = category
        fallback["summaryText"] = _build_structured_summary(category, slots, latest_message, fallback)
        fallback["evidenceLayers"] = _build_evidence_layers(fallback, citations)
        return {"assessment": fallback}

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
    assessment = state.get("assessment", {}) or {}
    # 如果档案不为空，则预备注入到 system_prompt 中作为医生的"病历本"
    patient_profile_block = f"\n\n{patient_profile}\n（请在所有分析和建议中充分利用以上档案信息，它们来自该患儿的历史问诊记录。）" if patient_profile else ""
    assessment_block = ""
    if assessment:
        assessment_block = (
            "\n\n【系统结构化分诊结果】\n"
            f"- 分诊级别：{assessment.get('triageLevel')}\n"
            f"- 分诊原因：{assessment.get('triageReason')}\n"
            f"- 年龄分层：{assessment.get('ageBand')}\n"
            f"- 约束提醒：{'；'.join(assessment.get('constraintWarnings', [])) if assessment.get('constraintWarnings') else '无'}\n"
            "（你的正式答复必须与以上结构化分诊保持一致，不能弱化紧急程度。）"
        )

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
    if assessment_block:
        system_prompt += assessment_block

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
    workflow.add_node("emergency_guard", emergency_guard_node)
    workflow.add_node("slot_filling", slot_filling_node)
    workflow.add_node("ocr", ocr_extraction_node)
    workflow.add_node("rag", rag_node)
    workflow.add_node("triage_assessment", triage_assessment_node)
    workflow.add_node("chat", chat_node)
    workflow.add_node("reflection", reflection_node)
    
    # 设定起点
    workflow.set_entry_point("router")
    
    # 路由判断（medical → emergency_guard，report → ocr，general → chat, 或走 web_search 前置）
    workflow.add_conditional_edges("router", route_after_router, {
        "web_search": "web_search",
        "emergency_guard": "emergency_guard",
        "rag": "rag",
        "ocr": "ocr",
        "chat": "chat"
    })
    
    workflow.add_conditional_edges("web_search", route_after_web_search, {
        "emergency_guard": "emergency_guard",
        "rag": "rag",
        "chat": "chat"
    })

    workflow.add_conditional_edges("emergency_guard", route_after_emergency_guard, {
        "slot_filling": "slot_filling",
        END: END
    })
    
    # 槽位判断
    workflow.add_conditional_edges("slot_filling", route_after_slot_filling, {
        "rag": "rag",
        END: END
    })
    
    workflow.add_edge("ocr", "rag")
    
    workflow.add_edge("rag", "triage_assessment")
    workflow.add_edge("triage_assessment", "chat")
    workflow.add_edge("chat", "reflection")
    workflow.add_conditional_edges("reflection", route_after_reflection, {
        "chat": "chat",
        END: END
    })
    
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    
    return workflow.compile(checkpointer=checkpointer)
