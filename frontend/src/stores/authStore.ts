import { useSyncExternalStore } from 'react';

const AUTH_KEY = 'cozypup_auth';
const DISCLAIMER_KEY = 'cozypup_disclaimer';

interface AuthState {
  isAuthenticated: boolean;
  user: { name: string; email: string } | null;
  hasAcknowledgedDisclaimer: boolean;
}

type Listener = () => void;

let state: AuthState = {
  isAuthenticated: false,
  user: null,
  hasAcknowledgedDisclaimer: false,
};
const listeners = new Set<Listener>();

function loadAuth(): Partial<AuthState> {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveAuth() {
  localStorage.setItem(
    AUTH_KEY,
    JSON.stringify({ isAuthenticated: state.isAuthenticated, user: state.user })
  );
}

function emit() {
  for (const l of listeners) l();
}

// Initialize
const saved = loadAuth();
state = {
  isAuthenticated: saved.isAuthenticated ?? false,
  user: saved.user ?? null,
  hasAcknowledgedDisclaimer: localStorage.getItem(DISCLAIMER_KEY) === 'true',
};

export const authStore = {
  subscribe(listener: Listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  getSnapshot(): AuthState {
    return state;
  },

  login(provider: 'apple' | 'google') {
    const mockUsers = {
      apple: { name: 'Apple User', email: 'user@icloud.com' },
      google: { name: 'Google User', email: 'user@gmail.com' },
    };
    state = { ...state, isAuthenticated: true, user: mockUsers[provider] };
    saveAuth();
    emit();
  },

  logout() {
    state = { isAuthenticated: false, user: null, hasAcknowledgedDisclaimer: false };
    localStorage.removeItem(AUTH_KEY);
    localStorage.removeItem(DISCLAIMER_KEY);
    emit();
  },

  acknowledgeDisclaimer() {
    state = { ...state, hasAcknowledgedDisclaimer: true };
    localStorage.setItem(DISCLAIMER_KEY, 'true');
    emit();
  },

  hasSeenDisclaimer(): boolean {
    return state.hasAcknowledgedDisclaimer;
  },
};

export function useAuth(): AuthState {
  return useSyncExternalStore(authStore.subscribe, authStore.getSnapshot);
}
