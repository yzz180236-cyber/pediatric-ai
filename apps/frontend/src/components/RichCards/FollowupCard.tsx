import { View, Text } from '@tarojs/components'
import { Button } from '@nutui/nutui-react-taro'
import './index.scss'

export function FollowupCard({ payload, onAction }: any) {
  const question = payload?.question || '请补充更多宝宝当前情况。'
  const options: string[] = Array.isArray(payload?.options) && payload.options.length > 0
    ? payload.options
    : ['已退烧，精神好', '仍发烧，精神差']

  return (
    <View className="rich-card followup-card">
      <View className="followup-head">
        <View className="followup-head-main">
          <Text className="followup-title">智能追问</Text>
          <Text className="followup-subtitle">还缺 1 条关键信息</Text>
        </View>
        <View className="followup-badge">
          <Text>继续补充</Text>
        </View>
      </View>

      <View className="followup-question-card">
        <Text className="followup-question-label">当前需要确认</Text>
        <Text className="followup-question-text">{question}</Text>
      </View>

      <View className="followup-tip">
        <Text>点击下方选项可直接回填，不用手动再输入。</Text>
      </View>

      <View className="followup-options">
        {options.map((option, index) => (
          <Button
            key={`${option}-${index}`}
            size="small"
            fill="outline"
            color={index === 0 ? '#5b6ee1' : '#7a8299'}
            onClick={() => onAction && onAction('followup_option_selected', { option })}
            className={`followup-option ${index === 0 ? 'is-primary' : ''}`}
          >
            {option}
          </Button>
        ))}
      </View>
    </View>
  )
}
