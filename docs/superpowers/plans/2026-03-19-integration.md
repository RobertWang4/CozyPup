# CozyPup Frontend ↔ Backend Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swap the frontend's localStorage mock layer for real backend API calls. After this, the app is production-ready.

**Prerequisites:**
- Frontend plan complete (`docs/superpowers/plans/2026-03-19-frontend.md`)
- Backend plan complete (`docs/superpowers/plans/2026-03-19-backend.md`)

**Spec:** `docs/superpowers/specs/2026-03-17-petcare-agent-design.md`

---

## Phase 1: API Client & Auth

---

### Task 1: API Client Module

**Files:**
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Write fetch wrapper**

`frontend/src/api/client.ts`:
- Base URL from env var (`VITE_API_URL`, defaults to `http://localhost:8000`)
- `authFetch(path, options)` — injects `Authorization: Bearer <token>` header
- Auto-refresh: on 401 response, attempt token refresh, retry once
- JSON parsing + error handling
- Export typed methods: `get<T>()`, `post<T>()`, `put<T>()`, `del()`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add API client with auth and token refresh"
```

---

### Task 2: Real Auth Flow

**Files:**
- Modify: `frontend/src/stores/authStore.ts`
- Create: `frontend/src/api/auth.ts`

- [ ] **Step 1: Write auth API module**

`frontend/src/api/auth.ts`:
- `signInWithApple()` — triggers Apple Sign In (Capacitor plugin), sends id_token to `POST /api/v1/auth/apple`
- `signInWithGoogle()` — triggers Google Sign In, sends to `POST /api/v1/auth/google`
- `refreshToken()` — sends refresh_token to `POST /api/v1/auth/refresh`
- Store tokens in Capacitor Secure Storage (iOS Keychain)

- [ ] **Step 2: Update authStore**

Replace mock `login()` with real OAuth → JWT flow. Keep the same `useAuth()` interface so components don't change.

- [ ] **Step 3: Install Capacitor plugins**

```bash
cd frontend && npm install @capacitor/secure-storage
# Apple Sign In: use Sign in with Apple JS or Capacitor plugin
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/auth.ts frontend/src/stores/authStore.ts frontend/package.json
git commit -m "feat: wire real auth flow with Apple/Google Sign In"
```

---

## Phase 2: Data Sync

---

### Task 3: Swap Pet Store to API

**Files:**
- Modify: `frontend/src/stores/petStore.ts`
- Create: `frontend/src/api/pets.ts`

- [ ] **Step 1: Write pets API module**

```typescript
// frontend/src/api/pets.ts
import { get, post, put, del } from './client';
import type { Pet } from '../types/pets';

export const petsApi = {
  list: () => get<Pet[]>('/api/v1/pets'),
  create: (data: Omit<Pet, 'id' | 'color' | 'createdAt'>) => post<Pet>('/api/v1/pets', data),
  update: (id: string, data: Partial<Pet>) => put<Pet>(`/api/v1/pets/${id}`, data),
  remove: (id: string) => del(`/api/v1/pets/${id}`),
};
```

- [ ] **Step 2: Update petStore**

Keep localStorage as local cache for offline/fast rendering. On mutations: call API first, then update local cache. On mount: fetch from API, update cache.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/pets.ts frontend/src/stores/petStore.ts
git commit -m "feat: swap pet store to API with local cache"
```

---

### Task 4: Swap Calendar Store to API

**Files:**
- Modify: `frontend/src/stores/calendarStore.ts`
- Create: `frontend/src/api/calendar.ts`

- [ ] **Step 1: Write calendar API module**

```typescript
// frontend/src/api/calendar.ts
import { get, put, del } from './client';
import type { CalendarEvent } from '../types/pets';

export const calendarApi = {
  getByRange: (start: string, end: string, petId?: string) =>
    get<CalendarEvent[]>(`/api/v1/calendar?start=${start}&end=${end}${petId ? `&pet_id=${petId}` : ''}`),
  update: (id: string, data: Partial<CalendarEvent>) => put<CalendarEvent>(`/api/v1/calendar/${id}`, data),
  remove: (id: string) => del(`/api/v1/calendar/${id}`),
};
```

- [ ] **Step 2: Update calendarStore**

Same pattern: API-first mutations, localStorage cache, fetch on mount.

- [ ] **Step 3: Remove demo seed data**

`seedDemoData()` is no longer needed — real data comes from backend via chat agent.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/calendar.ts frontend/src/stores/calendarStore.ts
git commit -m "feat: swap calendar store to API"
```

---

### Task 5: Wire Chat to Authenticated API

**Files:**
- Modify: `frontend/src/hooks/useChat.ts`

- [ ] **Step 1: Add auth header to SSE request**

In useChat's fetch call, add `Authorization: Bearer <token>` header. Get token from authStore.

- [ ] **Step 2: Update API URL**

Replace hardcoded `http://localhost:8000` with env var `VITE_API_URL`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useChat.ts
git commit -m "feat: wire chat to authenticated API"
```

---

## Phase 3: Push & Ship

---

### Task 6: Push Notification Registration

**Files:**
- Create: `frontend/src/hooks/usePushNotifications.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create push hook**

```typescript
// Register for push on app start (native only)
// Send device token to POST /api/v1/devices
// Handle notification received → navigate to relevant screen
```

- [ ] **Step 2: Wire into App.tsx**

Call hook on mount when authenticated.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/usePushNotifications.ts frontend/src/App.tsx
git commit -m "feat: add push notification registration"
```

---

### Task 7: AI Content Labeling & Report

**Files:**
- Modify: `frontend/src/components/ChatBubble.tsx`

- [ ] **Step 1: Add "AI" badge to assistant messages**

Small label or icon on AI messages indicating AI-generated content (App Store compliance).

- [ ] **Step 2: Add report button**

Long-press on AI message → "Report" option. Shows confirmation toast. Backend logging can be added later.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ChatBubble.tsx
git commit -m "feat: add AI labeling and report button"
```

---

### Task 8: End-to-End Verification

- [ ] **Step 1: Start both servers**

```bash
# Terminal 1: backend
cd backend && uvicorn app.main:app --reload

# Terminal 2: frontend
cd frontend && npm run dev
```

- [ ] **Step 2: Test full flow**

1. Login (Apple/Google) → JWT stored
2. Disclaimer popup → acknowledge
3. Add first pet → stored in DB
4. Chat → SSE streaming, auto-records to calendar
5. Open calendar drawer → real events from DB
6. Edit/delete calendar event → persists
7. Settings → real pet data, edit/delete/add works
8. Logout → clears tokens, returns to login

- [ ] **Step 3: Build iOS and test on device**

```bash
cd frontend && npm run build && npx cap sync ios && npx cap open ios
```

- [ ] **Step 4: Commit any fixes**

---

### Task 9: iOS Build & App Store Prep

- [ ] **Step 1: Configure Xcode**

- Set signing team
- Add Push Notification capability
- Add Apple Sign In capability
- Set app icons and launch screen

- [ ] **Step 2: Prepare App Store Connect**

- Screenshots (iPhone 15 Pro, iPhone 16 Pro Max)
- App description
- Privacy policy URL
- Data usage disclosure (chat content, pet info, location)

- [ ] **Step 3: TestFlight → App Store review**

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| **Phase 1** | Tasks 1-2 | API client, real auth (Apple/Google Sign In + JWT) |
| **Phase 2** | Tasks 3-5 | Swap stores: pets, calendar, chat to real API |
| **Phase 3** | Tasks 6-9 | Push notifications, compliance, E2E test, App Store |

**Total: 9 tasks.**
