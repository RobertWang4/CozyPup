import type { ChatMessage } from '../types/chat';

const MESSAGES_KEY = 'cozypup_chat_messages';
const SESSION_KEY = 'cozypup_chat_session';

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

export const chatStore = {
  saveMessages(messages: ChatMessage[]) {
    localStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
  },

  loadMessages(): ChatMessage[] {
    try {
      const raw = localStorage.getItem(MESSAGES_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  },

  clearMessages() {
    localStorage.removeItem(MESSAGES_KEY);
    localStorage.removeItem(SESSION_KEY);
  },

  saveSessionId(id: string) {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ id, date: todayStr() }));
  },

  loadSessionId(): string | null {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      const { id, date } = JSON.parse(raw);
      if (date !== todayStr()) {
        localStorage.removeItem(SESSION_KEY);
        localStorage.removeItem(MESSAGES_KEY);
        return null;
      }
      return id;
    } catch {
      return null;
    }
  },
};
