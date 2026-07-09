import { View, Text } from '@tarojs/components'
import type { OcrResultPayload } from '@pediatric-ai/shared-types'
import './index.scss'

export function OcrResultCard({ payload }: { payload?: OcrResultPayload }) {
  const items = payload?.items || [];
  return (
    <View className="rich-card ocr-card">
      <View className="card-title"><Text>🔬 化验单智能分析</Text></View>
      {payload?.needsManualReview ? (
        <View className='ocr-warning-banner'>
          <Text>{payload.warningSummary || '部分指标识别置信度较低，请家长核对原始化验单后再采纳。'}</Text>
        </View>
      ) : null}
      <View className="ocr-table">
        <View className="ocr-row header">
          <Text className="col">指标</Text><Text className="col">结果</Text><Text className="col">参考值</Text><Text className="col confidence">置信度</Text>
        </View>
        {items.map((it: any, i: number) => (
          <View key={i} className={`ocr-row ${it.warningFlag ? 'warning-row' : ''}`}>
            <Text className="col">{it.name}</Text>
            <Text className={`col ${it.isAbnormal ? 'abnormal' : ''}`}>
              {it.result} {it.unit || ''} {it.isAbnormal && '↑'}
            </Text>
            <Text className="col">{it.referenceRange || '-'}</Text>
            <Text className={`col confidence ${it.warningFlag ? 'warning' : ''}`}>
              {typeof it.confidence === 'number' ? `${Math.round(it.confidence * 100)}%` : '-'}
            </Text>
          </View>
        ))}
      </View>
      <View className="card-footer">
        <Text>
          {typeof payload?.overallConfidence === 'number' ? `整体识别置信度 ${Math.round(payload.overallConfidence * 100)}%。` : ''}
          以上结果仅供参考，不作为最终诊断依据。
        </Text>
      </View>
    </View>
  )
}
