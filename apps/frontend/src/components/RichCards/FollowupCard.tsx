import { View, Text } from '@tarojs/components'
import { Button } from '@nutui/nutui-react-taro'
import './index.scss'

export function FollowupCard({ payload, onAction }: any) {
  return (
    <View className="rich-card followup-card">
      <View className="card-title"><Text>🩺 诊后随访打卡</Text></View>
      <View className="card-content">
        <View><Text>距上次问诊已过 {payload?.hours_passed || 24} 小时。</Text></View>
        <View><Text>宝宝现在的精神状态和体温如何？</Text></View>
      </View>
      <View className="card-actions-row">
        <Button size="small" type="primary" onClick={() => onAction && onAction('followup_normal')}>已退烧，精神好</Button>
        <Button size="small" type="default" onClick={() => onAction && onAction('followup_abnormal')}>仍发烧，精神差</Button>
      </View>
    </View>
  )
}
