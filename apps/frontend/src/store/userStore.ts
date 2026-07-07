import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import Taro from '@tarojs/taro';

interface UserState {
  token: string | null;
  userId: string | null;
  role: string | null;
  authSource: string | null;
  setToken: (token: string, role?: string, userId?: string | null, authSource?: string | null) => void;
  clearToken: () => void;
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      token: null, // ← 绝对不能是 'test-token'
      userId: null,
      role: null,
      authSource: null,
      setToken: (token, role, userId, authSource) =>
        set({ token, role: role || 'user', userId: userId || null, authSource: authSource || null }),
      clearToken: () => set({ token: null, userId: null, role: null, authSource: null }),
    }),
    {
      name: 'user-store',
      storage: {
        getItem: (key) => Taro.getStorageSync(key),
        setItem: (key, value) => Taro.setStorageSync(key, value),
        removeItem: (key) => Taro.removeStorageSync(key),
      },
    }
  )
);
