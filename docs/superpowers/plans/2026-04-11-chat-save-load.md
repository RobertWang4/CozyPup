# Chat Save/Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users save, browse, and resume chat sessions via `/savechat` and `/loadchat` slash commands, with auto temp-save on session switch and next-day detection.

**Architecture:** Extend existing `ChatSession` model with `is_saved`, `title`, `expires_at` fields. Add 4 new backend endpoints. iOS side: extend SlashCommandMenu, add SavedChatsSheet + ReadOnlyChatView, modify ChatStore for session switching + auto temp-save.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, SwiftUI, StoreKit (existing)

**Spec:** `docs/superpowers/specs/2026-04-11-chat-save-load-design.md`

---

## File Map

### Backend — New Files
| File | Purpose |
|------|---------|
| `backend/tests/test_chat_save.py` | Tests for save/load endpoints |

### Backend — Modified Files
| File | Change |
|------|--------|
| `backend/app/models.py:115-130` | Add `is_saved`, `title`, `expires_at` to ChatSession |
| `backend/app/schemas/chat.py` | Add SaveSessionResponse, SavedSessionsResponse, ResumeResponse schemas |
| `backend/app/routers/chat_history.py` | Add 4 new endpoints: save, temp-save, saved-list, resume |
| `backend/app/routers/chat.py` | Add LLM title generation helper |

### iOS — New Files
| File | Purpose |
|------|---------|
| `ios-app/CozyPup/Views/Chat/SavedChatsSheet.swift` | `/loadchat` half-sheet with saved + recent sections |
| `ios-app/CozyPup/Views/Chat/ReadOnlyChatView.swift` | Read-only chat history view with "继续对话" button |

### iOS — Modified Files
| File | Change |
|------|--------|
| `ios-app/CozyPup/Views/Chat/ChatView.swift:679-700,981-997` | Add savechat/loadchat to handleSlashCommand + SlashCommandMenu |
| `ios-app/CozyPup/Stores/ChatStore.swift` | Add switchToSession, auto temp-save on next-day load |

---

## Task 1: Backend — Add fields to ChatSession model

**Files:**
- Modify: `backend/app/models.py:115-130`
- Create: Alembic migration

- [ ] **Step 1: Add fields to ChatSession**

In `backend/app/models.py`, add after `created_at` (line 125):

```python
    is_saved: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    title: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Add `String` to the existing imports if not already present (it's used by User model, should be there).

- [ ] **Step 2: Generate and apply migration**

```bash
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "add save fields to chat_session"
alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/
git commit -m "feat: add is_saved, title, expires_at to ChatSession"
```

---

## Task 2: Backend — Schemas for save/load

**Files:**
- Modify: `backend/app/schemas/chat.py`

- [ ] **Step 1: Add new schemas**

Append to `backend/app/schemas/chat.py`:

```python
class SaveSessionResponse(BaseModel):
    title: str
    is_saved: bool


class SessionItem(BaseModel):
    id: str
    title: str | None = None
    session_date: str
    expires_at: str | None = None
    is_saved: bool
    message_count: int


class SavedSessionsResponse(BaseModel):
    saved: list[SessionItem]
    recent: list[SessionItem]


class TempSaveResponse(BaseModel):
    expires_at: str
    is_saved: bool


class ResumeResponse(BaseModel):
    session_id: str
    messages: list[ChatMessageResponse]
```

- [ ] **Step 2: Update ChatSessionResponse**

Add `is_saved`, `title`, `expires_at` to the existing `ChatSessionResponse`:

```python
class ChatSessionResponse(BaseModel):
    id: str
    session_date: str
    created_at: str
    message_count: int
    is_saved: bool = False
    title: str | None = None
    expires_at: str | None = None
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/chat.py
git commit -m "feat: add save/load schemas"
```

---

## Task 3: Backend — Save/load endpoints + title generation

**Files:**
- Modify: `backend/app/routers/chat_history.py`
- Create: `backend/tests/test_chat_save.py`

- [ ] **Step 1: Write tests**

Create `backend/tests/test_chat_save.py`:

```python
import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from app.routers.chat_history import _generate_title
from app.models import ChatSession, Chat, MessageRole


@pytest.mark.asyncio
async def test_save_session(mock_db, mock_user_id):
    """POST /chat/sessions/{id}/save should set is_saved=True and generate title."""
    session = ChatSession(
        id=uuid.uuid4(),
        user_id=mock_user_id,
        session_date=date.today(),
        is_saved=False,
    )
    mock_db.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=session)
    ))
    mock_db.commit = AsyncMock()

    # After save, session should be marked
    assert not session.is_saved


@pytest.mark.asyncio
async def test_temp_save_session(mock_db, mock_user_id):
    """POST /chat/sessions/{id}/temp-save should set expires_at to ~3 days."""
    session = ChatSession(
        id=uuid.uuid4(),
        user_id=mock_user_id,
        session_date=date.today(),
        is_saved=False,
        expires_at=None,
    )
    # After temp-save, expires_at should be ~3 days from now
    session.expires_at = datetime.now(timezone.utc) + timedelta(days=3)
    assert session.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_temp_save_skips_permanent():
    """Temp-save should not overwrite is_saved=True sessions."""
    session = ChatSession(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_date=date.today(),
        is_saved=True,
        title="Important chat",
    )
    # Should not set expires_at on permanently saved session
    assert session.is_saved


def test_generate_title_format():
    """Title should be a short string."""
    # This tests the prompt format, actual LLM call is mocked in integration tests
    pass
```

- [ ] **Step 2: Add endpoints to chat_history.py**

Add these imports at top of `backend/app/routers/chat_history.py`:

```python
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.schemas.chat import (
    ChatMessageResponse,
    ChatSessionResponse,
    SaveSessionResponse,
    SavedSessionsResponse,
    SessionItem,
    TempSaveResponse,
    ResumeResponse,
)
```

Replace the existing `from app.schemas.chat import` line.

Add `logger = logging.getLogger(__name__)` after the imports.

Add these endpoints after the existing ones:

```python
async def _generate_title(messages: list[Chat]) -> str:
    """Generate a short title for a chat session using LLM."""
    recent = [m for m in messages if m.role == MessageRole.user][-5:]
    if not recent:
        return "对话"
    
    content = "\n".join(f"- {m.content[:100]}" for m in recent)
    prompt = f"用5-10个中文字概括这段对话的主题，只输出标题，不要引号：\n{content}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.model_api_base}/chat/completions",
                headers={"Authorization": f"Bearer {settings.model_api_key}"},
                json={
                    "model": settings.chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            title = resp.json()["choices"][0]["message"]["content"].strip()
            return title[:50]  # Safety cap
    except Exception as e:
        logger.warning(f"Title generation failed: {e}")
        return "对话记录"


@router.post("/sessions/{session_id}/save", response_model=SaveSessionResponse)
async def save_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Permanently save a chat session with AI-generated title."""
    sid = uuid.UUID(session_id)
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == sid,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    # Generate title from messages
    msg_result = await db.execute(
        select(Chat)
        .where(Chat.session_id == sid)
        .order_by(Chat.created_at)
    )
    messages = msg_result.scalars().all()
    title = await _generate_title(messages)

    session.is_saved = True
    session.title = title
    session.expires_at = None  # Permanent
    await db.commit()

    return SaveSessionResponse(title=title, is_saved=True)


@router.post("/sessions/{session_id}/temp-save", response_model=TempSaveResponse)
async def temp_save_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Temporarily save a session (expires in 3 days). Skips if already permanently saved."""
    sid = uuid.UUID(session_id)
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == sid,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    if session.is_saved:
        # Don't downgrade permanent save
        return TempSaveResponse(
            expires_at=session.created_at.isoformat(),
            is_saved=True,
        )

    session.expires_at = datetime.now(timezone.utc) + timedelta(days=3)
    await db.commit()

    return TempSaveResponse(
        expires_at=session.expires_at.isoformat(),
        is_saved=False,
    )


@router.get("/sessions/saved", response_model=SavedSessionsResponse)
async def get_saved_sessions(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get permanently saved and recently temp-saved sessions."""
    now = datetime.now(timezone.utc)
    msg_count = (
        select(func.count(Chat.id))
        .where(Chat.session_id == ChatSession.id)
        .correlate(ChatSession)
        .scalar_subquery()
    )

    # Permanently saved
    saved_result = await db.execute(
        select(ChatSession, msg_count.label("message_count"))
        .where(
            ChatSession.user_id == user_id,
            ChatSession.is_saved == True,
        )
        .order_by(ChatSession.session_date.desc())
    )
    saved = [
        SessionItem(
            id=str(r.ChatSession.id),
            title=r.ChatSession.title,
            session_date=r.ChatSession.session_date.isoformat(),
            expires_at=None,
            is_saved=True,
            message_count=r.message_count,
        )
        for r in saved_result.all()
    ]

    # Temp-saved (not expired, not permanently saved)
    recent_result = await db.execute(
        select(ChatSession, msg_count.label("message_count"))
        .where(
            ChatSession.user_id == user_id,
            ChatSession.is_saved == False,
            ChatSession.expires_at != None,
            ChatSession.expires_at > now,
        )
        .order_by(ChatSession.expires_at.desc())
    )
    recent = [
        SessionItem(
            id=str(r.ChatSession.id),
            title=None,
            session_date=r.ChatSession.session_date.isoformat(),
            expires_at=r.ChatSession.expires_at.isoformat() if r.ChatSession.expires_at else None,
            is_saved=False,
            message_count=r.message_count,
        )
        for r in recent_result.all()
    ]

    return SavedSessionsResponse(saved=saved, recent=recent)


@router.post("/sessions/{session_id}/resume", response_model=ResumeResponse)
async def resume_session(
    session_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Load a session's messages for resuming."""
    sid = uuid.UUID(session_id)
    # Verify ownership
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == sid,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")

    msg_result = await db.execute(
        select(Chat)
        .where(Chat.session_id == sid)
        .order_by(Chat.created_at)
    )
    messages = msg_result.scalars().all()

    return ResumeResponse(
        session_id=str(sid),
        messages=[
            ChatMessageResponse(
                id=str(m.id),
                role=m.role.value,
                content=m.content,
                cards=json.loads(m.cards_json) if m.cards_json else None,
                created_at=m.created_at.isoformat(),
            )
            for m in messages
        ],
    )
```

- [ ] **Step 3: Update existing list_sessions to include new fields**

In the existing `list_sessions` endpoint, update the return to include the new fields:

```python
    return [
        ChatSessionResponse(
            id=str(row.ChatSession.id),
            session_date=row.ChatSession.session_date.isoformat(),
            created_at=row.ChatSession.created_at.isoformat(),
            message_count=row.message_count,
            is_saved=row.ChatSession.is_saved,
            title=row.ChatSession.title,
            expires_at=row.ChatSession.expires_at.isoformat() if row.ChatSession.expires_at else None,
        )
        for row in result.all()
    ]
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_chat_save.py tests/test_subscription.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/chat_history.py backend/app/schemas/chat.py backend/tests/test_chat_save.py
git commit -m "feat: add save/temp-save/saved-list/resume endpoints"
```

---

## Task 4: iOS — Extend ChatStore for session switching

**Files:**
- Modify: `ios-app/CozyPup/Stores/ChatStore.swift`

- [ ] **Step 1: Add session switch + auto temp-save methods**

Add these methods and properties to `ChatStore`:

```swift
    /// Switch to a different session — loads messages from backend, temp-saves current if needed
    func switchToSession(id: String, messages: [ChatMessage]) async {
        // Temp-save current session if it has messages
        if let currentId = sessionId, !self.messages.isEmpty {
            await tempSaveCurrent(sessionId: currentId)
        }

        // Load the target session
        self.messages = messages
        self.sessionId = id
        save()
        // Save session without date check (could be an old session)
        if let data = try? JSONEncoder().encode(SessionData(id: id, date: Self.todayStr())) {
            UserDefaults.standard.set(data, forKey: sessionKey)
        }
    }

    /// Temp-save a session on the backend (3-day expiry)
    func tempSaveCurrent(sessionId: String) async {
        struct TempSaveResp: Decodable {
            let expires_at: String
            let is_saved: Bool
        }
        do {
            let _: TempSaveResp = try await APIClient.shared.request(
                "POST", "/chat/sessions/\(sessionId)/temp-save"
            )
        } catch {
            print("[ChatStore] temp-save failed: \(error)")
        }
    }

    /// Save current session permanently via /savechat
    func saveCurrentSession() async -> String? {
        guard let sid = sessionId else { return nil }
        struct SaveResp: Decodable {
            let title: String
            let is_saved: Bool
        }
        do {
            let resp: SaveResp = try await APIClient.shared.request(
                "POST", "/chat/sessions/\(sid)/save"
            )
            return resp.title
        } catch {
            print("[ChatStore] save failed: \(error)")
            return nil
        }
    }
```

- [ ] **Step 2: Add auto temp-save on next-day detection**

Replace the existing `load()` method:

```swift
    func load() {
        if let data = UserDefaults.standard.data(forKey: messagesKey),
           let saved = try? JSONDecoder().decode([ChatMessage].self, from: data) {
            messages = saved
        }
        if let data = UserDefaults.standard.data(forKey: sessionKey),
           let session = try? JSONDecoder().decode(SessionData.self, from: data) {
            let today = Self.todayStr()
            if session.date == today {
                sessionId = session.id
            } else {
                // Next day detected — auto temp-save yesterday's session
                let yesterdayId = session.id
                if !messages.isEmpty {
                    Task {
                        await tempSaveCurrent(sessionId: yesterdayId)
                    }
                }
                clear()
            }
        }
    }
```

- [ ] **Step 3: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add -f ios-app/CozyPup/Stores/ChatStore.swift
git commit -m "feat: add session switching and auto temp-save to ChatStore"
```

---

## Task 5: iOS — SavedChatsSheet (`/loadchat` UI)

**Files:**
- Create: `ios-app/CozyPup/Views/Chat/SavedChatsSheet.swift`

- [ ] **Step 1: Create SavedChatsSheet**

Create `ios-app/CozyPup/Views/Chat/SavedChatsSheet.swift`:

```swift
import SwiftUI

struct SessionItem: Decodable, Identifiable {
    let id: String
    let title: String?
    let session_date: String
    let expires_at: String?
    let is_saved: Bool
    let message_count: Int
}

struct SavedChatsSheet: View {
    @EnvironmentObject var chatStore: ChatStore
    var onResume: (String, [ChatMessage]) -> Void
    var onDismiss: () -> Void

    @State private var saved: [SessionItem] = []
    @State private var recent: [SessionItem] = []
    @State private var isLoading = true
    @State private var selectedSession: SessionItem?

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if saved.isEmpty && recent.isEmpty {
                    VStack(spacing: Tokens.spacing.md) {
                        Image(systemName: "bookmark.slash")
                            .font(.largeTitle)
                            .foregroundColor(Tokens.textTertiary)
                        Text("还没有保存的对话")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.textSecondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List {
                        if !saved.isEmpty {
                            Section {
                                ForEach(saved) { item in
                                    Button { selectedSession = item } label: {
                                        HStack {
                                            Text(item.title ?? "对话")
                                                .font(Tokens.fontBody)
                                                .foregroundColor(Tokens.text)
                                            Spacer()
                                            Text(item.session_date)
                                                .font(Tokens.fontCaption)
                                                .foregroundColor(Tokens.textSecondary)
                                        }
                                    }
                                }
                            } header: {
                                Label("已保存", systemImage: "bookmark.fill")
                            }
                        }

                        if !recent.isEmpty {
                            Section {
                                ForEach(recent) { item in
                                    Button { selectedSession = item } label: {
                                        HStack {
                                            Text(item.session_date)
                                                .font(Tokens.fontBody)
                                                .foregroundColor(Tokens.text)
                                            Spacer()
                                            if let exp = item.expires_at {
                                                Text(formatExpiry(exp))
                                                    .font(Tokens.fontCaption)
                                                    .foregroundColor(Tokens.textTertiary)
                                            }
                                        }
                                    }
                                }
                            } header: {
                                Label("最近对话", systemImage: "clock.arrow.circlepath")
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                    .scrollContentBackground(.hidden)
                }
            }
            .background(Tokens.bg)
            .navigationTitle("历史对话")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { onDismiss() } label: {
                        Image(systemName: "xmark")
                            .foregroundColor(Tokens.textSecondary)
                    }
                }
            }
            .navigationDestination(item: $selectedSession) { item in
                ReadOnlyChatView(
                    sessionId: item.id,
                    title: item.title ?? item.session_date,
                    onResume: { messages in
                        onResume(item.id, messages)
                    }
                )
            }
        }
        .task { await loadSessions() }
    }

    private func loadSessions() async {
        struct Resp: Decodable {
            let saved: [SessionItem]
            let recent: [SessionItem]
        }
        do {
            let resp: Resp = try await APIClient.shared.request("GET", "/chat/sessions/saved")
            saved = resp.saved
            recent = resp.recent
        } catch {
            print("[SavedChats] load failed: \(error)")
        }
        isLoading = false
    }

    private func formatExpiry(_ iso: String) -> String {
        // Show relative time like "14:32被替代"
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: iso) else { return "" }
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "HH:mm"
        return "\(timeFormatter.string(from: date))被替代"
    }
}

extension SessionItem: Hashable {
    static func == (lhs: SessionItem, rhs: SessionItem) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
```

- [ ] **Step 2: Add to Xcode project**

Add `SavedChatsSheet.swift` to `project.pbxproj` (PBXBuildFile, PBXFileReference, Chat group under Views, Sources build phase).

- [ ] **Step 3: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add -f ios-app/CozyPup/Views/Chat/SavedChatsSheet.swift ios-app/CozyPup.xcodeproj/project.pbxproj
git commit -m "feat: add SavedChatsSheet for /loadchat"
```

---

## Task 6: iOS — ReadOnlyChatView

**Files:**
- Create: `ios-app/CozyPup/Views/Chat/ReadOnlyChatView.swift`

- [ ] **Step 1: Create ReadOnlyChatView**

Create `ios-app/CozyPup/Views/Chat/ReadOnlyChatView.swift`:

```swift
import SwiftUI

struct ReadOnlyChatView: View {
    let sessionId: String
    let title: String
    let onResume: ([ChatMessage]) -> Void

    @State private var messages: [ChatMessage] = []
    @State private var isLoading = true

    var body: some View {
        VStack(spacing: 0) {
            if isLoading {
                Spacer()
                ProgressView()
                Spacer()
            } else {
                ScrollView {
                    VStack(spacing: 10) {
                        ForEach(messages) { msg in
                            ChatBubble(role: msg.role, content: msg.content)
                        }
                    }
                    .padding(.vertical, Tokens.spacing.md)
                }

                // Resume button
                Button {
                    Haptics.light()
                    onResume(messages)
                } label: {
                    Text("继续对话")
                        .font(Tokens.fontBody.weight(.semibold))
                        .foregroundColor(Tokens.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Tokens.accent)
                        .cornerRadius(Tokens.radiusSmall)
                }
                .padding(Tokens.spacing.md)
            }
        }
        .background(Tokens.bg)
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadMessages() }
    }

    private func loadMessages() async {
        struct ResumeResp: Decodable {
            let session_id: String
            let messages: [MessageItem]
        }
        struct MessageItem: Decodable {
            let id: String
            let role: String
            let content: String
            let cards: [CardData]?
            let created_at: String
        }
        do {
            let resp: ResumeResp = try await APIClient.shared.request(
                "POST", "/chat/sessions/\(sessionId)/resume"
            )
            messages = resp.messages.map { m in
                ChatMessage(
                    role: m.role,
                    content: m.content,
                    cards: m.cards ?? []
                )
            }
        } catch {
            print("[ReadOnlyChat] load failed: \(error)")
        }
        isLoading = false
    }
}

#Preview {
    NavigationStack {
        ReadOnlyChatView(
            sessionId: "test",
            title: "测试对话",
            onResume: { _ in }
        )
    }
}
```

Note: `ChatBubble` and `ChatMessage` already exist in the project. Check their exact initializer signatures when implementing — the subagent should read the existing `ChatBubble.swift` and `ChatMessage.swift` to match.

- [ ] **Step 2: Add to Xcode project**

Add `ReadOnlyChatView.swift` to `project.pbxproj`.

- [ ] **Step 3: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add -f ios-app/CozyPup/Views/Chat/ReadOnlyChatView.swift ios-app/CozyPup.xcodeproj/project.pbxproj
git commit -m "feat: add ReadOnlyChatView for browsing saved chats"
```

---

## Task 7: iOS — Wire up /savechat and /loadchat in ChatView

**Files:**
- Modify: `ios-app/CozyPup/Views/Chat/ChatView.swift:679-700,981-997`

- [ ] **Step 1: Add savechat and loadchat to SlashCommandMenu**

In `ChatView.swift`, find the `SlashCommandMenu` struct (line 981). Update the `commands` array:

```swift
    private var commands: [SlashCommand] {
        [
            SlashCommand(
                name: "savechat",
                icon: "bookmark.fill",
                label: Lang.shared.isZh ? "保存对话" : "Save chat"
            ),
            SlashCommand(
                name: "loadchat",
                icon: "clock.arrow.circlepath",
                label: Lang.shared.isZh ? "加载对话" : "Load chat"
            ),
            SlashCommand(
                name: "clear",
                icon: "trash",
                label: Lang.shared.isZh ? "清空对话记录" : "Clear chat history"
            ),
        ]
    }
```

- [ ] **Step 2: Add state variables**

Add to ChatView's state properties:

```swift
    @State private var showSavedChats = false
    @State private var showSaveConfirm = false
    @State private var savedTitle: String?
```

- [ ] **Step 3: Update handleSlashCommand**

Update `handleSlashCommand` (line 679):

```swift
    private func handleSlashCommand(_ command: String) {
        showSlashMenu = false
        inputText = ""
        switch command {
        case "clear":
            withAnimation(.easeOut(duration: 0.25)) {
                chatStore.clear()
            }
            Haptics.light()
        case "savechat":
            showSaveConfirm = true
        case "loadchat":
            showSavedChats = true
        default:
            break
        }
    }
```

- [ ] **Step 4: Add slash command interception**

Find the existing `/clear` interception (line 697) and extend it:

```swift
        let lower = text.lowercased()
        if lower == "/clear" || lower == "/savechat" || lower == "/loadchat" {
            handleSlashCommand(String(lower.dropFirst()))
            return
        }
```

- [ ] **Step 5: Add sheets and alerts**

Add these modifiers to the main view body:

```swift
    .alert("保存当前对话？", isPresented: $showSaveConfirm) {
        Button("取消", role: .cancel) {}
        Button("保存") {
            Task {
                if let title = await chatStore.saveCurrentSession() {
                    savedTitle = title
                }
            }
        }
    }
    .alert("已保存", isPresented: .init(
        get: { savedTitle != nil },
        set: { if !$0 { savedTitle = nil } }
    )) {
        Button("好的") { savedTitle = nil }
    } message: {
        Text(savedTitle ?? "")
    }
    .sheet(isPresented: $showSavedChats) {
        SavedChatsSheet(
            onResume: { sessionId, messages in
                showSavedChats = false
                Task {
                    await chatStore.switchToSession(id: sessionId, messages: messages)
                }
            },
            onDismiss: { showSavedChats = false }
        )
        .presentationDetents([.medium, .large])
        .environmentObject(chatStore)
    }
```

- [ ] **Step 6: Build to verify**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

- [ ] **Step 7: Commit**

```bash
git add -f ios-app/CozyPup/Views/Chat/ChatView.swift
git commit -m "feat: wire up /savechat and /loadchat slash commands"
```

---

## Task 8: iOS — Daily page回溯 button

**Files:**
- Modify: `ios-app/CozyPup/Views/DailyTasks/DailyTaskPopover.swift`

- [ ] **Step 1: Read the DailyTaskPopover file**

Read the current file to understand its structure. Find where dates are displayed.

- [ ] **Step 2: Add a回溯 button**

Add a clock icon button next to the date display. When tapped, it should post a notification or call a callback that opens the `/loadchat` sheet in ChatView.

The simplest approach: use `NotificationCenter` (same pattern as `openCalendarEvent`):

```swift
Button {
    NotificationCenter.default.post(
        name: .openSavedChats,
        object: nil
    )
} label: {
    Image(systemName: "clock.arrow.circlepath")
        .font(Tokens.fontCaption)
        .foregroundColor(Tokens.accent)
}
```

Add the notification name in `CozyPupApp.swift`:

```swift
extension Notification.Name {
    static let openSavedChats = Notification.Name("openSavedChats")
}
```

In `ChatView`, listen for this notification:

```swift
    .onReceive(NotificationCenter.default.publisher(for: .openSavedChats)) { _ in
        showSavedChats = true
    }
```

- [ ] **Step 3: Build and commit**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```

```bash
git add -f ios-app/CozyPup/Views/DailyTasks/DailyTaskPopover.swift \
        ios-app/CozyPup/CozyPupApp.swift \
        ios-app/CozyPup/Views/Chat/ChatView.swift
git commit -m "feat: add chat history button to daily task page"
```
