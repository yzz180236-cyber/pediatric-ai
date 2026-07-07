import { View } from '@tarojs/components'
import ReactECharts from 'echarts-for-react'
import './index.scss'

interface GrowthChartProps {
  data: number[]
  months: string[]
}

const WHO_WEIGHT_REFERENCE = [
  { month: 0, p3: 2.5, p15: 2.8, p50: 3.3, p85: 3.9, p97: 4.4 },
  { month: 1, p3: 3.4, p15: 3.9, p50: 4.5, p85: 5.2, p97: 5.8 },
  { month: 2, p3: 4.3, p15: 4.8, p50: 5.6, p85: 6.4, p97: 7.1 },
  { month: 3, p3: 5.0, p15: 5.6, p50: 6.4, p85: 7.3, p97: 8.0 },
  { month: 4, p3: 5.6, p15: 6.2, p50: 7.0, p85: 7.9, p97: 8.7 },
  { month: 5, p3: 6.0, p15: 6.7, p50: 7.5, p85: 8.5, p97: 9.3 },
  { month: 6, p3: 6.4, p15: 7.1, p50: 7.9, p85: 8.9, p97: 9.8 },
  { month: 7, p3: 6.7, p15: 7.4, p50: 8.3, p85: 9.3, p97: 10.3 },
  { month: 8, p3: 6.9, p15: 7.7, p50: 8.6, p85: 9.6, p97: 10.6 },
  { month: 9, p3: 7.1, p15: 7.9, p50: 8.9, p85: 9.9, p97: 10.9 },
  { month: 10, p3: 7.4, p15: 8.2, p50: 9.2, p85: 10.2, p97: 11.2 },
  { month: 11, p3: 7.6, p15: 8.4, p50: 9.4, p85: 10.4, p97: 11.5 },
  { month: 12, p3: 7.7, p15: 8.6, p50: 9.6, p85: 10.6, p97: 11.7 },
]

export function GrowthChart({ data, months }: GrowthChartProps) {
  if (data.length === 0) {
    return (
      <View className="growth-chart-container growth-chart-empty">
        暂无体重记录
      </View>
    )
  }

  const normalizedMonths = months.map((month) => Number(month))
  const reference = normalizedMonths.map((monthValue) => {
    const hit = WHO_WEIGHT_REFERENCE.find((item) => item.month === monthValue)
    return hit ?? null
  })

  const options = {
    title: {
      text: '体重记录与 WHO 参考曲线',
      left: 'center',
      textStyle: { fontSize: 14, color: '#333' }
    },
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      data: months,
      name: '月龄',
    },
    yAxis: {
      type: 'value',
      name: '体重 (kg)',
      min: 0
    },
    series: [
      {
        name: 'WHO P3',
        data: reference.map((item) => item?.p3 ?? null),
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f2a7a0', type: 'dashed', width: 1 },
      },
      {
        name: 'WHO P15',
        data: reference.map((item) => item?.p15 ?? null),
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f6c28b', type: 'dashed', width: 1 },
      },
      {
        name: 'WHO P50',
        data: reference.map((item) => item?.p50 ?? null),
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#7eb6ff', width: 2 },
      },
      {
        name: 'WHO P85',
        data: reference.map((item) => item?.p85 ?? null),
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f6c28b', type: 'dashed', width: 1 },
      },
      {
        name: 'WHO P97',
        data: reference.map((item) => item?.p97 ?? null),
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#f2a7a0', type: 'dashed', width: 1 },
      },
      {
        name: '宝宝体重',
        data: data,
        type: 'line',
        smooth: true,
        lineStyle: { color: '#00bcd4', width: 3 },
        itemStyle: { color: '#00bcd4' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{
                offset: 0, color: 'rgba(0, 188, 212, 0.5)'
            }, {
                offset: 1, color: 'rgba(0, 188, 212, 0)'
            }]
          }
        }
      }
    ]
  }

  return (
    <View className="growth-chart-container">
      <ReactECharts option={options} style={{ height: '300px', width: '100%' }} />
    </View>
  )
}
