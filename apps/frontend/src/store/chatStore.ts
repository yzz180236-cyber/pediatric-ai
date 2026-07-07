import { create } from 'zustand';
import { Message } from '@pediatric-ai/shared-types';

interface ChatState {
  currentSessionId: string | null;
  sessions: any[];
  messages: Message[];
  addMessage: (msg: Message) => void;
  updateMessage: (id: number, updater: (msg: Message) => Message) => void;
  setMessages: (msgs: Message[]) => void;
  clearMessages: () => void;
  setCurrentSessionId: (id: string | null) => void;
  setSessions: (sessions: any[]) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  currentSessionId: null,
  sessions: [],
  messages: [
    {
      id: 1,
      text: '你好，我是智慧儿科 AI 助手，请问宝宝今天有什么不适？',
      sender: 'ai',
    }
  ],
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  updateMessage: (id, updater) => set((state) => ({
    messages: state.messages.map(msg => msg.id === id ? updater(msg) : msg)
  })),
  setMessages: (msgs) => set({ messages: msgs }),
  clearMessages: () => set({ 
    messages: [{
      id: 1,
      text: '你好，我是智慧儿科 AI 助手，请问宝宝今天有什么不适？',
      sender: 'ai',
    }] 
  }),
  setCurrentSessionId: (id) => set({ currentSessionId: id }),
  setSessions: (sessions) => set({ sessions }),
}));
