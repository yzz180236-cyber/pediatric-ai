import os
import atexit
import logging
import re
import json
import random
import time
from pydantic import BaseModel, Field
from typing import Any, Literal, Dict, List, Optional, Union
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
import base64
from .state import GraphState
from .rag_milvus import PediatricRAG
from config import get_llm_base_url, require_env

logger = logging.getLogger(__name__)

_rag_engine = None
_postgres_checkpointer_context = None
_postgres_checkpointer = None

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
    timeout_seconds = float(os.environ.get("LLM_TIMEOUT_SECONDS", "15"))
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout_seconds,
        max_retries=0,
    )


TRANSIENT_LLM_ERROR_PATTERNS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "rate limit",
    "temporarily unavailable",
    "connection reset",
    "service unavailable",
)
MAX_LLM_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))
MEDICATION_REDLINE_PATTERN = re.compile(
    r"(阿莫西林|头孢|布洛芬|对乙酰氨基酚|美林|泰诺林|抗生素|阿奇霉素|雾化|止咳糖浆)"
    r"[\s\S]{0,24}?"
    r"(\d+(\.\d+)?\s*(ml|mL|毫升|mg|毫克|片|包|粒|滴|次|天|小时))",
    re.IGNORECASE,
)
PRESCRIPTION_ONLY_PATTERN = re.compile(
    r"(处方药|抗生素|阿莫西林|头孢|阿奇霉素|美林|泰诺林|布洛芬|对乙酰氨基酚)",
    re.IGNORECASE,
)
DISCLAIMER_PATTERN = re.compile(r"免责声明|仅供.*参考|不能替代.*面诊|不作为.*诊断依据")


def _should_retry_llm_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(pattern in message for pattern in TRANSIENT_LLM_ERROR_PATTERNS)


def _invoke_llm_with_retry(
    llm: ChatOpenAI,
    messages: List[Any],
    trace_id: str,
    operation: str,
) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_LLM_RETRIES + 1):
        try:
            return llm.invoke(messages)
        except Exception as exc:
            last_exc = exc
            is_last_attempt = attempt >= MAX_LLM_RETRIES
            if not _should_retry_llm_error(exc) or is_last_attempt:
                logger.exception(f"[{trace_id}] {operation} 调用失败，attempt={attempt}")
                raise
            delay = min(0.6 * (2 ** (attempt - 1)) + random.uniform(0, 0.2), 3.0)
            logger.warning(f"[{trace_id}] {operation} 调用失败，{delay:.2f}s 后重试第 {attempt + 1} 次: {exc}")
            time.sleep(delay)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"{operation} 调用失败")


def _extract_first_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]
    except Exception:
        pass

    try:
        decoder = json.JSONDecoder()
        for start_index, char in enumerate(stripped):
            if char != "{":
                continue
            parsed, _ = decoder.raw_decode(stripped[start_index:])
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    return None


def _normalize_json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    alias_pairs = {
        "intent_type": "intent",
        "need_web_search": "needs_web_search",
        "triageLevel": "triage_level",
        "triageReason": "triage_reason",
        "trendDirection": "trend_direction",
        "trendReason": "trend_reason",
        "recommendedAction": "recommended_actions",
        "recommended_actions_list": "recommended_actions",
        "warningSignals": "warning_signals",
        "constraintWarnings": "constraint_warnings",
        "ageBand": "age_band",
    }
    for old_key, new_key in alias_pairs.items():
        if old_key in normalized and new_key not in normalized:
            normalized[new_key] = normalized[old_key]
    return normalized


def _extract_citation_indices(reply: str) -> List[int]:
    return [int(match) for match in re.findall(r"\[\^(\d+)\]", reply or "")]


def _is_measurement_only_reply(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    if _is_growth_only_reply(compact):
        return True
    measurement_keywords = ("kg", "cm", "℃", "度", "次/分", "mmol", "10^", "%", "bpm", "ml")
    has_measurement_keyword = any(keyword.lower() in compact.lower() for keyword in measurement_keywords)
    no_symptom_text = not re.search(r"发热|发烧|咳|喘|痛|吐|泻|疹|抽|精神差|呼吸", compact)
    digit_ratio = sum(char.isdigit() for char in compact) / max(len(compact), 1)
    return has_measurement_keyword and no_symptom_text and digit_ratio >= 0.2


def _evaluate_reply_safety(
    reply: str,
    citations: List[Dict[str, object]],
    require_citation_protocol: bool,
) -> List[str]:
    violations: List[str] = []
    if not DISCLAIMER_PATTERN.search(reply or ""):
        violations.append("回答缺少强制免责声明。")
    if MEDICATION_REDLINE_PATTERN.search(reply or ""):
        violations.append("回答包含具体药物名称与剂量/频次，触发医疗用药红线。")
    elif PRESCRIPTION_ONLY_PATTERN.search(reply or "") and re.search(r"推荐|建议|使用|服用|口服", reply or ""):
        violations.append("回答对处方药给出了过强的推荐或治疗导向。")
    if require_citation_protocol:
        citation_indices = _extract_citation_indices(reply)
        if citation_indices:
            citation_count = len(citations)
            invalid_indices = [idx for idx in citation_indices if idx < 1 or idx > citation_count]
            if invalid_indices:
                violations.append("回答中的引用编号超出实际 RAG 召回范围。")
        if "[^" in (reply or "") and not citation_indices:
            violations.append("回答包含损坏的引用语法。")
    return violations


def _build_medical_redline_fallback(citations: List[Dict[str, object]]) -> str:
    source_line = ""
    if citations:
        source_labels = []
        for index, citation in enumerate(citations[:2], start=1):
            title = str(citation.get("title", "指南来源"))
            chapter = str(citation.get("chapter", "") or "")
            label = f"[^{index}] {title}"
            if chapter:
                label += f" / {chapter}"
            source_labels.append(label)
        source_line = "\n\n参考依据：\n" + "\n".join(source_labels)
    return (
        "### 安全提示\n"
        "当前问题涉及医疗用药或高风险处置，我不能提供具体药物品牌、剂量或替代处方建议。\n"
        "请尽快携带宝宝的年龄、体重、症状持续时间和既往过敏史，联系线下儿科医生或就近就诊。"
        f"{source_line}\n\n"
        "> ⚠️ 免责声明：以上内容仅供医学参考，不能替代执业医师面诊，不作为最终诊断依据。"
    )


def _invoke_json_dict(prompt: str, trace_id: str) -> Optional[dict]:
    try:
        llm = get_llm(is_vision=False)
        raw = _invoke_llm_with_retry(
            llm,
            [HumanMessage(content=prompt)],
            trace_id,
            "structured_json",
        ).content
        parsed = _extract_first_json_object(raw if isinstance(raw, str) else str(raw))
        return _normalize_json_payload(parsed) if parsed else None
    except Exception:
        logger.exception(f"[{trace_id}] JSON 调用失败")
        return None

class IntentResult(BaseModel):
    intent: Literal["medical", "report", "general"]
    confidence: float
    reasoning: str = ""
    needs_web_search: bool = False
    search_query: str = ""


class AssessmentResult(BaseModel):
    triage_level: Literal["home_observation", "visit_within_24h", "clinic_soon", "emergency_now"]
    triage_reason: str
    trend_direction: Literal["worsening", "improving", "fluctuating", "stable", "unknown"] = "unknown"
    trend_reason: str = ""
    recommended_actions: Union[List[str], str] = Field(default_factory=list)
    warning_signals: Union[List[str], str] = Field(default_factory=list)
    constraint_warnings: Union[List[str], str] = Field(default_factory=list)
    age_band: str = ""


def _ensure_text_list(value: Union[List[str], str]) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parts = re.split(r"[；;\n、]+", text)
        return [part.strip() for part in parts if part.strip()]
    return []


def _build_assessment_payload(result: AssessmentResult) -> Dict[str, object]:
    return {
        "triageLevel": result.triage_level,
        "triageReason": result.triage_reason,
        "trendDirection": result.trend_direction,
        "trendReason": result.trend_reason,
        "recommendedActions": _ensure_text_list(result.recommended_actions),
        "warningSignals": _ensure_text_list(result.warning_signals),
        "constraintWarnings": _ensure_text_list(result.constraint_warnings),
        "ageBand": result.age_band,
    }


def calculate_pews(slots: dict[str, Any]) -> tuple[int, dict[str, int]]:
    """
    根据提取的 slots 槽位信息计算 PEWS (Pediatric Early Warning Score) 评分。
    PEWS 评分涵盖三个维度：精神行为表现 (Behavior)、心血管状态 (Cardiovascular)、呼吸状态 (Respiratory)。
    每个维度得分为 0~3 分，总分为 0~9 分。
    """
    def _is_negated(text: str, keyword: str) -> bool:
        """检查文本中的某个关键字是否被前置的否定修饰词所否定"""
        negation_words = ["没有", "无", "未见", "未出现", "排除", "不伴有", "非", "未伴随", "否认", "未曾", "无明显"]
        pos = 0
        while True:
            pos = text.find(keyword, pos)
            if pos == -1:
                break
            # 向前探查最多 6 个字
            start = max(0, pos - 6)
            prefix = text[start:pos]
            for neg in negation_words:
                if neg in prefix:
                    neg_pos = prefix.find(neg)
                    inter_text = prefix[neg_pos + len(neg):]
                    # 确保否定词和关键字之间没有标点符号阻断
                    if not any(punc in inter_text for punc in ["，", "。", "！", "？", ",", ".", "!", "?", ";", "；"]):
                        return True
            pos += len(keyword)
        return False

    scores = {"behavior": 0, "cardiovascular": 0, "respiratory": 0}
    
    # 1. 精神行为维度评估
    behavior_text = str(slots.get("behavior") or slots.get("mental_status") or "").lower()
    if behavior_text:
        # 3分：昏睡、对刺激反应极低/无反应、神志不清、谵妄、难以唤醒
        if any(kw in behavior_text and not _is_negated(behavior_text, kw) for kw in ["昏睡", "神志不清", "无反应", "谵妄", "难以唤醒", "唤不醒"]):
            scores["behavior"] = 3
        # 2分：难以唤醒、对刺激反应迟钝、极度萎靡、昏昏欲睡
        elif any(kw in behavior_text and not _is_negated(behavior_text, kw) for kw in ["反应迟钝", "极其萎靡", "嗜睡", "极其不好", "精神极差"]):
            scores["behavior"] = 2
        # 1分：精神萎靡、神志淡漠、爱哭闹、烦躁不安
        elif any(kw in behavior_text and not _is_negated(behavior_text, kw) for kw in ["萎靡", "淡漠", "烦躁", "哭闹", "精神差", "精神不好", "懒动"]):
            scores["behavior"] = 1
            
    # 2. 心血管与末梢循环维度评估
    cv_text = str(slots.get("cardiovascular") or slots.get("skin_circulation") or "").lower()
    if cv_text:
        # 3分：发绀、明显青紫、发紫、毛细血管再充盈时间 > 3秒
        if any(kw in cv_text and not _is_negated(cv_text, kw) for kw in ["发绀", "青紫", "发紫", "再充盈>3", "充盈大于3"]):
            scores["cardiovascular"] = 3
        # 2分：手脚冰凉、大理石样花纹、毛细血管再充盈 3 秒左右
        elif any(kw in cv_text and not _is_negated(cv_text, kw) for kw in ["冰凉", "冰冷", "凉", "大理石", "花纹", "再充盈3"]):
            scores["cardiovascular"] = 2
        # 1分：面色苍白、面色灰暗
        elif any(kw in cv_text and not _is_negated(cv_text, kw) for kw in ["苍白", "灰暗", "白", "无血色"]):
            scores["cardiovascular"] = 1
            
    # 3. 呼吸维度评估
    resp_text = str(slots.get("respiratory") or slots.get("respiratory_status") or "").lower()
    if resp_text:
        # 3分：叹气样呼吸、呼吸暂停、喘憋窒息、青紫
        if any(kw in resp_text and not _is_negated(resp_text, kw) for kw in ["叹气", "暂停", "发绀", "窒息", "喘憋", "青紫"]):
            scores["respiratory"] = 3
        # 2分：明显三凹征（锁骨上/肋间/剑突下凹陷）、明显呻吟、呼吸急促/困难
        elif any(kw in resp_text and not _is_negated(resp_text, kw) for kw in ["三凹征", "凹陷", "呻吟", "急促", "极快", "呼吸困难"]):
            scores["respiratory"] = 2
        # 1分：呼吸轻度增快、轻度三凹征、气促
        elif any(kw in resp_text and not _is_negated(resp_text, kw) for kw in ["气促", "稍快", "轻度三凹", "增快"]):
            scores["respiratory"] = 1
            
    total_score = sum(scores.values())
    return total_score, scores


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


def _looks_like_medical_query(text: str) -> bool:
    return bool(re.search(
        r"发烧|发热|咳嗽|腹泻|呕吐|皮疹|手足口病|支原体|肺炎|百日咳|麻疹|风疹|流感|指南|诊疗|预警|重症",
        text,
        re.IGNORECASE,
    ))


def _looks_like_knowledge_query(text: str) -> bool:
    return bool(re.search(
        r"指南|依据|重症预警|预警信号|是什么|有哪些|怎么判断|如何识别|说明",
        text,
        re.IGNORECASE,
    ))


def _is_growth_only_reply(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"[\d\.]+(个?月|岁)[、,，/]?[\d\.]+kg([、,，/]?[\d\.]+cm)?", compact, re.IGNORECASE):
        return True
    if re.fullmatch(r"[\d\.]+kg([、,，/]?[\d\.]+cm)?", compact, re.IGNORECASE):
        return True
    return False


def _recent_user_text(state: GraphState, limit: int = 2) -> str:
    recent_user_messages = [
        str(item.get("content", "")).strip()
        for item in state.get("history", [])
        if item.get("role") == "user" and str(item.get("content", "")).strip()
    ]
    tail = recent_user_messages[-limit:] if recent_user_messages else []
    current_messages = [str(item).strip() for item in state.get("messages", []) if str(item).strip()]
    return "\n".join([*tail, *current_messages])


QUERY_SYNONYM_MAP: Dict[str, List[str]] = {
    "拉肚子": ["腹泻", "小儿腹泻", "补液盐"],
    "拉稀": ["腹泻", "小儿腹泻", "补液盐"],
    "水样便": ["腹泻", "脱水", "补液盐"],
    "咳得厉害": ["咳嗽", "呼吸道感染", "肺炎预警"],
    "喘": ["喘息", "呼吸困难", "下呼吸道感染"],
    "起疹子": ["皮疹", "手足口病", "出疹性疾病"],
    "嘴唇发紫": ["发绀", "呼吸困难", "急症预警"],
    "不吃东西": ["进食差", "脱水风险", "精神反应差"],
}


def _estimate_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _truncate_history_for_model(
    history: List[dict],
    latest_message: str,
    patient_profile: str,
) -> List[dict]:
    max_tokens = int(os.environ.get("CHAT_HISTORY_MAX_TOKENS", "1800"))
    reserve_tokens = _estimate_token_count(latest_message) + _estimate_token_count(patient_profile)
    budget = max(400, max_tokens - reserve_tokens)
    selected: List[dict] = []
    running_tokens = 0
    for item in reversed(history):
        content = str(item.get("content", "")).strip()
        image_note = " [含图片]" if item.get("image") else ""
        item_tokens = _estimate_token_count(content + image_note)
        if selected and running_tokens + item_tokens > budget:
            break
        selected.append(item)
        running_tokens += item_tokens
    return list(reversed(selected))


def _apply_local_query_synonyms(query: str) -> str:
    expanded_terms: List[str] = []
    for alias, canonical_terms in QUERY_SYNONYM_MAP.items():
        if alias in query:
            expanded_terms.extend(canonical_terms)
    expanded_terms = [term for term in dict.fromkeys(expanded_terms) if term not in query]
    if not expanded_terms:
        return query
    return f"{query}；相关医学术语：{'、'.join(expanded_terms)}"


def _rewrite_medical_query(query: str, trace_id: str) -> str:
    base_query = _apply_local_query_synonyms(query)
    prompt = f"""你是儿科医学检索改写器。请把家长口语化提问改写为适合医学指南检索的短查询。
要求：
1. 保留原始症状与病程信息，不要编造新事实。
2. 可补充 2-5 个贴近临床指南的同义词或检索关键词。
3. 仅输出一个 JSON：{{"expanded_query":"..."}}。

原始问题：{query}
基础同义词扩展：{base_query}
"""
    parsed = _invoke_json_dict(prompt, trace_id)
    expanded_query = str(parsed.get("expanded_query", "")).strip() if parsed else ""
    if not expanded_query:
        return base_query
    if len(expanded_query) > 180:
        return expanded_query[:180]
    return expanded_query


def _normalize_ocr_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    items = payload.get("items")
    normalized_items: List[Dict[str, Any]] = []
    low_confidence_items: List[str] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            confidence_raw = item.get("confidence")
            try:
                confidence = float(confidence_raw) if confidence_raw is not None else 0.6
            except (TypeError, ValueError):
                confidence = 0.6
            confidence = max(0.0, min(confidence, 1.0))
            warning_flag = bool(item.get("warningFlag")) or confidence < 0.85
            normalized_item = {
                "name": str(item.get("name", "")).strip(),
                "result": str(item.get("result", "")).strip(),
                "unit": str(item.get("unit", "")).strip(),
                "referenceRange": str(item.get("referenceRange", "")).strip(),
                "isAbnormal": bool(item.get("isAbnormal")),
                "confidence": confidence,
                "warningFlag": warning_flag,
            }
            normalized_items.append(normalized_item)
            if warning_flag and normalized_item["name"]:
                low_confidence_items.append(normalized_item["name"])
    payload["items"] = normalized_items
    payload["needsManualReview"] = bool(low_confidence_items)
    payload["lowConfidenceItems"] = low_confidence_items
    if low_confidence_items and not payload.get("warningSummary"):
        payload["warningSummary"] = f"以下指标识别置信度偏低，请家长手动确认：{'、'.join(low_confidence_items)}"
    payload["overallConfidence"] = round(
        sum(item["confidence"] for item in normalized_items) / len(normalized_items),
        3,
    ) if normalized_items else 0.0
    return payload


def _build_user_fact_memory(slots: Dict[str, str], assessment: Optional[Dict[str, Any]]) -> str:
    facts: List[str] = []
    for key in ["age", "temperature", "duration", "mental_state", "breathing_state", "hydration", "frequency", "symptom"]:
        value = str(slots.get(key, "")).strip()
        if value:
            facts.append(f"{key}={value}")
    if assessment:
        triage_level = str(assessment.get("triageLevel", "")).strip()
        summary_text = str(assessment.get("summaryText", "")).strip()
        if triage_level:
            facts.append(f"triage={triage_level}")
        if summary_text:
            facts.append(f"summary={summary_text[:180]}")
    return "；".join(facts)


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


def _perform_web_search(query: str, trace_id: str) -> str:
    if not query:
        return ""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        logger.info(f"[{trace_id}] Web Search 完成: {query}")
        return "\n".join(
            [
                f"标题: {r.get('title')}\n来源: {r.get('href')}\n摘要: {r.get('body')}"
                for r in results
            ]
        )
    except Exception:
        logger.exception(f"[{trace_id}] web_search_tool 异常")
        return "搜索服务暂时不可用"


def _perform_rag_search(query: str, trace_id: str) -> Dict[str, Any]:
    try:
        context, citations = get_rag_engine().search(query, top_k=5)
        logger.info(f"[{trace_id}] RAG 检索完成，召回 {len(citations)} 条指南")
        if not citations:
            return {
                "context": "未检索到高置信度的权威指南依据。请基于保守的儿科安全原则回答，并明确提示家长线下就医。",
                "citations": [],
            }
        return {"context": context, "citations": citations}
    except Exception:
        logger.exception(f"[{trace_id}] rag_tool 异常")
        return {"context": "知识库暂时不可用，将基于通用知识回答。", "citations": []}


def _perform_ocr_extraction(image_data: str, trace_id: str) -> Dict[str, Any]:
    if not image_data:
        return {}
    logger.info(f"[{trace_id}] 进入 ocr_extraction_tool")
    llm = get_llm(is_vision=True)
    prompt = """请识别这张医学化验单，严格输出一段纯 JSON，不需要Markdown包裹，不需要解释：
{
  "hospitalName": "xxx医院",
  "date": "xxxx-xx-xx",
  "patientName": "姓名",
  "warningSummary": "",
  "items": [
    {
      "name": "白细胞",
      "result": "10.0",
      "unit": "10^9/L",
      "referenceRange": "4.0-10.0",
      "isAbnormal": false,
      "confidence": 0.93
    }
  ]
}
要求：
1. confidence 为 0.0 到 1.0。
2. 模糊、反光、单位不清或参考范围缺失时，confidence 必须下降。
3. 不确定时宁可低置信度，也不要编造。"""
    real_image = resolve_image(image_data)
    if not real_image:
        return {}
    try:
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": real_image}},
        ]
        res = _invoke_llm_with_retry(
            llm,
            [HumanMessage(content=user_content)],
            trace_id,
            "ocr",
        )
        content = res.content
        match = re.search(r"\{.*\}", str(content), re.DOTALL)
        if match:
            ocr_json = json.loads(match.group(0))
            logger.info(f"[{trace_id}] OCR 提取成功")
            return _normalize_ocr_result(ocr_json)
    except Exception:
        logger.exception(f"[{trace_id}] OCR 提取失败")
    return {}


def _build_agentic_tools(state: GraphState, trace_id: str, expanded_query: str) -> List[Any]:
    patient_profile = state.get("patient_profile", "").strip()
    patient_context = state.get("patient_context", {}) or {}
    image_data = state.get("image_data", "")
    latest_message = state["messages"][-1] if state.get("messages") else ""

    @tool("patient_profile_retriever")
    def patient_profile_retriever() -> str:
        """读取患儿结构化档案与关键上下文，仅在医学判断需要年龄、体重、过敏史时调用。"""
        return json.dumps(
            {
                "patientProfile": patient_profile,
                "patientContext": patient_context,
            },
            ensure_ascii=False,
        )

    @tool("expand_medical_query")
    def expand_medical_query_tool(raw_query: str) -> str:
        """将家长口语化医学问题扩展为适合指南检索的查询。"""
        rewritten = _rewrite_medical_query(raw_query or latest_message, trace_id)
        return json.dumps({"expandedQuery": rewritten}, ensure_ascii=False)

    @tool("search_guideline_rag")
    def search_guideline_rag(query: str) -> str:
        """检索权威医学指南，返回可追溯 citations 与 context。"""
        result = _perform_rag_search(query or expanded_query or latest_message, trace_id)
        return json.dumps(result, ensure_ascii=False)

    @tool("search_web_updates")
    def search_web_updates(query: str) -> str:
        """当需要最新资讯或最新政策时执行联网搜索。"""
        result = {"web_search_context": _perform_web_search(query or latest_message, trace_id)}
        return json.dumps(result, ensure_ascii=False)

    @tool("analyze_ocr_report")
    def analyze_ocr_report() -> str:
        """解析当前上传的检验报告/化验单图片，返回带置信度的结构化结果。"""
        result = _perform_ocr_extraction(image_data, trace_id)
        return json.dumps({"ocr_result": result}, ensure_ascii=False)

    return [
        patient_profile_retriever,
        expand_medical_query_tool,
        search_guideline_rag,
        search_web_updates,
        analyze_ocr_report,
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

    if _looks_like_medical_query(msg):
        logger.info(f"[{trace_id}] 规则命中医学问句，直接路由为 medical")
        return {
            "intent": "medical",
            "intent_confidence": 0.95,
            "needs_web_search": False,
            "search_query": "",
        }

    classify_prompt = f"""你是一名儿科问诊系统的意图分类器。
请以 JSON 结构化结果输出意图分类，不要输出任何额外解释文字。

意图类型：
- medical: 用户描述宝宝的症状、询问疾病、寻求医疗建议
- report: 用户上传了检验报告/化验单，要求解读，或者提到报告
- general: 育儿日常咨询、喂养问题、非医疗问题

用户输入："{msg}"

请判断意图并给出置信度（0.0~1.0）。如果用户的问题需要查询最新的新闻、医学突破、政策、或者通识事实库，请将 needs_web_search 设为 true，并在 search_query 中填入搜索词。
输出必须是合法 JSON。"""

    parsed = _invoke_json_dict(
        classify_prompt + "\n请仅输出一个 JSON 对象，不要输出数组，不要输出 markdown。",
        trace_id,
    )
    if parsed:
        intent = str(parsed.get("intent") or parsed.get("intent_type") or "general")
        confidence = float(parsed.get("confidence") or 0.0)
        needs_web_search = bool(parsed.get("needs_web_search") or parsed.get("need_web_search") or False)
        search_query = str(parsed.get("search_query") or parsed.get("query") or "")
        if intent not in {"medical", "report", "general"}:
            intent = "general"
        logger.info(f"[{trace_id}] 意图识别结果: {intent}, 置信度: {confidence}, 网搜: {needs_web_search}")
        return {
            "intent": intent,
            "intent_confidence": confidence,
            "needs_web_search": needs_web_search,
            "search_query": search_query,
        }
    return {"intent": "general", "intent_confidence": 0.0, "needs_web_search": False, "search_query": ""}

def route_after_router(state: GraphState) -> str:
    """条件路由：根据意图走向"""
    intent = state.get("intent", "general")
    if intent == "medical":
        return "emergency_guard"
    return "agentic_tools"


def emergency_guard_node(state: GraphState):
    """危险信号前置熔断：命中急症信号时不再继续普通问诊链路"""
    trace_id = state.get("trace_id", "unknown")
    patient_context = state.get("patient_context", {}) or {}
    latest_message = state["messages"][-1] if state.get("messages") else ""
    if _is_growth_only_reply(latest_message):
        logger.info(f"[{trace_id}] 当前输入是纯生长数据补充，跳过急症熔断")
        return {}

    recent_user_messages = [
        str(item.get("content", "")).strip()
        for item in state.get("history", [])
        if item.get("role") == "user" and str(item.get("content", "")).strip()
    ][-2:]
    if latest_message.strip():
        recent_user_messages.append(latest_message.strip())
    if recent_user_messages and all(_is_measurement_only_reply(text) for text in recent_user_messages):
        logger.info(f"[{trace_id}] 最近两轮均为纯指标/纯生长数据，跳过急症熔断")
        return {}

    merged_text = "\n".join(recent_user_messages)

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
    is_complete: bool = False
    filled_slots: Dict[str, str] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    followup_question: Optional[str]
    # AI 动态生成的快捷选项（最多 5 个），方便家长快速点击回答
    followup_options: Optional[List[str]] = None


def agentic_tools_node(state: GraphState):
    """局部 ReAct 工具调度节点：在最多 3 轮工具调用内收集检索/档案/OCR 上下文"""
    trace_id = state.get("trace_id", "unknown")
    intent = state.get("intent", "general")
    latest_message = state["messages"][-1] if state.get("messages") else ""
    base_query = state.get("slots", {}).get("symptom") or latest_message
    expanded_query = _rewrite_medical_query(base_query, trace_id) if intent in {"medical", "report"} else base_query
    tools = _build_agentic_tools(state, trace_id, expanded_query)
    tool_map = {tool_item.name: tool_item for tool_item in tools}
    llm = get_llm(is_vision=False).bind_tools(tools)

    system_prompt = """你是智慧儿科的工具调度代理。
目标：在最多 3 次工具调用内，为后续正式答复准备可靠上下文。
规则：
1. 医学问题优先考虑读取患儿档案；涉及临床依据时再做指南检索。
2. 用户上传化验单或提到报告时，优先调用 analyze_ocr_report。
3. 只有当问题明确需要最新资讯、政策或新闻时，才调用 search_web_updates。
4. 如需检索医学指南，先调用 expand_medical_query 再调用 search_guideline_rag。
5. 不要重复调用同一工具；拿到足够信息后立即停止。"""
    user_prompt = (
        f"用户意图: {intent}\n"
        f"用户当前问题: {latest_message}\n"
        f"槽位摘要: {state.get('slots', {})}\n"
        f"是否有图片: {bool(state.get('image_data'))}\n"
        f"当前推荐检索查询: {expanded_query}\n"
        "请按需调用工具。"
    )
    messages: List[Any] = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

    collected_context = state.get("context", "")
    collected_citations = list(state.get("citations", []) or [])
    collected_web_context = state.get("web_search_context", "")
    collected_ocr_result = state.get("ocr_result", {})
    tool_trace: List[str] = []
    total_tool_calls = 0

    for _ in range(3):
        ai_message = _invoke_llm_with_retry(llm, messages, trace_id, "agentic_tools")
        messages.append(ai_message)
        tool_calls = getattr(ai_message, "tool_calls", []) or []
        if not tool_calls:
            break
        for tool_call in tool_calls:
            if total_tool_calls >= 3:
                break
            tool_name = str(tool_call.get("name", ""))
            selected_tool = tool_map.get(tool_name)
            if not selected_tool:
                continue
            try:
                tool_result = selected_tool.invoke(tool_call.get("args", {}))
                parsed_result = _extract_first_json_object(str(tool_result)) or {}
                if tool_name == "expand_medical_query":
                    expanded_query = str(parsed_result.get("expandedQuery", expanded_query)).strip() or expanded_query
                    tool_trace.append(f"已扩展检索查询：{expanded_query}")
                elif tool_name == "search_guideline_rag":
                    collected_context = str(parsed_result.get("context", collected_context))
                    collected_citations = parsed_result.get("citations", collected_citations) or []
                    tool_trace.append(f"已检索指南，召回 {len(collected_citations)} 条参考依据")
                elif tool_name == "search_web_updates":
                    collected_web_context = str(parsed_result.get("web_search_context", collected_web_context))
                    tool_trace.append("已补充最新联网信息")
                elif tool_name == "analyze_ocr_report":
                    collected_ocr_result = parsed_result.get("ocr_result", collected_ocr_result) or {}
                    item_count = len(collected_ocr_result.get("items", [])) if isinstance(collected_ocr_result, dict) else 0
                    tool_trace.append(f"已解析化验单，提取 {item_count} 个指标")
                elif tool_name == "patient_profile_retriever":
                    tool_trace.append("已读取患儿历史档案")
                messages.append(
                    ToolMessage(
                        content=json.dumps(parsed_result, ensure_ascii=False),
                        tool_call_id=str(tool_call.get("id", "")),
                        name=tool_name,
                    )
                )
            except Exception:
                logger.exception(f"[{trace_id}] 工具调用失败: {tool_name}")
                messages.append(
                    ToolMessage(
                        content=json.dumps({"error": f"{tool_name} failed"}, ensure_ascii=False),
                        tool_call_id=str(tool_call.get("id", "")),
                        name=tool_name,
                    )
                )
            total_tool_calls += 1
        if total_tool_calls >= 3:
            break

    response: Dict[str, Any] = {
        "expanded_query": expanded_query,
        "agent_tool_trace": tool_trace,
    }
    if collected_context:
        response["context"] = collected_context
    if collected_citations:
        response["citations"] = collected_citations
    if collected_web_context:
        response["web_search_context"] = collected_web_context
    if collected_ocr_result:
        response["ocr_result"] = collected_ocr_result
    return response

def _inner_slot_filling_node(state: GraphState):
    """槽位填充节点内置处理函数"""
    trace_id = state.get("trace_id", "unknown")
    all_messages = state.get("messages", [])
    existing_slots = state.get("slots", {})
    
    conversation_text = "\n".join([f"家长的陈述: {m}" for m in all_messages])
    latest_message = all_messages[-1] if all_messages else ""
    category = _detect_symptom_category(conversation_text)
    template_slots = _extract_template_slots(conversation_text, existing_slots)

    if category != "general" and _looks_like_knowledge_query(latest_message):
        updated_slots = {**template_slots, "symptom_category": category}
        if "symptom" not in updated_slots:
            updated_slots["symptom"] = latest_message[:120]
        logger.info(f"[{trace_id}] 命中医学知识问句，跳过追问直接进入 RAG")
        return {"slots": {**updated_slots, "status": "filled"}}

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
    
    prompt = f"""请以 JSON 结构化输出分析以下完整的对话记录，提取儿科问诊关键信息。
必填信息：年龄/月龄、主诉症状
选填信息：体温、持续时长、大小便情况、以及以下用于 PEWS (儿童早期预警评分) 的客观指征字段：
  - behavior: 精神行为表现（正常/活跃、哭闹烦躁、精神萎靡、嗜睡、难以唤醒、昏睡无反应）
  - cardiovascular: 皮肤与循环表现（皮肤红润、面色苍白、手脚冰凉/大理石样花纹、发绀青紫/毛细血管再充盈时间长）
  - respiratory: 呼吸状态表现（呼吸平稳、气促/呼吸增快、吸气凹陷三凹征、呻吟、叹气样呼吸/呼吸暂停）

已知槽位信息（已从之前对话提取）：{existing_slots}

完整对话记录：
{conversation_text}

请判断是否已收集到足够信息（必填槽位均已填满）。
- 若信息不足，请给出一个温柔专业的追问句（followup_question）。
- 同时根据追问的内容，生成 3-5 个简洁 of 快捷回答选项（followup_options），方便家长直接点选。
  例如询问月龄时：["0-3个月", "4-6个月", "7-12个月", "1-3岁", "3岁以上"]
  例如询问体温时：["低热 37.3-38°C", "中热 38-39°C", "高热 39°C以上", "没有发烧"]
  选项必须是对追问的直接作答，不要出现与问题无关的内容。"""
    
    parsed = _invoke_json_dict(prompt + "\n请仅输出一个 JSON 对象，不要输出数组，不要输出 markdown。", trace_id)
    try:
        result = SlotStatus(**(parsed or {}))
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
    except Exception:
        logger.exception(f"[{trace_id}] _inner_slot_filling_node 异常")
        return {"slots": {"status": "error"}}


def _pews_emergency_check(slots_to_return: Dict[str, Any], patient_context: Dict[str, Any], trace_id: str) -> Dict[str, Any] | None:
    """PEWS 确定性评估过滤拦截"""
    pews_score, pews_details = calculate_pews(slots_to_return)
    # 如果总评分 >= 5，或者任意单个核心项为 3 分 (重度紧急)
    is_pews_emergency = (pews_score >= 5) or any(v == 3 for v in pews_details.values())
    
    if is_pews_emergency:
        logger.warning(f"[{trace_id}] 触发 PEWS 预警熔断，总分: {pews_score}, 详情: {pews_details}")
        
        reasons = []
        if pews_details["behavior"] == 3 or (pews_details["behavior"] >= 2 and pews_score >= 5):
            reasons.append("意识不清或精神极度萎靡")
        if pews_details["cardiovascular"] == 3 or (pews_details["cardiovascular"] >= 2 and pews_score >= 5):
            reasons.append("末梢循环极差或严重发绀/青紫")
        if pews_details["respiratory"] == 3 or (pews_details["respiratory"] >= 2 and pews_score >= 5):
            reasons.append("严重呼吸困难或呻吟/叹气样呼吸/呼吸暂停")
            
        triage_reason = "；".join(reasons) or "儿童早期预警评分(PEWS)达到重度危急线"
        
        assessment = _build_assessment_payload(
            AssessmentResult(
                triage_level="emergency_now",
                triage_reason=triage_reason,
                recommended_actions=[
                    "请立即前往最近的儿科急诊或呼叫 120 急救，不要继续等待线上问诊。",
                    "送医途中保持呼吸道畅通，避免自行喂服复杂药物。",
                    "尽量保暖并记录病情变化次数（如体温、呕吐次数）。"
                ],
                warning_signals=list(reasons),
                constraint_warnings=[],
                age_band=_get_age_band(patient_context)
            )
        )
        
        reply = (
            "### 紧急就医提示 (基于 PEWS 临床评估)\n"
            "- 当前分诊级别：**立即急诊 (重度危急)**\n"
            f"- 预警特征：{triage_reason} (PEWS 评分: {pews_score}分)\n"
            "- 建议：宝宝目前症状极其危急，请立即前往最近的医院儿科急诊，或立即拨打 120 呼叫救护车！\n\n"
            "> ⚠️ 免责声明：以上内容基于临床 PEWS 量表自动化评分，不能替代医师面诊，请以线下急诊诊断为准。"
        )
        
        # 将 slots["status"] 强置为 missing 迫使 route_after_slot_filling 路由走向 END
        # 同时回写 pews_score
        return {
            "slots": {**slots_to_return, "status": "missing"},
            "pews_score": pews_score,
            "assessment": assessment,
            "reply": reply
        }
    return None


def slot_filling_node(state: GraphState):
    """槽位填充节点：自动化追问关键体征，并内置 PEWS 重症熔断校验"""
    trace_id = state.get("trace_id", "unknown")
    patient_context = state.get("patient_context", {}) or {}
    slots_to_write = state.get("slots", {}) or {}
    
    # 1. 运行前置 PEWS 强熔断拦截（即使网络断开，依靠本地已有槽位数据也能保证安全就医）
    pews_emergency_output = _pews_emergency_check(slots_to_write, patient_context, trace_id)
    if pews_emergency_output:
        return pews_emergency_output
        
    # 2. 运行内置大模型槽位解析器
    output = _inner_slot_filling_node(state)
    
    # 3. 对大模型解析返回的最新 slots 结果，再次进行后置 PEWS 熔断检查
    latest_slots = output.get("slots", {})
    if latest_slots and latest_slots.get("status") != "error":
        post_pews_output = _pews_emergency_check(latest_slots, patient_context, trace_id)
        if post_pews_output:
            return post_pews_output
            
    return output

def route_after_slot_filling(state: GraphState) -> str:
    """条件路由：根据槽位状态走向"""
    status = state.get("slots", {}).get("status", "")
    if status == "missing":
        # 如果槽位缺失且已经生成了追问 reply，则提前结束 Graph
        return END
    return "agentic_tools"


def route_after_agentic_tools(state: GraphState) -> str:
    intent = state.get("intent", "general")
    if intent in {"medical", "report"}:
        return "triage_assessment"
    return "chat"


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

    prompt = f"""你是一名负责儿科线上分诊的资深医生，请根据用户描述、已提取槽位和档案信息，以 JSON 结构化输出分诊结论。

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
8. 输出必须是合法 JSON，不要附加说明文字
"""

    parsed = _invoke_json_dict(prompt + "\n请仅输出一个 JSON 对象，不要输出数组，不要输出 markdown。", trace_id)
    try:
        result = AssessmentResult(**(parsed or {}))
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
    query = state.get("expanded_query") or state.get("slots", {}).get("symptom") or (state["messages"][-1] if state["messages"] else "")
    return _perform_rag_search(str(query), trace_id)

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
    return {"ocr_result": _perform_ocr_extraction(image_data, trace_id)}

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
    citations = state.get("citations", []) or []
    citation_protocol_block = ""
    if citations:
        citation_lines = []
        for index, citation in enumerate(citations, start=1):
            title = str(citation.get("title", "指南来源"))
            chapter = str(citation.get("chapter", "") or "")
            confidence = citation.get("retrievalConfidence") or citation.get("score")
            line = f"[^{index}] {title}"
            if chapter:
                line += f" / {chapter}"
            if confidence is not None:
                line += f" / 检索置信: {confidence}"
            citation_lines.append(line)
        citation_protocol_block = (
            "\n\n【引用协议】\n"
            "如果你引用了下面的指南依据，正文中只能使用 `[^1]`、`[^2]` 这类脚注标记，且编号必须与下方列表完全一致。\n"
            "严禁编造不存在的引用编号，严禁输出列表之外的来源。\n"
            + "\n".join(citation_lines)
        )
    else:
        citation_protocol_block = (
            "\n\n【引用协议】\n"
            "当前没有检索到高置信度指南依据，不要伪造指南来源，不要输出任何 `[^n]` 引用编号。"
        )

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
{citation_protocol_block}

> ⚠️ 免责声明：以上解读仅供医学参考，不能替代执业医师面诊，不作为最终诊断依据！如指标异常明显或患儿症状严重，请立即前往线下医院就诊。"""

    elif intent == "medical":
        system_prompt = f"""你是一名拥有 20 年临床经验的儿科主任医师，当前时间：{current_time}。
请以专业、严谨且温柔的医生口吻回答家长的问题。

## 回答要求
1. **先思考后回答**：在回答正式开始前，请务必先将你的临床推理与分析过程包裹在 `<think>` 和 `</think>` 标签内输出。这必须是你思考的第一步！
   在思考区内，你必须且仅可使用【中文语法 + 英文术语】的专业推理逻辑，写下以下推导：
   - **【症状画像与剖析】**：梳理起病时间、核心体征与伴随症状，研判患儿发热、咳喘等严重程度。
   - **【指南对齐与鉴别诊断】**：比对已召回的儿科医学指南，列出疑似诊断和排除依据。
   - **【用药安全与合规核算】**：确保不推荐具体处方药品牌和剂量，核查是否存在超龄/超剂量安全红线。
   格式为：
<think>
(流式写下你的临床推理过程)
</think>

---
2. **精准性**：给出有据可查的医学建议，不猜测、不模糊
3. **结构化**：用分点列举，便于家长理解和记忆
4. **年龄敏感**：必须考虑患儿月龄/年龄对症状判断和处理方式的影响
5. **安全红线**：对于需要立即就医的紧急情况（高热惊厥、呼吸困难、口唇发紫等），必须第一句话就告知家长
6. **用药谨慎**：不给出具体药物剂量，建议家长遵医嘱
7. **引用严格**：只有在确实引用到检索结果时才使用 `[^citation_index]` 格式，不要编造脚注

参考医疗指南与外部知识：
{context_block}
--------------------
{citation_protocol_block}

> ⚠️ 免责声明：以上内容仅供医学参考，不能替代执业医师面诊，不作为最终诊断依据！情况紧急请立即前往线下医院就医。"""

    else:
        system_prompt = f"""你是一名资深儿科医生，同时也是「智慧儿科」平台的 AI 健康助手，当前时间：{current_time}。

## 你的定位
- 以温柔、专业的口吻与家长沟通日常育儿问题
- 涉及医学问题时，始终保持专业严谨，不做无根据的猜测
- 鼓励家长提供更多信息（如宝宝月龄、具体症状），以便给出更精准的建议
- 对于非医学问题（如喂养、作息、早教等），给出有科学依据的建议

## 先思考后回答（必填）
在给出正式建议前，请务必先将你的临床推理与分析过程包裹在 `<think>` 和 `</think>` 标签内输出。在思考区内，你应该客观理清以下要点：
- **【画像梳理】**：确认宝宝月龄/年龄及本次交互的育儿咨询核心。
- **【指南对齐】**：根据召回的常识或指南，梳理科学抚育建议。
- **【合规约束】**：自查是否有误作诊断或错误推荐药物的情况。
格式为：
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
{citation_protocol_block}
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
    history_data = _truncate_history_for_model(
        state.get("history", []),
        msg,
        patient_profile,
    )
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
            
        response = _invoke_llm_with_retry(llm, messages, trace_id, "chat")
        content = response.content.strip()
        logger.info(f"[{trace_id}] chat_node 生成完毕，长度: {len(content)}")
        
        if not content:
            logger.warning(f"[{trace_id}] 大模型生成了空字符串，触发兜底！")
            content = "【系统提示】抱歉，当前模型未能生成诊断总结，请尝试用文字补充说明您的问题。"

        # 提取 think 推理链并解耦最终回复
        clinical_reasoning = ""
        clean_reply = content
        think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL | re.IGNORECASE)
        if think_match:
            clinical_reasoning = think_match.group(1).strip()
            clean_reply = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
            
        return {
            "reply": clean_reply,
            "clinical_reasoning": clinical_reasoning
        }
    except Exception as e:
        logger.exception(f"[{trace_id}] chat_node 异常")
        return {"reply": "【系统提示】抱歉，系统暂时有些忙碌，未能生成回答，请稍后再试。"}

def reflection_node(state: GraphState):
    """自我审查节点：对生成的回答进行红线与合规审查"""
    trace_id = state.get("trace_id", "unknown")
    reply = state.get("reply", "")
    intent = state.get("intent", "general")
    count = state.get("reflection_count", 0)
    citations = state.get("citations", []) or []
    require_citation_protocol = intent in {"medical", "report"}
    local_violations = _evaluate_reply_safety(reply, citations, require_citation_protocol)
    
    # 只有医疗问题与报告解读才启动严格的自我审查，日常闲聊免检
    if intent not in {"medical", "report"}:
        logger.info(f"[{trace_id}] 非医疗意图，跳过自我审查")
        return {"reflection_count": count + 1, "reflection_feedback": "PASS"}
    if local_violations:
        feedback = "FAIL: " + "；".join(local_violations)
        next_count = count + 1
        logger.warning(f"[{trace_id}] 本地红线审查拦截成功: {feedback}")
        if next_count >= 2:
            return {
                "reflection_count": next_count,
                "reflection_feedback": feedback,
                "reply": _build_medical_redline_fallback(citations),
                "clinical_reasoning": "安全合规拦截：原思维推理触犯处方药/推荐剂量红线，已作废。",
            }
        return {"reflection_count": next_count, "reflection_feedback": feedback}
        
    llm = get_llm(is_vision=False)
    prompt = f"""
    你现在的身份是严苛的【儿科主任医师兼合规审核员】。
    请极其严格地审查下面 AI 助手的草稿回答。

    审查标准：
    1. 【红线】回答最末尾是否明确附带了类似“免责声明”、“不能替代执业医师面诊”等警告字样？
    2. 【红线】是否编造了不存在的药物或过度治疗方案？
    3. 【体验】语气是否足够温柔、关切？
    4. 【引用】如果回答中出现 `[^数字]` 引用编号，该编号是否全部落在 1 到 {len(citations)} 的范围内？

    待审查回答草稿：
    --------------------
    {reply}
    --------------------
    
    如果完全合格，请只输出 "PASS" 这四个字母，不要解释。
    如果有任何问题，请输出 "FAIL: [具体的不合格原因，并给出下一步如何修改的具体建议]"。
    """
    
    try:
        res = _invoke_llm_with_retry(
            llm,
            [HumanMessage(content=prompt)],
            trace_id,
            "reflection",
        ).content
        if res.strip().startswith("PASS"):
            logger.info(f"[{trace_id}] 自我审查 PASS")
            return {"reflection_count": count + 1, "reflection_feedback": "PASS"}
        else:
            logger.warning(f"[{trace_id}] 自我审查拦截成功! 意见: {res}")
            next_count = count + 1
            if next_count >= 2:
                return {
                    "reflection_count": next_count,
                    "reflection_feedback": res,
                    "reply": _build_medical_redline_fallback(citations),
                    "clinical_reasoning": "安全合规拦截：原思维推理触犯处方药/推荐剂量红线，已作废。",
                }
            return {"reflection_count": next_count, "reflection_feedback": res}
    except Exception:
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


def _cleanup_postgres_checkpointer() -> None:
    global _postgres_checkpointer_context, _postgres_checkpointer
    if _postgres_checkpointer_context is not None:
        _postgres_checkpointer_context.__exit__(None, None, None)
        _postgres_checkpointer_context = None
        _postgres_checkpointer = None


def _build_checkpointer():
    global _postgres_checkpointer_context, _postgres_checkpointer
    postgres_dsn = os.environ.get("LANGGRAPH_POSTGRES_DSN", "").strip()
    if postgres_dsn:
        from langgraph.checkpoint.postgres import PostgresSaver

        if _postgres_checkpointer is None:
            _postgres_checkpointer_context = PostgresSaver.from_conn_string(postgres_dsn)
            _postgres_checkpointer = _postgres_checkpointer_context.__enter__()
            _postgres_checkpointer.setup()
            atexit.register(_cleanup_postgres_checkpointer)
        return _postgres_checkpointer

    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()

def build_graph():
    """构建与编译拓扑图"""
    workflow = StateGraph(GraphState)
    
    workflow.add_node("router", router_node)
    workflow.add_node("emergency_guard", emergency_guard_node)
    workflow.add_node("slot_filling", slot_filling_node)
    workflow.add_node("agentic_tools", agentic_tools_node)
    workflow.add_node("triage_assessment", triage_assessment_node)
    workflow.add_node("chat", chat_node)
    workflow.add_node("reflection", reflection_node)
    
    # 设定起点
    workflow.set_entry_point("router")
    
    # 路由判断（medical → emergency_guard，其它交给 agentic_tools 做局部 ReAct 工具调度）
    workflow.add_conditional_edges("router", route_after_router, {
        "emergency_guard": "emergency_guard",
        "agentic_tools": "agentic_tools",
    })

    workflow.add_conditional_edges("emergency_guard", route_after_emergency_guard, {
        "slot_filling": "slot_filling",
        END: END
    })
    
    # 槽位判断
    workflow.add_conditional_edges("slot_filling", route_after_slot_filling, {
        "agentic_tools": "agentic_tools",
        END: END
    })

    workflow.add_conditional_edges("agentic_tools", route_after_agentic_tools, {
        "triage_assessment": "triage_assessment",
        "chat": "chat",
    })
    workflow.add_edge("triage_assessment", "chat")
    workflow.add_edge("chat", "reflection")
    workflow.add_conditional_edges("reflection", route_after_reflection, {
        "chat": "chat",
        END: END
    })

    checkpointer = _build_checkpointer()
    return workflow.compile(checkpointer=checkpointer)
