import { useEffect, useState } from 'react'
import { ScrollView, Text, Textarea, View } from '@tarojs/components'
import { Button } from '@nutui/nutui-react-taro'
import { DoctorWorkbenchSessionDetailDto, UpdateDoctorSessionRequest } from '@pediatric-ai/shared-types'
import Taro, { useRouter } from '@tarojs/taro'
import { ensureAuthenticated } from '../../../utils/auth'
import { request } from '../../../utils/request'
import './index.scss'

export default function DoctorSessionDetailPage() {
  const router = useRouter()
  const sessionId = router.params.id || ''
  const [detail, setDetail] = useState<DoctorWorkbenchSessionDetailDto | null>(null)
  const [status, setStatus] = useState<'active' | 'followup' | 'closed'>('active')
  const [doctorNote, setDoctorNote] = useState('')
  const [saving, setSaving] = useState(false)

  const handleBack = () => {
    if (Taro.getCurrentPages().length > 1) {
      Taro.navigateBack()
      return
    }

    Taro.redirectTo({ url: '/pages/doctor/workbench/index' })
  }

  useEffect(() => {
    const loadDetail = async () => {
      if (!sessionId) return
      try {
        await ensureAuthenticated()
        const data = await request<DoctorWorkbenchSessionDetailDto>(`/doctor/workbench/sessions/${sessionId}`, {
          method: 'GET',
        })
        setDetail(data)
        setStatus(data.status)
        setDoctorNote(data.doctorNote)
      } catch (error) {
        console.error('加载会话详情失败', error)
        Taro.showToast({ title: '加载会话详情失败', icon: 'none' })
      }
    }

    loadDetail()
  }, [sessionId])

  const handleSave = async () => {
    if (!sessionId) return
    setSaving(true)
    try {
      await ensureAuthenticated()
      const payload: UpdateDoctorSessionRequest = {
        status,
        doctorNote: doctorNote.trim(),
      }
      const updated = await request<DoctorWorkbenchSessionDetailDto>(`/doctor/workbench/sessions/${sessionId}`, {
        method: 'PUT',
        data: payload,
      })
      setDetail(updated)
      setStatus(updated.status)
      setDoctorNote(updated.doctorNote)
      Taro.showToast({ title: '已保存处理状态', icon: 'success' })
    } catch (error) {
      console.error('保存医生处理状态失败', error)
      Taro.showToast({ title: '保存失败', icon: 'none' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <ScrollView scrollY className='doctor-session-page'>
      <View className='doctor-session-topbar'>
        <View className='doctor-session-back' onClick={handleBack}>
          返回
        </View>
        <View className='doctor-session-topbar-title'>会话详情</View>
        <View className='doctor-session-topbar-spacer' />
      </View>

      <View className='doctor-session-card'>
        <View className='doctor-session-title'>患儿会话概览</View>
        <Text className='doctor-session-line'>宝宝称呼：{detail?.patientDisplayName || '加载中...'}</Text>
        <Text className='doctor-session-line'>患儿 ID：{detail?.patientUserId || '加载中...'}</Text>
        <Text className='doctor-session-line'>生日：{detail?.patientBirthday || '未登记'}</Text>
        <Text className='doctor-session-line'>性别：{detail?.patientGender === 1 ? '男' : detail?.patientGender === 2 ? '女' : '未知'}</Text>
        <Text className='doctor-session-line'>过敏史：{detail?.knownAllergens || '未登记'}</Text>
        <Text className='doctor-session-line'>处理状态：{status === 'followup' ? '待随访' : status === 'closed' ? '已处理' : '进行中'}</Text>
        <Text className='doctor-session-line'>最近活跃：{detail ? new Date(detail.lastActiveAt).toLocaleString() : '加载中...'}</Text>
        {detail?.patientUserId && (
          <Button
            block
            onClick={() =>
              Taro.navigateTo({
                url: `/pages/profile/index?readonly=1&userId=${detail.patientUserId}&backTo=${encodeURIComponent(
                  `/pages/doctor/session-detail/index?id=${sessionId}`
                )}`,
              })
            }
            className='doctor-session-profile-btn'
          >
            查看患儿档案（只读）
          </Button>
        )}
      </View>

      <View className='doctor-session-card'>
        <View className='doctor-session-subtitle'>医生处理</View>
        <View className='doctor-session-status-row'>
          <View className={`doctor-session-status-chip ${status === 'active' ? 'active' : ''}`} onClick={() => setStatus('active')}>
            进行中
          </View>
          <View className={`doctor-session-status-chip ${status === 'followup' ? 'active' : ''}`} onClick={() => setStatus('followup')}>
            待随访
          </View>
          <View className={`doctor-session-status-chip ${status === 'closed' ? 'active' : ''}`} onClick={() => setStatus('closed')}>
            已处理
          </View>
        </View>
        <Textarea
          className='doctor-session-note'
          value={doctorNote}
          placeholder='记录你的处理意见、复诊提醒或随访要求'
          onInput={(event) => setDoctorNote(event.detail.value)}
        />
        <Button type='primary' block loading={saving} disabled={saving} onClick={handleSave}>
          {saving ? '保存中...' : '保存处理状态'}
        </Button>
      </View>

      <View className='doctor-session-card'>
        <View className='doctor-session-subtitle'>病情摘要</View>
        <Text className='doctor-session-line'>{detail?.medicalHistory || '暂无问诊摘要'}</Text>
      </View>

      <View className='doctor-session-card'>
        <View className='doctor-session-subtitle'>最近化验单摘要</View>
        <Text className='doctor-session-line'>{detail?.lastOcrSummary || '暂无化验单摘要'}</Text>
      </View>

      <View className='doctor-session-card'>
        <View className='doctor-session-subtitle'>会话消息</View>
        {detail?.messages.length ? (
          detail.messages.map((message) => (
            <View key={message.id} className={`doctor-session-message ${message.sender}`}>
              <Text className='doctor-session-message-role'>{message.sender === 'user' ? '家长' : 'AI'}</Text>
              <Text className='doctor-session-message-text'>{message.content}</Text>
              <Text className='doctor-session-message-time'>{new Date(message.createdAt).toLocaleString()}</Text>
            </View>
          ))
        ) : (
          <Text className='doctor-session-line'>暂无消息</Text>
        )}
      </View>
    </ScrollView>
  )
}
