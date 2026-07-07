import { View, Text } from '@tarojs/components'
import './index.scss'

export function OcrResultCard({ payload }: any) {
  const items = payload?.items || [
    { name: '白细胞', value: '12.5', reference: '4.0-10.0', isAbnormal: true },
    { name: '中性粒细胞', value: '75%', reference: '40%-70%', isAbnormal: true },
    { name: '血红蛋白', value: '120', reference: '110-160', isAbnormal: false }
  ];
  return (
    <View className="rich-card ocr-card">
      <View className="card-title"><Text>🔬 化验单智能分析</Text></View>
      <View className="ocr-table">
        <View className="ocr-row header">
          <Text className="col">指标</Text><Text className="col">结果</Text><Text className="col">参考值</Text>
        </View>
        {items.map((it: any, i: number) => (
          <View key={i} className="ocr-row">
            <Text className="col">{it.name}</Text>
            <Text className={`col ${it.isAbnormal ? 'abnormal' : ''}`}>
              {it.value || it.result} {it.isAbnormal && '↑'}
            </Text>
            <Text className="col">{it.reference || it.referenceRange}</Text>
          </View>
        ))}
      </View>
      <View className="card-footer"><Text>以上结果仅供参考，不作为最终诊断依据。</Text></View>
    </View>
  )
}
