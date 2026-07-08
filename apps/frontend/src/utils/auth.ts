import Taro from '@tarojs/taro';
import { useUserStore } from '../store/userStore';
import { BASE_URL } from './request';
import { trackEvent } from './tracker';

export const isH5Dev = process.env.TARO_ENV === 'h5' && process.env.NODE_ENV === 'development';

export async function wxLogin(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (isH5Dev && typeof window !== 'undefined') {
      reject(new Error('H5 开发环境请使用账号密码登录'));
      return;
    }

    Taro.login({
      success: async (res) => {
        if (!res.code) {
          reject(new Error('获取微信 code 失败'));
          return;
        }
        try {
          await doLogin(res.code);
          resolve();
        } catch (err) {
          reject(err);
        }
      },
      fail: (err) => {
        console.error('微信登录失败', err);
        reject(new Error('微信登录失败'));
      },
    });
  });
}

async function doLogin(code: string) {
  await loginWithPayload({ code });
}

export async function devLogin(username: string, password: string): Promise<void> {
  await loginWithPayload({ username, password });
  trackEvent('dev_login_success', { username, authSource: 'dev' });
}

export function logout(): void {
  const { role, authSource, userId } = useUserStore.getState();
  useUserStore.getState().clearToken();
  trackEvent('auth_logout', {
    role: role || 'unknown',
    authSource: authSource || 'unknown',
    userId: userId || 'unknown',
  });
}

export async function ensureAuthenticated(): Promise<string> {
  const existingToken = useUserStore.getState().token;
  if (existingToken) {
    return existingToken;
  }

  if (isH5Dev && typeof window !== 'undefined') {
    throw new Error('请先使用开发账号登录');
  }

  await wxLogin();
  const refreshedToken = useUserStore.getState().token;
  if (!refreshedToken) {
    throw new Error('登录失败，请重试');
  }
  return refreshedToken;
}

async function loginWithPayload(payload: Record<string, string>) {
  const response = await Taro.request({
    url: `${BASE_URL}/auth/login`,
    method: 'POST',
    data: payload,
  });

  if (response.statusCode !== 201 && response.statusCode !== 200) {
    throw new Error(response.data?.message || '登录请求失败');
  }

  const { accessToken, userId, authSource } = response.data as {
    accessToken: string;
    expiresIn: number;
    userId: string;
    authSource: string;
    role: string;
  };
  const { role } = response.data as {
    accessToken: string;
    expiresIn: number;
    userId: string;
    authSource: string;
    role: string;
  };
  useUserStore.getState().setToken(accessToken, role, userId, authSource);
  trackEvent('auth_login_success', { authSource, userId });
  console.log('登录成功，已获取 Token');
}
