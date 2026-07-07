import { useEffect, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { Tabs, TabPane } from '@nutui/nutui-react-taro'
import { DoctorWorkbenchDto } from '@pediatric-ai/shared-types'
import { useUserStore } from '../../../store/userStore'
import { FollowupCard } from '../../../components/RichCards/FollowupCard'
import { ensureAuthenticated } from '../../../utils/auth'
import { request } from '../../../utils/request'
import './index.scss'

export default function DoctorWorkbench() {
  const role = useUserStore((state) => state.role)
  const [workbench, setWorkbench] = useState<DoctorWorkbenchDto | null>(null)
  const [loading, setLoading] = useState(true)

  useDidShow(() => {
    // 拦截鉴权，如果是普通用户强行进入则回退
    if (role !== 'doctor') {
      Taro.showToast({ title: '无权访问工作台', icon: 'none' })
      setTimeout(() => {
        Taro.redirectTo({ url: '/pages/index/index' })
      }, 1500)
    }
  })

  useEffect(() => {
    const loadWorkbench = async () => {
      if (role !== 'doctor') return
      try {
        await ensureAuthenticated()
        const data = await request<DoctorWorkbenchDto>('/doctor/workbench', {
          method: 'GET',
        })
        setWorkbench(data)
      } catch (error) {
        console.error('加载医生工作台失败', error)
      } finally {
        setLoading(false)
      }
    }

    loadWorkbench()
  }, [role])

  return (
    <View className="workbench-container">
      <View className="header">
        <Text className="title">医生工作台</Text>
        <Text className="subtitle">欢迎，Dr. Pediatrics</Text>
      </View>
      <View className="summary-strip">
        <View className="summary-item">
          <Text className="summary-value">{workbench?.summary.totalSessions ?? 0}</Text>
          <Text className="summary-label">近期会话</Text>
        </View>
        <View className="summary-item">
          <Text className="summary-value">{workbench?.summary.activePatients ?? 0}</Text>
          <Text className="summary-label">活跃患儿</Text>
        </View>
        <View className="summary-item">
          <Text className="summary-value">{workbench?.summary.dietaryAlerts ?? 0}</Text>
          <Text className="summary-label">排敏提醒</Text>
        </View>
      </View>
      <Tabs className="tabs-container">
        <TabPane title="预诊单列表" paneKey="1">
          <View className="list-content">
            {loading ? (
              <View className="empty-tips">加载中...</View>
            ) : workbench?.sessions.length ? (
              workbench.sessions.map((session) => (
                <View
                  key={session.sessionId}
                  className="workbench-card"
                  onClick={() => Taro.navigateTo({ url: `/pages/doctor/session-detail/index?id=${session.sessionId}` })}
                >
                  <Text className="card-title">患儿 {session.patientUserId.slice(0, 8)}</Text>
                  <Text className="card-line">状态：{session.status === 'followup' ? '待随访' : session.status === 'closed' ? '已处理' : '进行中'}</Text>
                  <Text className="card-line">最近消息：{session.latestMessagePreview}</Text>
                  <Text className="card-line">最后活跃：{new Date(session.lastActiveAt).toLocaleString()}</Text>
                  <Text className="card-line">过敏史：{session.knownAllergens || '未登记'}</Text>
                </View>
              ))
            ) : (
              <View className="empty-tips">暂无待处理预诊单</View>
            )}
          </View>
        </TabPane>
        <TabPane title="随访管理" paneKey="2">
          <View className="list-content">
            {workbench?.dietaryAlerts.length ? (
              workbench.dietaryAlerts.map((record) => (
                <View key={record.recordId} className="workbench-card">
                  <Text className="card-title">排敏提醒：{record.addedFood}</Text>
                  <Text className="card-line">提示：{record.allergyWarning}</Text>
                  <Text className="card-line">时间：{new Date(record.createdAt).toLocaleString()}</Text>
                </View>
              ))
            ) : (
              <FollowupCard payload={{ plan: '一周后复查血常规', notes: '注意观察是否起疹子' }} />
            )}
          </View>
        </TabPane>
      </Tabs>
    </View>
  )
}
