import Taro from '@tarojs/taro';
import { useUserStore } from '../store/userStore';

export const BASE_URL = (typeof process !== 'undefined' && process.env.TARO_APP_BFF_URL) ? process.env.TARO_APP_BFF_URL : 'http://localhost:3000/api/v1';
export const AI_ENGINE_URL = (typeof process !== 'undefined' && process.env.TARO_APP_AI_ENGINE_URL) ? process.env.TARO_APP_AI_ENGINE_URL : 'http://localhost:8000';

export const request = async <T = any>(
  url: string,
  options: Partial<Taro.request.Option> = {}
): Promise<T> => {
  const token = useUserStore.getState().token;
  
  const header = {
    ...options.header,
    'Content-Type': 'application/json',
  };

  if (token) {
    header['Authorization'] = `Bearer ${token}`;
  }

  // 本地高危词拦截
  if (options.data) {
    let dataStr = typeof options.data === 'string' ? options.data : '';
    try {
      dataStr = typeof options.data === 'object' ? JSON.stringify(options.data) : dataStr;
    } catch(e){}
    const { containsHighRiskWords } = await import('./security');
    if (containsHighRiskWords(dataStr)) {
      Taro.showToast({ title: '内容涉嫌违规，已拦截发送', icon: 'none' });
      throw new Error('Local security check failed');
    }
  }

  try {
    const response = await Taro.request({
      ...options,
      url: `${BASE_URL}${url}`,
      header,
    } as Taro.request.Option);

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response.data;
    } else if (response.statusCode === 401) {
      Taro.showToast({ title: '登录已过期，请重新登录', icon: 'none' });
      useUserStore.getState().clearToken();
      throw new Error('Unauthorized');
    } else if (response.statusCode === 429) {
      Taro.showToast({ title: '请求过快，请稍后再试', icon: 'none' });
      throw new Error('Too Many Requests');
    } else {
      Taro.showToast({ title: response.data?.message || '网络请求错误', icon: 'none' });
      throw new Error(response.data?.message || '网络请求错误');
    }
  } catch (err: any) {
    console.error('Request failed:', err);
    // 网络层断线 (例如服务器没起) 容错
    if (err?.errMsg && err.errMsg.includes('request:fail')) {
       Taro.showToast({ title: '无法连接到服务器，请检查网络', icon: 'none' });
    }
    throw err;
  }
};
