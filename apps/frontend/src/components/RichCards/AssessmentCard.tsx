import { AssessmentPayload } from "@pediatric-ai/shared-types";
import { View, Text } from "@tarojs/components";
import { Button } from "@nutui/nutui-react-taro";

const TRIAGE_META: Record<AssessmentPayload["triageLevel"], { label: string; tone: string }> = {
  home_observation: { label: "居家观察", tone: "safe" },
  visit_within_24h: { label: "24小时内就医", tone: "warning" },
  clinic_soon: { label: "尽快门诊", tone: "warning-strong" },
  emergency_now: { label: "立即急诊", tone: "danger" },
};

const TREND_LABELS: Record<NonNullable<AssessmentPayload["trendDirection"]>, string> = {
  worsening: "较前加重",
  improving: "较前缓解",
  fluctuating: "反复波动",
  stable: "暂无明显变化",
  unknown: "趋势暂不明确",
};

const EVIDENCE_LABELS = {
  guideline: "指南引用",
  safety_rule: "安全规则",
  model_inference: "模型推断",
} as const;

export function AssessmentCard({
  payload,
  onAction,
}: {
  payload?: AssessmentPayload;
  onAction?: (action: string, payload?: unknown) => void;
}) {
  if (!payload) return null;
  const meta = TRIAGE_META[payload.triageLevel] || TRIAGE_META.home_observation;

  return (
    <View className={`rich-card assessment-card ${meta.tone}`}>
      <View className="card-title">智能分诊结果</View>
      <View className="assessment-head">
        <Text className={`assessment-badge ${meta.tone}`}>{meta.label}</Text>
        <Text className="assessment-age-band">{payload.ageBand || "年龄信息不足"}</Text>
      </View>

      <View className="card-content">
        <Text className="assessment-label">分诊原因</Text>
        <Text className="assessment-text">{payload.triageReason}</Text>
      </View>

      {payload.trendDirection && (
        <View className="card-content">
          <Text className="assessment-label">病程趋势</Text>
          <Text className="assessment-text">
            {TREND_LABELS[payload.trendDirection] || "趋势暂不明确"}
          </Text>
          {payload.trendReason ? (
            <Text className="assessment-list-item muted">- {payload.trendReason}</Text>
          ) : null}
        </View>
      )}

      {payload.recommendedActions?.length > 0 && (
        <View className="card-content">
          <Text className="assessment-label">建议动作</Text>
          {payload.recommendedActions.map((item, index) => (
            <Text key={`${item}-${index}`} className="assessment-list-item">
              {index + 1}. {item}
            </Text>
          ))}
        </View>
      )}

      {payload.warningSignals?.length > 0 && (
        <View className="card-content">
          <Text className="assessment-label">危险信号</Text>
          <Text className="assessment-warning">{payload.warningSignals.join("、")}</Text>
        </View>
      )}

      {payload.constraintWarnings?.length > 0 && (
        <View className="card-content">
          <Text className="assessment-label">安全约束提醒</Text>
          {payload.constraintWarnings.map((item, index) => (
            <Text key={`${item}-${index}`} className="assessment-list-item muted">
              - {item}
            </Text>
          ))}
        </View>
      )}

      {payload.evidenceLayers?.length ? (
        <View className="card-content">
          <Text className="assessment-label">证据来源分层</Text>
          {payload.evidenceLayers.map((layer, index) => (
            <View key={`${layer.sourceType}-${index}`} className="assessment-evidence-item">
              <Text className={`assessment-evidence-badge ${layer.sourceType}`}>
                {EVIDENCE_LABELS[layer.sourceType] || layer.sourceType}
              </Text>
              <Text className="assessment-list-item">{layer.content}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <View className="card-actions-row">
        <Button size="small" type="default" onClick={() => onAction?.("mark_followup", payload)}>
          标记随访
        </Button>
        <Button size="small" type="primary" onClick={() => onAction?.("request_doctor_review", payload)}>
          提交医生复核
        </Button>
      </View>
    </View>
  );
}
