import { useEffect, useState } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { View, Text, Textarea, Picker, ScrollView } from '@tarojs/components'
import { Button, Input } from '@nutui/nutui-react-taro'
import { DietaryRecordDto, PatientProfileDto, UpdateDietaryRecordRequest, UpdatePatientProfileRequest } from '@pediatric-ai/shared-types'
import { ensureAuthenticated } from '../../utils/auth'
import { request } from '../../utils/request'
import { trackEvent } from '../../utils/tracker'
import { GrowthChart } from '../../components/GrowthChart'
import { useGrowthRecords } from '../index/hooks/useGrowthRecords'
import { GrowthRecordForm } from '../index/components/GrowthRecordForm'
import './index.scss'

function formatAgeLabel(birthday: string): string {
  if (!birthday) return '未填写'
  const birth = new Date(birthday)
  if (Number.isNaN(birth.getTime())) return '未填写'

  const now = new Date()
  const months = Math.max(
    0,
    Math.floor((now.getTime() - birth.getTime()) / (1000 * 60 * 60 * 24 * 30.44))
  )

  if (months < 24) {
    return `${months}个月`
  }

  const years = Math.floor(months / 12)
  const remainMonths = months % 12
  return remainMonths > 0 ? `${years}岁${remainMonths}个月` : `${years}岁`
}

export default function ProfilePage() {
  const router = useRouter()
  const readonly = router.params.readonly === '1'
  const targetUserId = router.params.userId || ''
  const backTo = router.params.backTo ? decodeURIComponent(router.params.backTo) : ''
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const [birthday, setBirthday] = useState('')
  const [gender, setGender] = useState(0)
  const [knownAllergens, setKnownAllergens] = useState('')
  const [medicalHistory, setMedicalHistory] = useState('')
  const [lastOcrSummary, setLastOcrSummary] = useState('')
  const [dietaryRecords, setDietaryRecords] = useState<DietaryRecordDto[]>([])
  const [editingDietaryId, setEditingDietaryId] = useState<string | null>(null)
  const [editingDietaryFood, setEditingDietaryFood] = useState('')
  const [editingDietaryRecommendation, setEditingDietaryRecommendation] = useState('')
  const [editingDietaryWarning, setEditingDietaryWarning] = useState('')
  const [dietarySaving, setDietarySaving] = useState(false)
  const [initialBirthday, setInitialBirthday] = useState('')
  const [initialDisplayName, setInitialDisplayName] = useState('')
  const [initialGender, setInitialGender] = useState(0)
  const [initialKnownAllergens, setInitialKnownAllergens] = useState('')
  const [activeGrowthMetric, setActiveGrowthMetric] = useState<'weight' | 'height'>('weight')
  const [showAllGrowthRecords, setShowAllGrowthRecords] = useState(false)
  const {
    growthRecords,
    newAgeMonths,
    setNewAgeMonths,
    newWeight,
    setNewWeight,
    newHeight,
    setNewHeight,
    editing,
    saving: growthSaving,
    handleAddRecord,
    handleEditRecord,
    handleCancelEdit,
    handleDeleteRecord,
  } = useGrowthRecords()
  const sortedGrowthRecords = [...growthRecords].sort((a, b) => {
    if (a.ageMonths !== b.ageMonths) {
      return a.ageMonths - b.ageMonths
    }
    return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
  })
  const heightGrowthRecords = sortedGrowthRecords.filter((record) => record.height !== null)
  const defaultVisibleGrowthCount = 4
  const visibleGrowthRecords =
    showAllGrowthRecords || sortedGrowthRecords.length <= defaultVisibleGrowthCount
      ? sortedGrowthRecords
      : sortedGrowthRecords.slice(-defaultVisibleGrowthCount)

  const loadProfile = async () => {
    try {
      await ensureAuthenticated()
      const profile = await request<PatientProfileDto>(
        readonly && targetUserId ? `/doctor/patients/${targetUserId}/profile` : '/patient/profile',
        { method: 'GET' }
      )
      setDisplayName(profile.displayName)
      setBirthday(profile.birthday)
      setGender(profile.gender)
      setKnownAllergens(profile.knownAllergens)
      setInitialDisplayName(profile.displayName)
      setInitialBirthday(profile.birthday)
      setInitialGender(profile.gender)
      setInitialKnownAllergens(profile.knownAllergens)
      setMedicalHistory(profile.medicalHistory)
      setLastOcrSummary(profile.lastOcrSummary)
      const dietary = await request<DietaryRecordDto[]>('/patient/dietary', {
        method: 'GET',
      })
      setDietaryRecords(dietary)
    } catch (error) {
      console.error('加载档案失败', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProfile()
  }, [])

  const handleSave = async () => {
    if (readonly) {
      return
    }

    if (!birthday) {
      Taro.showToast({ title: '请输入生日', icon: 'none' })
      return
    }

    setSaving(true)
    try {
      await ensureAuthenticated()
      const payload: UpdatePatientProfileRequest = {
        displayName: displayName.trim(),
        birthday,
        gender,
        knownAllergens: knownAllergens.trim(),
      }
      const profile = await request<PatientProfileDto>('/patient/profile', {
        method: 'PUT',
        data: payload,
      })
      setDisplayName(profile.displayName)
      setBirthday(profile.birthday)
      setGender(profile.gender)
      setKnownAllergens(profile.knownAllergens)
      setInitialDisplayName(profile.displayName)
      setInitialBirthday(profile.birthday)
      setInitialGender(profile.gender)
      setInitialKnownAllergens(profile.knownAllergens)
      setMedicalHistory(profile.medicalHistory)
      setLastOcrSummary(profile.lastOcrSummary)
      trackEvent('patient_profile_updated', {
        gender: profile.gender,
        hasAllergens: Boolean(profile.knownAllergens),
      })
      Taro.showToast({ title: '档案已保存', icon: 'success' })
    } catch (error) {
      console.error('保存档案失败', error)
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteDietaryRecord = async (record: DietaryRecordDto) => {
    const result = await Taro.showModal({
      title: '删除排敏记录',
      content: `确定删除「${record.addedFood}」这条电子排敏卡记录吗？`,
    })
    if (!result.confirm) return

    try {
      await ensureAuthenticated()
      await request<{ success: true }>(`/patient/dietary/${record.id}`, {
        method: 'DELETE',
      })
      setDietaryRecords((current) => current.filter((item) => item.id !== record.id))
      trackEvent('dietary_record_deleted', {
        recordId: record.id,
        addedFood: record.addedFood,
      })
      Taro.showToast({ title: '已删除', icon: 'success' })
    } catch (error) {
      console.error('删除排敏记录失败', error)
    }
  }

  const handleEditDietaryRecord = (record: DietaryRecordDto) => {
    if (readonly) return
    setEditingDietaryId(record.id)
    setEditingDietaryFood(record.addedFood)
    setEditingDietaryRecommendation(record.recommendation)
    setEditingDietaryWarning(record.allergyWarning)
  }

  const handleCancelDietaryEdit = () => {
    setEditingDietaryId(null)
    setEditingDietaryFood('')
    setEditingDietaryRecommendation('')
    setEditingDietaryWarning('')
  }

  const handleSaveDietaryRecord = async () => {
    if (readonly) return
    if (!editingDietaryId) return
    if (!editingDietaryFood.trim() || !editingDietaryRecommendation.trim() || !editingDietaryWarning.trim()) {
      Taro.showToast({ title: '请补全排敏记录', icon: 'none' })
      return
    }

    setDietarySaving(true)
    try {
      await ensureAuthenticated()
      const payload: UpdateDietaryRecordRequest = {
        addedFood: editingDietaryFood.trim(),
        recommendation: editingDietaryRecommendation.trim(),
        allergyWarning: editingDietaryWarning.trim(),
      }
      const updated = await request<DietaryRecordDto>(`/patient/dietary/${editingDietaryId}`, {
        method: 'PUT',
        data: {
          addedFood: payload.addedFood,
          recommendation: payload.recommendation,
          allergyWarning: payload.allergyWarning,
        },
      })
      setDietaryRecords((current) =>
        current.map((record) => (record.id === updated.id ? updated : record))
      )
      trackEvent('dietary_record_updated', {
        recordId: updated.id,
        addedFood: updated.addedFood,
      })
      handleCancelDietaryEdit()
      Taro.showToast({ title: '已更新', icon: 'success' })
    } catch (error) {
      console.error('更新排敏记录失败', error)
    } finally {
      setDietarySaving(false)
    }
  }

  const handleRefresh = async () => {
    setLoading(true)
    await loadProfile()
    Taro.showToast({ title: '已刷新档案', icon: 'success' })
  }

  const hasUnsavedProfileChanges =
    displayName.trim() !== initialDisplayName.trim() ||
    birthday !== initialBirthday ||
    gender !== initialGender ||
    knownAllergens.trim() !== initialKnownAllergens.trim()

  const handleBack = async () => {
    if (!hasUnsavedProfileChanges) {
      if (Taro.getCurrentPages().length > 1) {
        Taro.navigateBack()
        return
      }

      if (backTo) {
        Taro.redirectTo({ url: backTo })
        return
      }

      Taro.redirectTo({ url: '/pages/index/index' })
      return
    }

    const result = await Taro.showModal({
      title: '未保存修改',
      content: '宝宝档案有未保存的修改，确定现在返回吗？',
      confirmText: '仍然返回',
      cancelText: '继续编辑',
    })

    if (result.confirm) {
      if (Taro.getCurrentPages().length > 1) {
        Taro.navigateBack()
        return
      }

      if (backTo) {
        Taro.redirectTo({ url: backTo })
        return
      }

      Taro.redirectTo({ url: '/pages/index/index' })
    }
  }

  const ageLabel = formatAgeLabel(birthday)
  const profileCompletionCount = [birthday, knownAllergens.trim()].filter(Boolean).length + (gender !== 0 ? 1 : 0)
  const genderLabel = gender === 1 ? '男' : gender === 2 ? '女' : '未知'

  return (
    <View className='profile-page'>
      <View className='profile-topbar'>
        <View className='profile-back' onClick={handleBack}>
          返回
        </View>
        <View className='profile-topbar-title'>宝宝档案</View>
        <View className='profile-topbar-spacer' />
      </View>

      <ScrollView scrollY className='profile-scroll'>
        <View className='profile-card profile-card-spacing'>
          <View className='profile-title'>宝宝档案</View>
          <View className='profile-tip'>基础资料会参与问诊上下文与生长评估，请保持真实、及时更新。</View>

          <View className='profile-overview'>
            <View className='profile-overview-item'>
              <View className='profile-overview-label'>当前年龄</View>
              <View className='profile-overview-value'>{ageLabel}</View>
            </View>
            <View className='profile-overview-item'>
              <View className='profile-overview-label'>已填基础项</View>
              <View className='profile-overview-value'>{profileCompletionCount}/3</View>
            </View>
            <View className='profile-overview-item'>
              <View className='profile-overview-label'>性别状态</View>
              <View className='profile-overview-value'>{genderLabel}</View>
            </View>
          </View>

          <View className='profile-section'>
            <View className='profile-section-title'>基础资料</View>
            <View className='profile-section-tip'>请优先维护生日、性别和过敏信息，这些会直接影响问诊建议与生长评估。</View>
            <View className='profile-field'>
              <View className='profile-label'>生日</View>
              <Picker
                mode='date'
                value={birthday}
                start='2010-01-01'
                end={new Date().toISOString().slice(0, 10)}
                onChange={(event) => setBirthday(event.detail.value)}
              disabled={loading || readonly}
            >
                <View className={`profile-date-trigger ${loading ? 'disabled' : ''}`}>
                  <Text className={`profile-date-value ${birthday ? '' : 'placeholder'}`}>
                    {birthday || '请选择生日'}
                  </Text>
                </View>
              </Picker>
            </View>

            <View className='profile-field'>
              <View className='profile-label'>宝宝昵称</View>
              <Input
                value={displayName}
                onChange={setDisplayName}
                placeholder='例如：果果、米粒'
                className='profile-input'
                disabled={readonly}
              />
            </View>

            <View className='profile-field'>
              <View className='profile-label'>性别</View>
              <View className='profile-gender-row'>
                <View className={`profile-gender-chip ${gender === 0 ? 'active' : ''} ${readonly ? 'readonly' : ''}`} onClick={() => !readonly && setGender(0)}>
                  未知
                </View>
                <View className={`profile-gender-chip ${gender === 1 ? 'active' : ''} ${readonly ? 'readonly' : ''}`} onClick={() => !readonly && setGender(1)}>
                  男
                </View>
                <View className={`profile-gender-chip ${gender === 2 ? 'active' : ''} ${readonly ? 'readonly' : ''}`} onClick={() => !readonly && setGender(2)}>
                  女
                </View>
              </View>
            </View>

            <View className='profile-field'>
              <View className='profile-label'>已知过敏史</View>
              <Textarea
              className='profile-textarea'
              value={knownAllergens}
              placeholder='例如：鸡蛋、牛奶蛋白、花生'
              disabled={readonly}
              onInput={(event) => setKnownAllergens(event.detail.value)}
            />
              <View className='profile-field-hint'>建议按“食物名、反应、发生时间”方式记录，便于后续医生查看。</View>
            </View>
          </View>

          <View className='profile-section'>
            <View className='profile-section-title'>生长发育</View>
            <View className='profile-section-tip'>建议同步记录月龄、体重和身高，才能更完整地观察宝宝的生长发育趋势。</View>
            <View className='profile-field'>
              <View className='profile-label'>生长记录</View>
            {!readonly && (
              <GrowthRecordForm
                newAgeMonths={newAgeMonths}
                setNewAgeMonths={setNewAgeMonths}
                newWeight={newWeight}
                setNewWeight={setNewWeight}
                newHeight={newHeight}
                setNewHeight={setNewHeight}
                editing={editing}
                onCancelEdit={handleCancelEdit}
                saving={growthSaving}
                handleAddRecord={handleAddRecord}
              />
            )}
            </View>

            <View className='profile-field'>
              <View className='profile-label'>已保存生长记录</View>
              {sortedGrowthRecords.length > defaultVisibleGrowthCount && (
                <View className='profile-growth-toolbar'>
                  <View className='profile-growth-toolbar-copy'>
                    默认展示最近 {defaultVisibleGrowthCount} 条，避免记录过长影响浏览。
                  </View>
                  <View
                    className='profile-growth-toolbar-action'
                    onClick={() => setShowAllGrowthRecords((current) => !current)}
                  >
                    {showAllGrowthRecords ? '收起' : `查看全部 ${sortedGrowthRecords.length} 条`}
                  </View>
                </View>
              )}
              <View className='profile-growth-list'>
                {growthRecords.length === 0 ? (
                  <View className='profile-dietary-empty'>暂无生长记录</View>
                ) : (
                  visibleGrowthRecords.map((record, index) => {
                    const isLatest = sortedGrowthRecords[sortedGrowthRecords.length - 1]?.id === record.id
                    const isLastVisible = index === visibleGrowthRecords.length - 1

                    return (
                      <View key={record.id} className={`profile-growth-timeline-item ${isLatest ? 'is-latest' : ''}`}>
                        <View className='profile-growth-timeline-rail'>
                          <View className='profile-growth-timeline-dot' />
                          {!isLastVisible && <View className='profile-growth-timeline-line' />}
                        </View>
                        <View className='profile-growth-item'>
                          <View className='profile-growth-main'>
                            <View className='profile-growth-head'>
                              <View className='profile-growth-month'>{record.monthLabel}</View>
                              {isLatest && <View className='profile-growth-latest-badge'>最新</View>}
                            </View>
                            <View className='profile-growth-metrics'>
                              <Text className='profile-growth-metric'>{record.weight} kg</Text>
                              <Text className='profile-growth-divider'>·</Text>
                              <Text className='profile-growth-metric secondary'>
                                {record.height ? `${record.height} cm` : '未记录身高'}
                              </Text>
                            </View>
                          </View>
                          <View className='profile-growth-actions'>
                            {!readonly && (
                              <>
                                <View className='profile-growth-action edit' onClick={() => handleEditRecord(record)}>
                                  修改
                                </View>
                                <View className='profile-growth-action delete' onClick={() => handleDeleteRecord(record)}>
                                  删除
                                </View>
                              </>
                            )}
                          </View>
                        </View>
                      </View>
                    )
                  })
                )}
              </View>
            </View>

            <View className='profile-field'>
              <View className='profile-label'>近期生长发育曲线</View>
              <View className='profile-chart-card'>
                <View className='profile-chart-tabs'>
                  <View
                    className={`profile-chart-tab ${activeGrowthMetric === 'weight' ? 'active' : ''}`}
                    onClick={() => setActiveGrowthMetric('weight')}
                  >
                    体重
                  </View>
                  <View
                    className={`profile-chart-tab ${activeGrowthMetric === 'height' ? 'active' : ''}`}
                    onClick={() => setActiveGrowthMetric('height')}
                  >
                    身高
                  </View>
                </View>

                {activeGrowthMetric === 'weight' ? (
                  <GrowthChart
                    months={sortedGrowthRecords.map((record) => `${record.ageMonths}`)}
                    data={sortedGrowthRecords.map((record) => record.weight)}
                    metric='weight'
                  />
                ) : (
                  <GrowthChart
                    months={heightGrowthRecords.map((record) => `${record.ageMonths}`)}
                    data={heightGrowthRecords.map((record) => Number(record.height))}
                    metric='height'
                    title='身高记录'
                  />
                )}
              </View>
            </View>
          </View>

          <View className='profile-section'>
            <View className='profile-section-title'>排敏记录</View>
            <View className='profile-section-tip'>电子排敏卡用于记录“尝试了什么、系统给了什么提醒”，可随时更正或删除。</View>
            {!readonly && editingDietaryId && (
              <View className='profile-dietary-editor'>
                <View className='profile-label'>编辑电子排敏卡</View>
                <Input
                  value={editingDietaryFood}
                  onChange={setEditingDietaryFood}
                  placeholder='辅食名称'
                  className='profile-dietary-input'
                />
                <Input
                  value={editingDietaryRecommendation}
                  onChange={setEditingDietaryRecommendation}
                  placeholder='推荐内容'
                  className='profile-dietary-input profile-dietary-input-gap'
                />
                <Input
                  value={editingDietaryWarning}
                  onChange={setEditingDietaryWarning}
                  placeholder='过敏提示'
                  className='profile-dietary-input profile-dietary-input-gap'
                />
                <Button
                  type='primary'
                  block
                  loading={dietarySaving}
                  disabled={dietarySaving}
                  onClick={handleSaveDietaryRecord}
                  className='profile-dietary-save'
                >
                  {dietarySaving ? '保存中...' : '保存排敏卡'}
                </Button>
                <Button
                  block
                  disabled={dietarySaving}
                  onClick={handleCancelDietaryEdit}
                  className='profile-dietary-cancel'
                >
                  取消编辑
                </Button>
              </View>
            )}
            <View className='profile-field'>
              <View className='profile-label'>电子排敏卡记录</View>
              <View className='profile-dietary-list'>
                {dietaryRecords.length === 0 ? (
                  <View className='profile-dietary-empty'>暂无排敏记录</View>
                ) : (
                  dietaryRecords.map((record) => (
                    <View key={record.id} className='profile-dietary-item'>
                      <View className='profile-dietary-head'>
                        <View className='profile-dietary-food'>{record.addedFood}</View>
                        <View className='profile-dietary-actions'>
                          {!readonly && (
                            <>
                              <View
                                className='profile-dietary-edit'
                                onClick={() => handleEditDietaryRecord(record)}
                              >
                                编辑
                              </View>
                              <View
                                className='profile-dietary-delete'
                                onClick={() => handleDeleteDietaryRecord(record)}
                              >
                                删除
                              </View>
                            </>
                          )}
                        </View>
                      </View>
                      <View className='profile-dietary-text'>推荐：{record.recommendation}</View>
                      <View className='profile-dietary-text warning'>提示：{record.allergyWarning}</View>
                      <View className='profile-dietary-time'>
                        {new Date(record.createdAt).toLocaleString()}
                      </View>
                    </View>
                  ))
                )}
              </View>
            </View>
          </View>

          <View className='profile-section'>
            <View className='profile-section-title'>问诊摘要</View>
            <View className='profile-section-tip'>下面两块内容由系统自动沉淀，不能直接编辑，主要用于帮助你和医生快速回顾。</View>
            <View className='profile-field'>
              <View className='profile-label'>近期问诊摘要</View>
              <Textarea
                className='profile-textarea'
                value={medicalHistory || '暂无问诊摘要'}
                disabled
              />
            </View>

            <View className='profile-field'>
              <View className='profile-label'>最近化验单摘要</View>
              <Textarea
                className='profile-textarea'
                value={lastOcrSummary || '暂无化验单摘要'}
                disabled
              />
            </View>
          </View>

          <Button
            block
            disabled={loading}
            onClick={handleRefresh}
            className='profile-refresh-btn'
          >
            刷新档案
          </Button>
        </View>
      </ScrollView>

      {!readonly && (
        <View className='profile-bottom-bar'>
          <Button
            type='primary'
            block
            loading={saving}
            disabled={saving || loading || !hasUnsavedProfileChanges}
            onClick={handleSave}
            className={`profile-save-btn profile-save-btn-sticky ${hasUnsavedProfileChanges ? 'active' : 'inactive'}`}
          >
            {saving ? '保存中...' : '保存档案'}
          </Button>
        </View>
      )}
    </View>
  )
}
