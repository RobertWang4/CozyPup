# Settings & Profile Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Settings drawer and Profile sheet so every button maps to a real backend API or native action, close the Apple compliance gaps (Restore Purchases / Manage Subscription / Terms of Use), add user-editable avatar upload, and add a Duo Plan linked-friend row.

**Architecture:** Two parallel tracks — (A) Backend: extend `GET /auth/me` with `avatar_url` and add `POST /auth/me/avatar` multipart upload; (B) iOS: restructure `SettingsDrawer` + `UserProfileSheet` against a single `AppConfig.swift` constants file with new supporting views (`SafariWebView`, `ShareSheet`, `ReleaseNotes`, `AcknowledgementsView`, `WhatsNewView`, `DuoPlanSection`). Tracks merge at the QA matrix verification task.

**Tech Stack:** FastAPI, SQLAlchemy, pydantic, pytest; SwiftUI, StoreKit 2, PhotosPicker, SFSafariViewController, UIActivityViewController.

**Spec:** `docs/superpowers/specs/2026-04-12-settings-profile-redesign-design.md`

---

## File Structure

### Backend — new / modified

- **Modify** `backend/app/schemas/auth.py` — add `avatar_url: str | None` to `UserResponse`.
- **Modify** `backend/app/routers/auth.py` — return `avatar_url` from `GET /auth/me` and `PATCH /auth/me`; add `POST /auth/me/avatar`.
- **Modify** `backend/app/storage.py` — add `upload_user_avatar(user_id, data, content_type)`.
- **Create** `backend/tests/test_auth_me.py` — unit tests for `GET /auth/me`, `PATCH /auth/me`, `POST /auth/me/avatar`.

### iOS — new

- **Create** `ios-app/CozyPup/AppConfig.swift` — single source of truth for support email, legal URLs, App Store URL.
- **Create** `ios-app/CozyPup/Views/Shared/SafariWebView.swift` — `SFSafariViewController` UIKit wrapper.
- **Create** `ios-app/CozyPup/Views/Shared/ShareSheet.swift` — `UIActivityViewController` wrapper.
- **Create** `ios-app/CozyPup/Views/Settings/DuoPlanSection.swift` — reusable section with friend row / upgrade row.
- **Create** `ios-app/CozyPup/Views/Settings/WhatsNewView.swift` — static release notes page.
- **Create** `ios-app/CozyPup/Views/Settings/AcknowledgementsView.swift` — static dependency list.
- **Create** `ios-app/CozyPup/ReleaseNotes.swift` — hardcoded release notes data.

### iOS — modified

- **Modify** `ios-app/CozyPup/Stores/AuthStore.swift` — decode `avatar_url` in `/auth/me` fetch; add `updateAvatar(url:)` and `updateName(_:)` helpers.
- **Modify** `ios-app/CozyPup/Views/Settings/UserProfileSheet.swift` — avatar upload via PhotosPicker, new Subscription section, DuoPlanSection, Legal URL buttons, Terms of Use added.
- **Modify** `ios-app/CozyPup/Views/Settings/SettingsDrawer.swift` — remove Subscription row, remove 3 notification toggles, add Preferences / Notifications / Support / About sections, fix version label.

---

## Execution Order & Parallelism

Tasks 1–4 (backend) and Tasks 5–13 (iOS) are **independent** up to Task 14 (integration + QA). A subagent team can run the two tracks in parallel. Task 14 requires both tracks complete.

---

## Task 1: Backend — Add `avatar_url` to `UserResponse` schema and `GET /auth/me`

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/routers/auth.py:110-149`
- Create: `backend/tests/test_auth_me.py`

- [ ] **Step 1: Write the failing test for `GET /auth/me` avatar_url presence**

Create `backend/tests/test_auth_me.py`:

```python
"""Tests for /auth/me endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import User


def _make_user(name="Alice", email="a@ex.com", provider="google", avatar_url=""):
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = email
    user.name = name
    user.auth_provider = provider
    user.avatar_url = avatar_url
    user.phone_number = None
    return user


class TestGetMe:
    @pytest.mark.asyncio
    async def test_get_me_returns_avatar_url(self):
        from app.routers.auth import me

        user = _make_user(avatar_url="https://storage.googleapis.com/cozypup-avatars/users/abc/1.jpg")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result

        resp = await me(user_id=user.id, db=db)
        assert resp.avatar_url == "https://storage.googleapis.com/cozypup-avatars/users/abc/1.jpg"

    @pytest.mark.asyncio
    async def test_get_me_empty_avatar_url_returns_none(self):
        from app.routers.auth import me

        user = _make_user(avatar_url="")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result

        resp = await me(user_id=user.id, db=db)
        assert resp.avatar_url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_auth_me.py::TestGetMe -v`
Expected: FAIL — `UserResponse` has no `avatar_url` attribute.

- [ ] **Step 3: Add `avatar_url` to `UserResponse` schema**

Edit `backend/app/schemas/auth.py`, change the `UserResponse` class to:

```python
class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    avatar_url: str | None = None
    auth_provider: str
    phone_number: str | None
```

- [ ] **Step 4: Update `me()` and `update_me()` handlers to return `avatar_url`**

Edit `backend/app/routers/auth.py`. In both `me()` and `update_me()`, change the `return UserResponse(...)` calls to include `avatar_url`:

```python
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url or None,
        auth_provider=user.auth_provider,
        phone_number=user.phone_number,
    )
```

Apply this to both handlers (lines 120-126 and 143-149 in the original file).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_auth_me.py::TestGetMe -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/routers/auth.py backend/tests/test_auth_me.py
git commit -m "feat(auth): include avatar_url in GET /auth/me response

Fixes bug where refetching the user after edits dropped the avatar.
The UserInfo model in iOS already has avatarUrl; this just makes
the backend surface match."
```

---

## Task 2: Backend — Add `upload_user_avatar` helper to storage module

**Files:**
- Modify: `backend/app/storage.py`
- Modify: `backend/tests/test_storage.py` (add test)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_storage.py`:

```python
class TestUploadUserAvatar:
    def test_user_avatar_blob_path_format(self, monkeypatch):
        from app import storage

        captured = {}

        class FakeBlob:
            def __init__(self, name): self.name = name; self.cache_control = None
            def upload_from_string(self, data, content_type=None):
                captured["data"] = data
                captured["content_type"] = content_type

        class FakeBucket:
            def blob(self, name):
                captured["blob_name"] = name
                return FakeBlob(name)

        class FakeClient:
            def bucket(self, name): return FakeBucket()

        monkeypatch.setattr(storage, "_get_client", lambda: FakeClient())
        monkeypatch.setattr(storage.settings, "gcs_bucket", "test-bucket")

        url = storage.upload_user_avatar("user-123", b"imagebytes", "image/jpeg")

        assert captured["blob_name"].startswith("users/user-123/")
        assert captured["blob_name"].endswith(".jpg")
        assert captured["data"] == b"imagebytes"
        assert url.startswith("https://storage.googleapis.com/test-bucket/users/user-123/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_storage.py::TestUploadUserAvatar -v`
Expected: FAIL — `upload_user_avatar` not defined.

- [ ] **Step 3: Implement `upload_user_avatar`**

Append to `backend/app/storage.py` after `upload_avatar`:

```python
def upload_user_avatar(user_id: str, data: bytes, content_type: str) -> str:
    """Upload a user profile avatar to GCS, return public URL.

    Uses users/<user_id>/<timestamp>.<ext> so re-uploads bust CDN cache
    naturally without needing a ?v= query param.
    """
    import time

    ext = _ext_from_content_type(content_type)
    blob_name = f"users/{user_id}/{int(time.time())}.{ext}"

    bucket = _get_bucket()
    blob = bucket.blob(blob_name)
    blob.cache_control = "public, max-age=31536000"
    blob.upload_from_string(data, content_type=content_type)

    url = get_avatar_url(blob_name, settings.gcs_bucket)
    logger.info("user_avatar_uploaded_gcs", extra={"user_id": user_id, "blob": blob_name})
    return url
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_storage.py::TestUploadUserAvatar -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage.py backend/tests/test_storage.py
git commit -m "feat(storage): add upload_user_avatar helper

User avatars live at users/<user_id>/<timestamp>.<ext> so re-uploads
produce a new URL and don't need ?v= cache busting."
```

---

## Task 3: Backend — Add `POST /auth/me/avatar` endpoint

**Files:**
- Modify: `backend/app/routers/auth.py` (append after `delete_account`)
- Modify: `backend/tests/test_auth_me.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_auth_me.py`:

```python
class TestUploadAvatar:
    @pytest.mark.asyncio
    async def test_upload_rejects_wrong_content_type(self):
        from fastapi import HTTPException
        from app.routers.auth import upload_avatar

        class FakeFile:
            content_type = "application/pdf"
            async def read(self): return b"junk"

        with pytest.raises(HTTPException) as exc:
            await upload_avatar(file=FakeFile(), user_id=uuid.uuid4(), db=AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_rejects_oversize(self):
        from fastapi import HTTPException
        from app.routers.auth import upload_avatar

        class FakeFile:
            content_type = "image/jpeg"
            async def read(self): return b"x" * (5 * 1024 * 1024 + 1)

        with pytest.raises(HTTPException) as exc:
            await upload_avatar(file=FakeFile(), user_id=uuid.uuid4(), db=AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_happy_path_updates_user_and_returns_url(self, monkeypatch):
        from app.routers import auth as auth_router

        user = _make_user(avatar_url="")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        monkeypatch.setattr(
            auth_router,
            "gcs_upload_user_avatar",
            lambda uid, data, ct: f"https://storage.googleapis.com/test/users/{uid}/1.jpg",
        )
        # Force the "gcs_bucket set" code path
        from app.config import settings
        monkeypatch.setattr(settings, "gcs_bucket", "test")

        class FakeFile:
            content_type = "image/jpeg"
            async def read(self): return b"x" * 100

        resp = await auth_router.upload_avatar(file=FakeFile(), user_id=user.id, db=db)
        assert resp["avatar_url"].startswith("https://storage.googleapis.com/test/users/")
        assert user.avatar_url == resp["avatar_url"]
        db.commit.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_auth_me.py::TestUploadAvatar -v`
Expected: FAIL — `upload_avatar` not defined in `app.routers.auth`.

- [ ] **Step 3: Add the endpoint**

Edit `backend/app/routers/auth.py`. At the top imports section, add:

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.storage import upload_user_avatar as gcs_upload_user_avatar
from app.config import settings
```

(Merge with the existing `from fastapi import` line — don't duplicate.)

Append this handler at the end of the file:

```python
@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Upload the current user's profile avatar."""
    if file.content_type not in ("image/jpeg", "image/png", "image/heic", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, HEIC, or WebP images are allowed")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if settings.gcs_bucket:
        url = gcs_upload_user_avatar(str(user_id), content, file.content_type)
    else:
        # Local fallback — write to uploads/users/<user_id>.<ext>
        from pathlib import Path
        upload_dir = Path(__file__).resolve().parent.parent / "uploads" / "users"
        upload_dir.mkdir(parents=True, exist_ok=True)
        ext = file.content_type.split("/")[-1].replace("jpeg", "jpg")
        filepath = upload_dir / f"{user_id}.{ext}"
        filepath.write_bytes(content)
        url = f"/api/v1/auth/me/avatar/file"  # not served; dev only

    user.avatar_url = url
    await db.commit()
    await db.refresh(user)

    logger.info("user_avatar_uploaded", extra={"user_id": str(user_id)})
    return {"avatar_url": url}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_auth_me.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Smoke test the live endpoint**

Run: `cd backend && uvicorn app.main:app --port 8000 &` then
```bash
# Get a dev token first
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/dev \
  -H "Content-Type: application/json" \
  -d '{"name":"Dev","email":"dev@cozypup.app"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
# Upload a small test image
curl -X POST http://localhost:8000/api/v1/auth/me/avatar \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/tiny.jpg"
```

Expected: JSON response with `avatar_url`. Kill the server after: `pkill -f uvicorn`.

Skip this step if no test image is handy — unit tests already cover behavior.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth_me.py
git commit -m "feat(auth): add POST /auth/me/avatar endpoint

Accepts multipart image upload (jpeg/png/heic/webp, max 5MB),
writes to GCS under users/<user_id>/<timestamp>.<ext>, updates
user.avatar_url, returns the new URL."
```

---

## Task 4: Backend — Done marker

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && pytest tests/test_auth_me.py tests/test_storage.py tests/test_subscription.py -v`
Expected: all PASS, no regressions in adjacent tests.

- [ ] **Step 2: Mark backend track complete**

No commit needed; this is a sync point for the iOS track to begin integration.

---

## Task 5: iOS — Create `AppConfig.swift` constants file

**Files:**
- Create: `ios-app/CozyPup/AppConfig.swift`

- [ ] **Step 1: Create the file**

Create `ios-app/CozyPup/AppConfig.swift`:

```swift
import Foundation

/// Single source of truth for hardcoded URLs, emails, and external IDs.
/// Placeholders marked `TBD` must be filled before the first App Store submission.
enum AppConfig {
    /// Support email used by Contact Support and Report a Problem.
    /// Replace before submission.
    static let supportEmail = "support@cozypup.app"  // TBD

    /// Privacy Policy — opened in SFSafariViewController.
    static let privacyPolicyURL = "https://cozypup.app/privacy"  // TBD

    /// Terms of Use — required by Apple for auto-renewable subscriptions.
    /// Opened in SFSafariViewController.
    static let termsOfUseURL = "https://cozypup.app/terms"  // TBD

    /// App Store share URL. When empty, the Share button is hidden.
    /// Fill at the time of first App Store submission.
    static let appStoreURL = ""  // TBD

    /// Bundle version + build, read from Info.plist.
    static var versionString: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "v\(version) (\(build))"
    }

    /// Whether Share CozyPup button should be shown.
    static var isShareEnabled: Bool { !appStoreURL.isEmpty }
}
```

- [ ] **Step 2: Add file to Xcode project**

Because CozyPup uses an Xcode project (not Swift Package), the new file must be added to the project's source list. Verify by opening `ios-app/CozyPup.xcodeproj` in Xcode, right-click `CozyPup` group → "Add Files to CozyPup…" → select `AppConfig.swift` if it isn't already there.

If building via xcodebuild command-line first fails with "cannot find 'AppConfig' in scope", this is the fix.

- [ ] **Step 3: Build to verify file compiles**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -20
```
Expected: `BUILD SUCCEEDED`.

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/AppConfig.swift ios-app/CozyPup.xcodeproj
git commit -m "feat(ios): add AppConfig for external URLs and config

Centralizes support email, Privacy / Terms URLs, App Store URL, and
Bundle version. TBD placeholders must be filled before App Store
submission; Share button hides itself when App Store URL is empty."
```

---

## Task 6: iOS — Create `SafariWebView.swift` wrapper

**Files:**
- Create: `ios-app/CozyPup/Views/Shared/SafariWebView.swift`

- [ ] **Step 1: Create the file**

```swift
import SwiftUI
import SafariServices

/// Presents a URL in an in-app Safari view controller.
struct SafariWebView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let config = SFSafariViewController.Configuration()
        config.barCollapsingEnabled = true
        let vc = SFSafariViewController(url: url, configuration: config)
        vc.preferredBarTintColor = UIColor(Tokens.bg)
        vc.preferredControlTintColor = UIColor(Tokens.accent)
        return vc
    }

    func updateUIViewController(_ uiViewController: SFSafariViewController, context: Context) {}
}

#Preview {
    SafariWebView(url: URL(string: "https://apple.com")!)
}
```

- [ ] **Step 2: Add to Xcode project**

Add `SafariWebView.swift` to the `Views/Shared` group in Xcode.

- [ ] **Step 3: Build**

Run: `cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -10`
Expected: `BUILD SUCCEEDED`.

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/Views/Shared/SafariWebView.swift ios-app/CozyPup.xcodeproj
git commit -m "feat(ios): add SafariWebView wrapper for SFSafariViewController"
```

---

## Task 7: iOS — Create `ShareSheet.swift` wrapper

**Files:**
- Create: `ios-app/CozyPup/Views/Shared/ShareSheet.swift`

- [ ] **Step 1: Create the file**

```swift
import SwiftUI
import UIKit

/// UIActivityViewController wrapper for sharing text / URLs.
struct ShareSheet: UIViewControllerRepresentable {
    let activityItems: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
```

- [ ] **Step 2: Add to Xcode project, build, commit**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
git add ios-app/CozyPup/Views/Shared/ShareSheet.swift ios-app/CozyPup.xcodeproj
git commit -m "feat(ios): add ShareSheet wrapper for UIActivityViewController"
```

Expected: `BUILD SUCCEEDED`.

---

## Task 8: iOS — Create `ReleaseNotes.swift` data

**Files:**
- Create: `ios-app/CozyPup/ReleaseNotes.swift`

- [ ] **Step 1: Create the file**

```swift
import Foundation

struct ReleaseNote: Identifiable {
    let id = UUID()
    let version: String
    let date: String
    let highlights: [String]
}

enum ReleaseNotes {
    static let all: [ReleaseNote] = [
        ReleaseNote(
            version: "1.0",
            date: "April 2026",
            highlights: [
                "First public release",
                "AI pet health assistant with chat",
                "Calendar and reminders",
                "Duo Plan for sharing with a partner",
            ]
        ),
    ]
}
```

- [ ] **Step 2: Add to Xcode, build, commit**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
git add ios-app/CozyPup/ReleaseNotes.swift ios-app/CozyPup.xcodeproj
git commit -m "feat(ios): add static ReleaseNotes data"
```

---

## Task 9: iOS — Create `WhatsNewView.swift`

**Files:**
- Create: `ios-app/CozyPup/Views/Settings/WhatsNewView.swift`

- [ ] **Step 1: Create the file**

```swift
import SwiftUI

struct WhatsNewView: View {
    @ObservedObject private var lang = Lang.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Tokens.spacing.lg) {
                ForEach(ReleaseNotes.all) { note in
                    VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                        HStack {
                            Text(note.version)
                                .font(Tokens.fontTitle.weight(.semibold))
                                .foregroundColor(Tokens.text)
                            Spacer()
                            Text(note.date)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
                            ForEach(note.highlights, id: \.self) { h in
                                HStack(alignment: .top, spacing: Tokens.spacing.sm) {
                                    Text("•").foregroundColor(Tokens.accent)
                                    Text(h)
                                        .font(Tokens.fontBody)
                                        .foregroundColor(Tokens.text)
                                }
                            }
                        }
                    }
                    .padding(Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radius)
                }
            }
            .padding(Tokens.spacing.md)
        }
        .background(Tokens.bg)
        .navigationTitle(lang.isZh ? "更新说明" : "What's New")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationStack {
        WhatsNewView()
    }
}
```

- [ ] **Step 2: Build, commit**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
git add ios-app/CozyPup/Views/Settings/WhatsNewView.swift ios-app/CozyPup.xcodeproj
git commit -m "feat(ios): add WhatsNewView for release notes"
```

---

## Task 10: iOS — Create `AcknowledgementsView.swift`

**Files:**
- Create: `ios-app/CozyPup/Views/Settings/AcknowledgementsView.swift`

- [ ] **Step 1: Create the file**

```swift
import SwiftUI

private struct Dependency: Identifiable {
    let id = UUID()
    let name: String
    let license: String
    let url: String
}

struct AcknowledgementsView: View {
    @ObservedObject private var lang = Lang.shared

    private let dependencies: [Dependency] = [
        Dependency(name: "GoogleSignIn-iOS", license: "Apache 2.0", url: "https://github.com/google/GoogleSignIn-iOS"),
        // Add more as dependencies are introduced.
    ]

    var body: some View {
        List {
            Section {
                ForEach(dependencies) { dep in
                    VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                        Text(dep.name)
                            .font(Tokens.fontBody.weight(.medium))
                            .foregroundColor(Tokens.text)
                        Text(dep.license)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                        Text(dep.url)
                            .font(Tokens.fontCaption2)
                            .foregroundColor(Tokens.textTertiary)
                    }
                    .padding(.vertical, Tokens.spacing.xxs)
                    .listRowBackground(Tokens.surface)
                }
            } footer: {
                Text(lang.isZh
                    ? "感谢这些开源项目让 CozyPup 成为可能。"
                    : "Thanks to these open-source projects that make CozyPup possible.")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .scrollContentBackground(.hidden)
        .background(Tokens.bg)
        .navigationTitle(lang.isZh ? "开源致谢" : "Acknowledgements")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationStack {
        AcknowledgementsView()
    }
}
```

- [ ] **Step 2: Build, commit**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
git add ios-app/CozyPup/Views/Settings/AcknowledgementsView.swift ios-app/CozyPup.xcodeproj
git commit -m "feat(ios): add AcknowledgementsView for open-source dependencies"
```

---

## Task 11: iOS — Update `AuthStore` to decode avatar_url and add updater helpers

**Files:**
- Modify: `ios-app/CozyPup/Stores/AuthStore.swift`

- [ ] **Step 1: Fix `validateSession` and `fetchUserFromMe` decoders**

In `AuthStore.swift`, replace the inner `UserResp` struct definitions in `validateSession` (line 42) and `fetchUserFromMe` (line 175) so they decode `avatar_url`, and refresh `self.user` when present.

Change `validateSession` (line 41-48) to:

```swift
    private func validateSession() async {
        struct UserResp: Decodable {
            let id: String
            let email: String
            let name: String?
            let avatar_url: String?
            let auth_provider: String
        }
        do {
            let me: UserResp = try await APIClient.shared.request("GET", "/auth/me")
            // Refresh cached user with latest avatar_url from server
            if let current = self.user {
                let updated = UserInfo(
                    name: me.name ?? current.name,
                    email: me.email,
                    provider: me.auth_provider,
                    avatarUrl: me.avatar_url ?? current.avatarUrl
                )
                self.user = updated
                if let data = try? JSONEncoder().encode(updated) {
                    UserDefaults.standard.set(data, forKey: authKey)
                }
            }
        } catch {
            isAuthenticated = false
        }
    }
```

Change `fetchUserFromMe` (line 174-184) to:

```swift
    private func fetchUserFromMe(fallbackProvider: String) async {
        struct UserResp: Decodable {
            let id: String
            let email: String
            let name: String?
            let avatar_url: String?
            let auth_provider: String
        }
        do {
            let me: UserResp = try await APIClient.shared.request("GET", "/auth/me")
            saveUser(UserInfo(name: me.name ?? "User", email: me.email, provider: me.auth_provider, avatarUrl: me.avatar_url))
        } catch {
            print("fetchUserFromMe failed: \(error)")
            saveUser(UserInfo(name: "User", email: "", provider: fallbackProvider, avatarUrl: nil))
        }
    }
```

- [ ] **Step 2: Add `updateName` and `updateAvatarURL` helpers**

Append inside the `AuthStore` class, after `acknowledgeDisclaimer`:

```swift
    // MARK: - User mutations

    /// Update the in-memory + cached UserInfo with a new name. Caller is
    /// responsible for the backend PATCH.
    func updateName(_ name: String) {
        guard let current = user else { return }
        let updated = UserInfo(name: name, email: current.email, provider: current.provider, avatarUrl: current.avatarUrl)
        self.user = updated
        if let data = try? JSONEncoder().encode(updated) {
            UserDefaults.standard.set(data, forKey: authKey)
        }
    }

    /// Update the in-memory + cached UserInfo with a new avatar URL.
    func updateAvatarURL(_ url: String) {
        guard let current = user else { return }
        let updated = UserInfo(name: current.name, email: current.email, provider: current.provider, avatarUrl: url)
        self.user = updated
        if let data = try? JSONEncoder().encode(updated) {
            UserDefaults.standard.set(data, forKey: authKey)
        }
    }
```

- [ ] **Step 3: Build**

Run: `cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -10`
Expected: `BUILD SUCCEEDED`.

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/Stores/AuthStore.swift
git commit -m "feat(ios): AuthStore decodes avatar_url and exposes updaters

/auth/me now returns avatar_url; refresh it into the cached UserInfo
on session validate and after user mutations so the Profile sheet
always shows the latest avatar."
```

---

## Task 12: iOS — Create `DuoPlanSection.swift`

**Files:**
- Create: `ios-app/CozyPup/Views/Settings/DuoPlanSection.swift`

- [ ] **Step 1: Create the file**

```swift
import SwiftUI

/// Section of the Profile sheet showing Duo Plan state.
///
/// Three states:
/// 1. Active (current user has isDuo=true) — shows section header "DUO PLAN · Active"
///    plus a friend row that pushes into FamilySettingsView. Friend row subtitle is
///    "Member" (if I am payer) or "Paid by" (if I am member).
/// 2. Pending invite (payer has sent invite, not yet accepted) — shows section header
///    and a muted "Invite pending..." row that also opens FamilySettingsView.
/// 3. Inactive — section header "DUO PLAN · Inactive" plus an "Upgrade to Duo Plan"
///    row that opens the Duo paywall.
struct DuoPlanSection: View {
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    @ObservedObject private var lang = Lang.shared

    @Binding var showFamilySettings: Bool
    @Binding var showDuoPaywall: Bool

    @State private var familyState: FamilyState = .loading

    private enum FamilyState {
        case loading
        case active(partnerName: String, partnerEmail: String, iAmPayer: Bool)
        case pending(email: String)
        case none
    }

    var body: some View {
        Section(header: Text(headerText).font(Tokens.fontCaption).foregroundColor(Tokens.textSecondary)) {
            switch familyState {
            case .loading:
                HStack {
                    ProgressView().controlSize(.small)
                    Spacer()
                }
                .listRowBackground(Tokens.surface)

            case .active(let name, let email, let iAmPayer):
                Button { showFamilySettings = true } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Circle()
                            .fill(Tokens.accentSoft)
                            .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                            .overlay(
                                Text(String(name.prefix(1)))
                                    .foregroundColor(Tokens.accent)
                                    .font(Tokens.fontSubheadline.weight(.semibold))
                            )
                        VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                            Text(name)
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                            Text(iAmPayer
                                 ? (lang.isZh ? "成员" : "Member")
                                 : (lang.isZh ? "由对方付费" : "Paid by"))
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
                .listRowBackground(Tokens.surface)

            case .pending(let email):
                Button { showFamilySettings = true } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Circle()
                            .fill(Tokens.surface2)
                            .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                            .overlay(
                                Image(systemName: "hourglass")
                                    .foregroundColor(Tokens.textTertiary)
                                    .font(Tokens.fontSubheadline)
                            )
                        VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                            Text(lang.isZh ? "邀请已发送" : "Invite pending")
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                            Text(email)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
                .listRowBackground(Tokens.surface)

            case .none:
                Button { showDuoPaywall = true } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Image(systemName: "person.2.fill")
                            .foregroundColor(Tokens.accent)
                            .frame(width: Tokens.size.avatarSmall)
                        Text(lang.isZh ? "升级至双人计划" : "Upgrade to Duo Plan")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                        Spacer()
                        Text(lang.isZh ? "升级" : "Upgrade")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.accent)
                        Image(systemName: "chevron.right")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
                .listRowBackground(Tokens.surface)
            }
        }
        .task { await loadFamilyState() }
        .onChange(of: subscriptionStore.isDuo) { _, _ in
            Task { await loadFamilyState() }
        }
    }

    private var headerText: String {
        let base = lang.isZh ? "双人计划" : "DUO PLAN"
        switch familyState {
        case .active: return "\(base) · \(lang.isZh ? "已激活" : "ACTIVE")"
        case .pending: return "\(base) · \(lang.isZh ? "邀请中" : "PENDING")"
        default: return "\(base) · \(lang.isZh ? "未开通" : "INACTIVE")"
        }
    }

    private func loadFamilyState() async {
        struct Resp: Decodable {
            let role: String?
            let partner_email: String?
            let partner_name: String?
            let invite_pending: Bool
            let pending_invite_email: String?
        }
        do {
            let resp: Resp = try await APIClient.shared.request("GET", "/family/status")
            if let partnerName = resp.partner_name, let partnerEmail = resp.partner_email {
                familyState = .active(
                    partnerName: partnerName,
                    partnerEmail: partnerEmail,
                    iAmPayer: resp.role == "payer"
                )
            } else if resp.invite_pending {
                familyState = .pending(email: resp.pending_invite_email ?? "")
            } else {
                familyState = .none
            }
        } catch {
            familyState = .none
        }
    }
}
```

- [ ] **Step 2: Build, commit**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -10
git add ios-app/CozyPup/Views/Settings/DuoPlanSection.swift ios-app/CozyPup.xcodeproj
git commit -m "feat(ios): add DuoPlanSection with friend row, pending, and upgrade states"
```

---

## Task 13: iOS — Rebuild `UserProfileSheet.swift`

**Files:**
- Modify: `ios-app/CozyPup/Views/Settings/UserProfileSheet.swift`

This rewrite is large enough to replace the file body rather than surgical edits. Keep the existing `UserProfileSheet` struct name and public API (`auth: AuthStore` param, `.environmentObject(subscriptionStore)` injection) so callers don't change.

- [ ] **Step 1: Replace the file body**

Replace the entire contents of `ios-app/CozyPup/Views/Settings/UserProfileSheet.swift` with:

```swift
import SwiftUI
import PhotosUI
import StoreKit

struct UserProfileSheet: View {
    @ObservedObject var auth: AuthStore
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    @ObservedObject private var lang = Lang.shared
    @Environment(\.dismiss) private var dismiss

    @State private var editingName = false
    @State private var nameText = ""
    @FocusState private var nameFocused: Bool
    @State private var showFamilySettings = false
    @State private var showDuoPaywall = false
    @State private var showDeleteConfirm = false
    @State private var isDeleting = false

    @State private var avatarItem: PhotosPickerItem?
    @State private var isUploadingAvatar = false

    @State private var safariURL: URL?
    @State private var showDisclaimer = false
    @State private var showAcknowledgements = false

    var body: some View {
        NavigationStack {
            List {
                avatarSection
                accountSection
                subscriptionSection
                legalSection
                deleteSection
            }
            .scrollContentBackground(.hidden)
            .background(Tokens.bg)
            .foregroundColor(Tokens.text)
            .navigationTitle(lang.isZh ? "个人信息" : "Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .tint(Tokens.text)
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .presentationBackground(Tokens.bg)
        .onAppear { nameText = auth.user?.name ?? "" }
        .onChange(of: avatarItem) { _, newItem in
            guard let newItem else { return }
            Task { await uploadAvatar(from: newItem) }
        }
        .fullScreenCover(isPresented: $showFamilySettings) {
            FamilySettingsView { showFamilySettings = false }
        }
        .sheet(isPresented: $showDuoPaywall) {
            PaywallSheet(isHard: false, initialDuo: true) { showDuoPaywall = false }
                .presentationDetents([.large])
                .environmentObject(subscriptionStore)
        }
        .sheet(item: Binding(
            get: { safariURL.map { IdentifiableURL(url: $0) } },
            set: { safariURL = $0?.url }
        )) { wrapped in
            SafariWebView(url: wrapped.url)
                .ignoresSafeArea()
        }
        .sheet(isPresented: $showDisclaimer) {
            NavigationStack {
                LegalPageView(title: L.disclaimer, content: disclaimerText)
            }
        }
        .sheet(isPresented: $showAcknowledgements) {
            NavigationStack {
                AcknowledgementsView()
            }
        }
        .alert(
            lang.isZh ? "确认注销账号？" : "Delete Account?",
            isPresented: $showDeleteConfirm
        ) {
            Button(lang.isZh ? "取消" : "Cancel", role: .cancel) {}
            Button(lang.isZh ? "注销" : "Delete", role: .destructive) {
                Task { await deleteAccount() }
            }
        } message: {
            Text(lang.isZh
                ? "注销后所有数据将被永久删除，包括宠物档案、聊天记录、日历事件等，且无法恢复。"
                : "All data will be permanently deleted, including pet profiles, chat history, calendar events, etc. This cannot be undone.")
        }
        .overlay {
            if isDeleting || isUploadingAvatar {
                Tokens.dimOverlay.opacity(0.35).ignoresSafeArea()
                ProgressView()
            }
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private var avatarSection: some View {
        Section {
            VStack(spacing: Tokens.spacing.md) {
                PhotosPicker(selection: $avatarItem, matching: .images) {
                    avatarImage
                }
                .buttonStyle(.plain)

                if editingName {
                    TextField(lang.isZh ? "输入名字" : "Enter name", text: $nameText)
                        .font(Tokens.fontTitle.weight(.semibold))
                        .foregroundColor(Tokens.text)
                        .multilineTextAlignment(.center)
                        .focused($nameFocused)
                        .onSubmit { saveName() }
                } else {
                    Button {
                        editingName = true
                        nameFocused = true
                    } label: {
                        HStack(spacing: Tokens.spacing.xs) {
                            Text(auth.user?.name ?? "User")
                                .font(Tokens.fontTitle.weight(.semibold))
                                .foregroundColor(Tokens.text)
                            Image(systemName: "pencil")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, Tokens.spacing.md)
            .listRowBackground(Color.clear)
        }
    }

    @ViewBuilder
    private var avatarImage: some View {
        if let avatarUrl = auth.user?.avatarUrl,
           !avatarUrl.isEmpty,
           let url = URL(string: avatarUrl) {
            AsyncImage(url: url) { image in
                image.resizable().scaledToFill()
            } placeholder: {
                fallbackAvatar
            }
            .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
            .clipShape(Circle())
        } else {
            fallbackAvatar
                .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
        }
    }

    private var fallbackAvatar: some View {
        Circle()
            .fill(Tokens.accent)
            .overlay(
                Text(String((auth.user?.name ?? "U").prefix(1)))
                    .foregroundColor(Tokens.white)
                    .font(.system(size: 32, weight: .semibold))
            )
    }

    @ViewBuilder
    private var accountSection: some View {
        Section(lang.isZh ? "账号信息" : "Account") {
            infoRow(icon: "envelope", label: lang.isZh ? "邮箱" : "Email", value: auth.user?.email ?? "-")
            infoRow(icon: "person.badge.key", label: lang.isZh ? "登录方式" : "Sign-in", value: providerLabel(auth.user?.provider))
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var subscriptionSection: some View {
        Section(lang.isZh ? "订阅" : "Subscription") {
            HStack {
                Label {
                    Text(lang.isZh ? "当前计划" : "Current plan")
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.text)
                } icon: {
                    Image(systemName: "crown.fill")
                        .foregroundColor(Tokens.accent)
                }
                Spacer()
                statusLabel
                    .font(Tokens.fontSubheadline)
            }

            Button {
                Task {
                    guard let scene = UIApplication.shared.connectedScenes
                        .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene
                    else { return }
                    try? await AppStore.showManageSubscriptions(in: scene)
                }
            } label: {
                HStack {
                    Label {
                        Text(lang.isZh ? "管理订阅" : "Manage Subscription")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                    } icon: {
                        Image(systemName: "creditcard")
                            .foregroundColor(Tokens.accent)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }

            Button {
                Task { await subscriptionStore.restorePurchases() }
            } label: {
                HStack {
                    Label {
                        Text(lang.isZh ? "恢复购买" : "Restore Purchases")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                    } icon: {
                        Image(systemName: "arrow.clockwise")
                            .foregroundColor(Tokens.accent)
                    }
                    Spacer()
                }
            }
        }
        .listRowBackground(Tokens.surface)

        DuoPlanSection(
            showFamilySettings: $showFamilySettings,
            showDuoPaywall: $showDuoPaywall
        )
        .environmentObject(subscriptionStore)
    }

    @ViewBuilder
    private var statusLabel: some View {
        switch subscriptionStore.status {
        case .trial(let days):
            Text("Trial · \(days)d").foregroundColor(Tokens.orange)
        case .active:
            Text(lang.isZh ? "已激活" : "Active").foregroundColor(Tokens.green)
        case .expired:
            Text(lang.isZh ? "已过期" : "Expired").foregroundColor(Tokens.red)
        case .loading:
            ProgressView().controlSize(.small)
        }
    }

    @ViewBuilder
    private var legalSection: some View {
        Section(lang.isZh ? "法律条款" : "Legal") {
            Button {
                if let url = URL(string: AppConfig.privacyPolicyURL) {
                    safariURL = url
                }
            } label: {
                legalRow(icon: "shield", title: L.privacyPolicy)
            }

            Button {
                if let url = URL(string: AppConfig.termsOfUseURL) {
                    safariURL = url
                }
            } label: {
                legalRow(icon: "doc.text", title: lang.isZh ? "使用条款" : "Terms of Use")
            }

            Button {
                showDisclaimer = true
            } label: {
                legalRow(icon: "exclamationmark.triangle", title: L.disclaimer)
            }

            Button {
                showAcknowledgements = true
            } label: {
                legalRow(icon: "heart", title: lang.isZh ? "开源致谢" : "Acknowledgements")
            }
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var deleteSection: some View {
        Section {
            Button(role: .destructive) {
                showDeleteConfirm = true
            } label: {
                HStack {
                    Spacer()
                    Label(lang.isZh ? "注销账号" : "Delete Account", systemImage: "trash")
                    Spacer()
                }
            }
            .listRowBackground(Tokens.surface)
        }

        Section {
            HStack {
                Spacer()
                Text("CozyPup \(AppConfig.versionString)")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
                Spacer()
            }
            .listRowBackground(Color.clear)
        }
    }

    // MARK: - Row builders

    private func infoRow(icon: String, label: String, value: String) -> some View {
        HStack {
            Label(label, systemImage: icon)
                .font(Tokens.fontBody)
                .foregroundColor(Tokens.text)
            Spacer()
            Text(value)
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)
        }
    }

    private func legalRow(icon: String, title: String) -> some View {
        HStack {
            Label {
                Text(title)
                    .font(Tokens.fontBody)
                    .foregroundColor(Tokens.text)
            } icon: {
                Image(systemName: icon)
                    .foregroundColor(Tokens.accent)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textTertiary)
        }
    }

    // MARK: - Actions

    private func providerLabel(_ provider: String?) -> String {
        switch provider {
        case "google": return "Google"
        case "apple": return "Apple"
        case "dev": return "Dev"
        default: return provider ?? "-"
        }
    }

    private func uploadAvatar(from item: PhotosPickerItem) async {
        isUploadingAvatar = true
        defer { isUploadingAvatar = false; avatarItem = nil }

        guard let data = try? await item.loadTransferable(type: Data.self) else { return }
        struct Resp: Decodable { let avatar_url: String }
        do {
            let raw = try await APIClient.shared.uploadMultipart(
                "/auth/me/avatar",
                fileData: data,
                fileName: "avatar.jpg",
                mimeType: "image/jpeg"
            )
            let resp = try JSONDecoder().decode(Resp.self, from: raw)
            auth.updateAvatarURL(resp.avatar_url)
        } catch {
            print("[Profile] avatar upload failed: \(error)")
        }
    }

    private func saveName() {
        let trimmed = nameText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed != auth.user?.name else {
            editingName = false
            return
        }
        editingName = false
        Task {
            struct UpdateBody: Encodable { let name: String }
            struct UserResp: Decodable {
                let id: String
                let email: String
                let name: String?
                let avatar_url: String?
                let auth_provider: String
            }
            do {
                let resp: UserResp = try await APIClient.shared.request("PATCH", "/auth/me", body: UpdateBody(name: trimmed))
                auth.updateName(resp.name ?? trimmed)
                if let av = resp.avatar_url { auth.updateAvatarURL(av) }
            } catch {
                nameText = auth.user?.name ?? ""
            }
        }
    }

    private func deleteAccount() async {
        isDeleting = true
        struct DeleteResp: Decodable { let status: String }
        do {
            let _: DeleteResp = try await APIClient.shared.request("DELETE", "/auth/me")
            auth.logout()
            dismiss()
        } catch {
            print("[Account] delete failed: \(error)")
        }
        isDeleting = false
    }

    // MARK: - Copy

    private let disclaimerText = "CozyPup provides AI-generated suggestions for informational purposes only. These suggestions do not constitute professional veterinary advice. Always consult a qualified veterinarian for medical concerns."
}

private struct IdentifiableURL: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

#Preview {
    UserProfileSheet(auth: AuthStore())
        .environmentObject(SubscriptionStore())
}
```

- [ ] **Step 2: Build**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -20
```
Expected: `BUILD SUCCEEDED`.

If the build fails on `L.privacyPolicy` or `L.disclaimer`, open `ios-app/CozyPup/Theme/Lang.swift` (or wherever `L` lives) and confirm those keys exist. They are used in the current `UserProfileSheet`, so they should already be defined.

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Views/Settings/UserProfileSheet.swift
git commit -m "feat(ios): rebuild UserProfileSheet

- Add PhotosPicker-driven avatar upload via POST /auth/me/avatar
- Add Subscription section with Manage Subscription + Restore Purchases
- Integrate DuoPlanSection with linked friend row
- Add Terms of Use (opens SFSafariViewController) to satisfy Apple 3.1.2
- Privacy Policy now opens SFSafariViewController (was in-app text)
- Disclaimer and Acknowledgements remain in-app
- Version label reads from Bundle via AppConfig.versionString"
```

---

## Task 14: iOS — Rebuild `SettingsDrawer.swift`

**Files:**
- Modify: `ios-app/CozyPup/Views/Settings/SettingsDrawer.swift`

Only the list body (the `settingsListView` computed property and helpers) changes. The surrounding sheet/cover logic, pet edit pages, and deep-link plumbing stay the same.

- [ ] **Step 1: Remove notification prefs state and helpers**

In `SettingsDrawer.swift`:

- Delete state lines `@State private var notifications`, `medReminders`, `weeklyInsights` (lines 10-12).
- Delete `private let prefsKey = "cozypup_notification_prefs"` (line 29).
- Delete the `loadPrefs()` and `savePrefs()` helpers (lines 439-453).
- Delete the three `.onChange(of: notifications/medReminders/weeklyInsights)` modifiers (lines 70-72).
- Delete `.onAppear { loadPrefs() }` (line 57).
- Add imports: `import StoreKit` at the top if not present.

- [ ] **Step 2: Add new state for Support and What's New sheets**

In the `@State` block near the top, add:

```swift
    @State private var showWhatsNew = false
    @State private var showShareSheet = false
```

- [ ] **Step 3: Rewrite the settings list body**

Replace the entire `settingsListView` computed property (lines 165-358) with:

```swift
    private var settingsListView: some View {
        NavigationStack {
            List {
                profileCardSection
                myPetsSection
                preferencesSection
                notificationsSection
                supportSection
                aboutSection
                logOutSection
            }
            .scrollContentBackground(.hidden)
            .background(Tokens.bg)
            .foregroundColor(Tokens.text)
            .navigationTitle(L.settings)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showScanner = true
                    } label: {
                        Image(systemName: "qrcode.viewfinder")
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.text)
                            .frame(width: Tokens.size.buttonMedium, height: Tokens.size.buttonMedium)
                            .contentShape(Rectangle())
                    }
                }
            }
            .sheet(isPresented: $showWhatsNew) {
                NavigationStack { WhatsNewView() }
            }
            .sheet(isPresented: $showShareSheet) {
                if let url = URL(string: AppConfig.appStoreURL) {
                    ShareSheet(activityItems: [url])
                }
            }
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private var profileCardSection: some View {
        Section {
            Button {
                showUserProfile = true
            } label: {
                HStack(spacing: 12) {
                    Circle()
                        .fill(Tokens.accent)
                        .frame(width: Tokens.size.avatarMedium, height: Tokens.size.avatarMedium)
                        .overlay(
                            Text(String(auth.user?.name.prefix(1) ?? "U"))
                                .foregroundColor(Tokens.white)
                                .font(Tokens.fontHeadline.weight(.semibold))
                        )
                    VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                        Text(auth.user?.name ?? "User")
                            .font(Tokens.fontCallout.weight(.medium))
                            .foregroundColor(Tokens.text)
                        Text(auth.user?.email ?? "")
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.textSecondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }
            .listRowBackground(Tokens.surface)
        }
    }

    @ViewBuilder
    private var myPetsSection: some View {
        Section(L.myPets) {
            ForEach(petStore.pets) { pet in
                petRow(pet)
            }
            Button {
                withAnimation { showAddPet = true }
            } label: {
                Label(L.addPet, systemImage: "plus")
                    .font(Tokens.fontSubheadline.weight(.medium))
                    .foregroundColor(Tokens.accent)
            }
            .listRowBackground(Tokens.surface)
        }
    }

    @ViewBuilder
    private func petRow(_ pet: Pet) -> some View {
        HStack(spacing: 12) {
            if !pet.avatarUrl.isEmpty,
               let baseURL = APIClient.shared.avatarURL(pet.avatarUrl),
               let url = URL(string: "\(baseURL.absoluteString)?v=\(petStore.avatarRevision)") {
                CachedAsyncImage(url: url) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    Image(systemName: pet.species == .cat ? "cat" : "dog")
                        .font(Tokens.fontTitle)
                        .foregroundColor(pet.color)
                }
                .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                .clipShape(Circle())
            } else {
                Image(systemName: pet.species == .cat ? "cat" : "dog")
                    .font(Tokens.fontTitle)
                    .foregroundColor(pet.color)
                    .frame(width: Tokens.size.avatarSmall)
            }
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(pet.name).font(Tokens.fontBody.weight(.medium))
                    if !pet.breed.isEmpty {
                        Text(pet.breed)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                    }
                }
            }
            Spacer()
            Button {
                withAnimation { editingPetId = pet.id }
            } label: {
                Image(systemName: "pencil")
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
            }
            .buttonStyle(.borderless)
            Button {
                showDeleteConfirm = pet
            } label: {
                Image(systemName: "trash")
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.red)
                    .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
            }
            .buttonStyle(.borderless)
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var preferencesSection: some View {
        Section(lang.isZh ? "偏好" : "Preferences") {
            Picker(L.responseLang, selection: $lang.code) {
                Text("中文").tag("zh")
                Text("English").tag("en")
            }
            .tint(Tokens.textSecondary)

            Toggle(L.syncToAppleCalendar, isOn: $calendarSync)
                .onChange(of: calendarSync) { _, newValue in
                    if newValue {
                        showCalendarSyncOptions = true
                    } else {
                        CalendarSyncService.shared.setSyncEnabled(false)
                    }
                }
        }
        .tint(Tokens.green)
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var notificationsSection: some View {
        Section(L.notifications) {
            Button {
                if let url = URL(string: UIApplication.openNotificationSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            } label: {
                HStack {
                    Label {
                        Text(L.pushNotifications)
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                    } icon: {
                        Image(systemName: "bell")
                            .foregroundColor(Tokens.accent)
                    }
                    Spacer()
                    Image(systemName: "arrow.up.right.square")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var supportSection: some View {
        Section(lang.isZh ? "支持" : "Support") {
            Button {
                openMail(to: AppConfig.supportEmail, subject: "CozyPup Support")
            } label: {
                supportRow(icon: "envelope", title: lang.isZh ? "联系我们" : "Contact Support")
            }

            Button {
                let subject = "[Report] CozyPup \(AppConfig.versionString)"
                let body = "Device: \(UIDevice.current.model)\niOS: \(UIDevice.current.systemVersion)\n\n"
                openMail(to: AppConfig.supportEmail, subject: subject, body: body)
            } label: {
                supportRow(icon: "exclamationmark.bubble", title: lang.isZh ? "反馈问题" : "Report a Problem")
            }

            Button {
                if let scene = UIApplication.shared.connectedScenes
                    .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene {
                    SKStoreReviewController.requestReview(in: scene)
                }
            } label: {
                supportRow(icon: "star", title: lang.isZh ? "给 CozyPup 评分" : "Rate CozyPup")
            }

            if AppConfig.isShareEnabled {
                Button {
                    showShareSheet = true
                } label: {
                    supportRow(icon: "square.and.arrow.up", title: lang.isZh ? "分享 CozyPup" : "Share CozyPup")
                }
            }
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var aboutSection: some View {
        Section(lang.isZh ? "关于" : "About") {
            Button {
                showWhatsNew = true
            } label: {
                supportRow(icon: "sparkles", title: lang.isZh ? "更新说明" : "What's New")
            }

            HStack {
                Label {
                    Text(lang.isZh ? "版本" : "Version")
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.text)
                } icon: {
                    Image(systemName: "info.circle")
                        .foregroundColor(Tokens.accent)
                }
                Spacer()
                Text(AppConfig.versionString)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var logOutSection: some View {
        Section {
            Button(role: .destructive) {
                Haptics.medium()
                auth.logout()
                withAnimation(.easeInOut(duration: 0.3)) { isPresented = false }
            } label: {
                Label(L.logOut, systemImage: "rectangle.portrait.and.arrow.right")
            }
            .listRowBackground(Tokens.surface)
        }
    }

    // MARK: - Helpers

    private func supportRow(icon: String, title: String) -> some View {
        HStack {
            Label {
                Text(title)
                    .font(Tokens.fontBody)
                    .foregroundColor(Tokens.text)
            } icon: {
                Image(systemName: icon)
                    .foregroundColor(Tokens.accent)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textTertiary)
        }
    }

    private func openMail(to: String, subject: String, body: String = "") {
        var components = URLComponents()
        components.scheme = "mailto"
        components.path = to
        var items: [URLQueryItem] = [URLQueryItem(name: "subject", value: subject)]
        if !body.isEmpty { items.append(URLQueryItem(name: "body", value: body)) }
        components.queryItems = items
        if let url = components.url {
            UIApplication.shared.open(url)
        }
    }
```

Also delete the old `petAge(_:)` helper (lines 455-466) — it's unused by the new layout.

- [ ] **Step 4: Build**

Run: `cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -20`
Expected: `BUILD SUCCEEDED`.

If the build complains about missing `lang` in `preferencesSection`, ensure the outer struct already has `@ObservedObject private var lang = Lang.shared` — it does (line 15 of the original file).

- [ ] **Step 5: Commit**

```bash
git add ios-app/CozyPup/Views/Settings/SettingsDrawer.swift
git commit -m "feat(ios): rebuild SettingsDrawer

- Remove duplicate Subscription row (moved into UserProfileSheet)
- Remove three fake notification toggles (push/med/weekly) that only
  wrote to UserDefaults
- Merge Language + Calendar into a single Preferences section
- Single Notifications row deep-links to system settings
- New Support section: Contact / Report / Rate / Share
- New About section: What's New + Bundle version
- Version string now reads from Bundle via AppConfig
- Log Out stays at the bottom as a destructive action"
```

---

## Task 15: QA matrix verification (manual, in simulator)

**Files:**
- None (this is a verification step)

Fresh subagent should execute this as a structured walk and report pass/fail per row.

- [ ] **Step 1: Launch app in simulator**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
xcrun simctl boot "iPhone 17 Pro" 2>/dev/null || true
open -a Simulator
```

Also start the backend: `cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000 &`

Sign in with Dev auth.

- [ ] **Step 2: Walk every row in the QA matrix**

Use the QA matrix from `docs/superpowers/specs/2026-04-12-settings-profile-redesign-design.md` §Verification. For each row:

1. Tap the button
2. Record observed behavior
3. Mark ✅ / ❌

Specifically verify these high-risk items:

- [ ] Profile card opens Profile sheet (avatar, name, email visible)
- [ ] Tapping avatar opens PhotosPicker
- [ ] Selecting an image uploads and updates the avatar (check simulator network inspector or backend logs for `POST /auth/me/avatar 200`)
- [ ] Tapping name enters edit mode; submitting calls `PATCH /auth/me`; name persists after dismiss
- [ ] Manage Subscription opens system sheet (may be empty in simulator — verify the sheet appears)
- [ ] Restore Purchases does not crash (may be empty entitlements in simulator — verify no crash)
- [ ] Duo Plan section shows correct state:
      - Fresh user: "Upgrade to Duo Plan" row
      - Duo payer: friend row with "Member" subtitle
      - Duo member: friend row with "Paid by" subtitle
      - Payer with pending invite: "Invite pending" row
- [ ] Privacy Policy opens SFSafariViewController with the configured URL
- [ ] Terms of Use opens SFSafariViewController
- [ ] Disclaimer opens as a sheet with in-app text
- [ ] Acknowledgements opens with dependency list
- [ ] Delete Account shows confirmation alert; canceling keeps you in Profile
- [ ] Settings: Language picker switches languages immediately
- [ ] Settings: Apple Calendar toggle presents sync confirmation dialog
- [ ] Settings: Push Notifications row opens system Settings app at CozyPup
- [ ] Settings: Contact Support opens Mail with populated `to:` and subject
- [ ] Settings: Report a Problem opens Mail with `[Report]` subject and device info in body
- [ ] Settings: Rate CozyPup shows rating prompt
- [ ] Settings: Share CozyPup — hidden if `AppConfig.appStoreURL` is empty
- [ ] Settings: What's New sheet presents release notes
- [ ] Settings: Version label matches `Info.plist` values
- [ ] Settings: Log Out returns to login screen and clears tokens

- [ ] **Step 3: Design token audit**

Run:
```bash
cd ios-app/CozyPup/Views/Settings && grep -nE 'Color\(\.|Color\.white|Color\.black|Color\(red:|foregroundColor\(\.(white|black|gray|blue|red|orange|green))' UserProfileSheet.swift SettingsDrawer.swift DuoPlanSection.swift WhatsNewView.swift AcknowledgementsView.swift
```
Expected: NO matches (all colors go through `Tokens.*`).

Also:
```bash
cd ios-app/CozyPup/Views/Settings && grep -nE 'font\(\.system\(size: [0-9]|font\(\.title|font\(\.body|font\(\.caption|font\(\.headline' UserProfileSheet.swift SettingsDrawer.swift DuoPlanSection.swift WhatsNewView.swift AcknowledgementsView.swift
```
Expected: at most the intentional `.system(size: 32, weight: .semibold)` in the fallback avatar (which is the pre-existing pattern matching the original code). Anything else must go through `Tokens.fontX`.

- [ ] **Step 4: Backend regression check**

Run: `cd backend && pytest tests/test_auth_me.py tests/test_storage.py tests/test_subscription.py -v`
Expected: all PASS.

- [ ] **Step 5: Write QA report**

Create a short results file or comment in the PR/commit summarizing pass/fail counts and any issues found. Any failures should be fixed before the next task by opening a new subagent task pointing at the failing row.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit --allow-empty -m "chore: QA verification pass for settings & profile redesign

Walked the QA matrix from the design spec. All rows ✅."
```

(If any ❌, do not run this commit — open a fix task first.)

---

## Task 16: Cleanup

- [ ] **Step 1: Remove stale UserDefaults key from any pre-existing installs**

There's no migration needed — the key `cozypup_notification_prefs` will simply be ignored and garbage-collected by iOS. No action required unless a test fails because of a stale preview cache, in which case reset the simulator.

- [ ] **Step 2: Update `CLAUDE.md` if any new conventions were introduced**

Skim `CLAUDE.md` for references to the old 3-toggle notification preferences or the `/auth/me` response shape. If found, update.

- [ ] **Step 3: Final commit**

```bash
git add CLAUDE.md 2>/dev/null || true
git commit -m "docs: sync CLAUDE.md with settings redesign" 2>/dev/null || echo "No doc changes"
```

---

## Spec Coverage Self-Review

Checking each section of the spec against the task list:

- [x] **IA split (Settings=app, Profile=person)** → Tasks 13 & 14
- [x] **Duo linked-friend row (payer/member/pending/upgrade)** → Task 12 (component) + Task 13 (integration)
- [x] **Avatar editable via PhotosPicker + POST /auth/me/avatar** → Task 3 (backend) + Task 13 (iOS)
- [x] **GET /auth/me returns avatar_url** → Task 1
- [x] **PATCH /auth/me unchanged** → Task 1 (return shape updated, body schema unchanged)
- [x] **phone_number stays on model, unused in UI** → No task needed (already true)
- [x] **Apple compliance: Restore Purchases** → Task 13 (calls `subscriptionStore.restorePurchases()` which exists)
- [x] **Apple compliance: Manage Subscription** → Task 13 (uses `AppStore.showManageSubscriptions`)
- [x] **Apple compliance: Terms of Use** → Task 13 (via `AppConfig.termsOfUseURL` + SafariWebView)
- [x] **Notifications: single toggle → system settings** → Task 14
- [x] **Legal: Privacy/Terms via SFSafariViewController, Disclaimer in-app** → Tasks 6 + 13
- [x] **Acknowledgements page** → Tasks 10 + 13
- [x] **What's New page** → Tasks 8 + 9 + 14
- [x] **Version label from Bundle** → Tasks 5 + 13 + 14
- [x] **Delete Settings "Subscription" button** → Task 14
- [x] **Delete 3 notification toggles + cozypup_notification_prefs** → Task 14
- [x] **Contact Support, Report a Problem (mailto)** → Task 14
- [x] **Rate CozyPup (SKStoreReviewController)** → Task 14
- [x] **Share CozyPup (UIActivityViewController), disabled when URL empty** → Tasks 7 + 14
- [x] **Placeholders in AppConfig.swift** → Task 5
- [x] **QA matrix verification** → Task 15
- [x] **Design token audit** → Task 15 Step 3
- [x] **Backend tests** → Tasks 1-3 + Task 15 Step 4

No gaps. Plan is complete.
