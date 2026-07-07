/**
 * 智慧儿科前端数据打点与行为探针 (Tracker)
 * 用于商业化漏斗、核心留存事件分析
 */
declare global {
  interface Window {
    sensors?: {
      track: (eventName: string, payload: Record<string, unknown>) => void
    }
  }
}

export const trackEvent = (eventName: string, payload: Record<string, any> = {}) => {
  const eventData = {
    eventName,
    payload,
    timestamp: Date.now(),
    platform: process.env.TARO_ENV || 'h5',
  };
  
  // 在正式生产环境中，接入真实的上报 SDK
  if (process.env.NODE_ENV === 'production') {
    if (process.env.TARO_ENV === 'weapp' && typeof wx !== 'undefined' && wx.reportEvent) {
      wx.reportEvent(eventName, payload);
    } else if (typeof window !== 'undefined' && window.sensors) {
      window.sensors.track(eventName, payload);
    } else {
      console.log(`[Production Tracker] ${eventName}`, eventData);
    }
  } else {
    // 开发环境：在控制台高亮打印模拟打点请求，供测试验证
    console.log(`%c[Tracker 上报] ${eventName}`, 'color: #00d8a0; font-weight: bold;', eventData);
  }
};
