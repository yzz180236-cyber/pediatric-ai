import { View, Text } from '@tarojs/components'
import { Button } from '@nutui/nutui-react-taro'
import Taro from '@tarojs/taro'
import { request } from '../../utils/request'
import './index.scss'

export function DietaryFormCard({ payload, onAction }: any) {
  const handleSubmit = async () => {
    try {
      Taro.showLoading({ title: '同步排敏卡...' })
      await request('/patient/dietary', {
        method: 'POST',
        data: {
          recommendation: payload?.recommendation || '含铁米粉、果泥',
          allergy_warning: payload?.allergy_warning || '初次尝试请少量观察',
          added_food: '家长确认添加'
        }
      })
      Taro.hideLoading()
      Taro.showToast({ title: '计划已入档', icon: 'success' })
      if (onAction) onAction('accept_dietary')
    } catch (e) {
      Taro.hideLoading()
      Taro.showToast({ title: '入档失败', icon: 'error' })
    }
  }

  return (
    <View className="rich-card dietary-card">
      <View className="card-title"><Text>🍲 辅食添加评估</Text></View>
      <View className="card-content">
        <View><Text>根据宝宝目前的月龄，请您核对以下信息：</Text></View>
        <View className="info-row"><Text>推荐辅食:</Text> <Text className="val">{payload?.recommendation || '含铁米粉、果泥'}</Text></View>
        <View className="info-row"><Text>过敏提示:</Text> <Text className="val warning">{payload?.allergy_warning || '初次尝试请少量观察'}</Text></View>
      </View>
      <View className="card-actions">
        <Button size="small" type="primary" onClick={handleSubmit}>确认并加入电子排敏卡</Button>
      </View>
    </View>
  )
}
