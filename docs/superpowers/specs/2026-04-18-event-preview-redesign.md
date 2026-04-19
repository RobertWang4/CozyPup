# Event Preview Redesign

**Date**: 2026-04-18
**Status**: Approved, ready for implementation

## Goal

Replace the current long-press system `contextMenu` (edit / delete) and the full-screen `EventEditSheet` with a **unified floating preview card** that:

1. **Rises from the original event row position** (matchedGeometryEffect-style animation)
2. Serves as a **beautiful, shareable preview** — image-ready for WeChat Moments
3. Toggles **in-place into edit mode** (same card frame, fields become editable)
4. Offers **image-export sharing** with multiple layout options when multiple photos exist

## Non-goals

- Redesigning the timeline/day-chat views themselves
- Backend changes (reuse existing `CalendarEvent` model and endpoints)
- Reminders logic changes (reuse existing `reminder_at` field)

## Interaction

### Entry points
Long-press any event in these views (all currently use `contextMenu`):
- `EventRow.swift` (MonthGrid day list)
- `TimelineEventCard.swift` (DayChatSheet)
- `MultiDayTimelineView.swift` (multi-day list)

Replace each `.contextMenu { ... }` with the long-press gesture that opens the new preview overlay.

### Overlay behavior
- Background dims + blurs (`rgba(30,20,10,0.45)` + blur 4)
- Source card visually "rises" and scales to the floating card via matched geometry
- Tap outside the card, tap dim bg, or swipe down → collapse back to origin
- Three action buttons pinned near bottom: **编辑 (soft) · 分享 (accent primary) · 删除 (red)**

### States
```
Preview mode (default) ──[✎ 编辑]──▶ Edit mode
     ▲                                  │
     └──────[✓ 保存] or [取消]──────────┘
```

Same floating card frame, same position/size. Only interior content and bottom actions swap.

## Preview Mode — Card Content

Top-to-bottom inside the floating card:

| Element | Data source | Notes |
|---|---|---|
| Category chip | `event.category` | Colored dot + uppercase label (日常/饮食/医疗/异常), accent color per category |
| Reminder bell | `event.reminderAt != nil` | Top-right, accent color, small |
| **Hero area** | see fallback rules below | 200pt tall, 12pt corner radius |
| Carousel dots | `event.photos.count > 1` | Accent active dot elongated |
| Date header | `event.eventDate` | Letter-spaced uppercase, `2026 · 04 · 15 · 周三` |
| Title | `event.title` | Serif, 24pt, weight 400 |
| Pet tags | `event.petTags` (fallback `event.petName`) | Pill tags with color dots |
| Divider | | 0.5pt `#F0E4D4` |
| Info rows | show only when populated | Time / Location / Cost |
| Brand footer | constant | `COZYPUP 🐾 2026.04.15`, faint, letter-spaced |

### Hero fallback logic
1. `event.photos.count > 0` → **peek carousel** (see below)
2. else if event has location (`locationLat/Lng`) → **MapKit snapshot** of that location
3. else → **pet avatar** (first tagged pet) on warm gradient background (pet's `colorIndex` tint)

### Peek carousel (new)
New component: `PeekPhotoCarousel`

- Center photo: flex-1, full height (200pt), drop shadow
- Side photos: 28pt wide × 140pt tall, opacity 0.6, rounded
- First photo: no left peek; last: no right peek
- Single photo: no peek, centered full width
- Swipe horizontally with spring animation to change center
- Tap a side photo also cycles to it
- Top-right overlay: `"2 / 3"` counter when count > 1
- Below carousel: elongated-dot position indicator
- **peek width token**: `28pt` (confirmed: narrow, main-photo-first)

## Edit Mode — Same Card, Editable Fields

The floating card stays in the exact same frame. Internal content crossfades between preview and edit layouts.

| Field | Preview | Edit |
|---|---|---|
| Category | Read-only chip | Horizontal row of 4 selectable chips |
| Hero | Peek carousel | Main photo (cropped to 150pt) + thumbnail row with ✕ delete per photo + dashed "+" add button |
| Title | Serif read-only | Serif `TextField` with accent underline |
| Date | Read-only label | Tap → system `DatePicker` sheet |
| Time | Read-only label | Tap → system time picker, clearable |
| Pet tags | Read-only pills | Each pill gets ✕; dashed "+" opens pet selector |
| Location | Read-only row | Tap → existing `LocationPickerSheet` |
| Cost | Read-only `$ 85` | Numeric `TextField` |
| **Reminder** *(new to card)* | Hidden (only shown as bell icon) | Full row: toggle + time label. When enabled → time picker |
| **Type** *(new to card)* | Hidden | Row with picker: 记录 (log) / 预约 (appointment) |
| **Notes** *(new to card)* | Hidden unless set; when set, shown on preview as extra info row | Multi-line `TextEditor`, placeholder "补充信息（选填）" |

Bottom actions change to: **取消** · **✓ 保存** (accent primary).

- **Save** → writes through existing `onSave` / `onLocationUpdate` / `onPhotoUpload` / `onPhotoDelete` closures; card returns to preview mode (does not collapse).
- **Cancel** → discards all in-memory edits; card returns to preview mode.

### Note on the "Notes" field
`CalendarEvent` does not currently have a user-facing description field separate from `title`. The existing `raw_text` is the original chat message, not user-editable. **Scope decision**: add a new `notes` field to the model (nullable string). Backend schema migration required.

Why: The preview card's aesthetic goal (Moments-shareable) benefits from a free-form caption area independent of the short title.

## Share Flow

Tap **↗ 分享** on preview card:

- **0 photos or 1 photo**: skip picker, directly render default single-layout share image
- **2+ photos**: bottom sheet with 4 layout choices:
  1. **单张大图** — use currently-centered carousel photo only
  2. **保持 peek 排列** — match in-app visual
  3. **九宫格** — grid (2×2 for 2–4 photos, 3×3 for 5+)
  4. **主图 + 缩略** — main photo + thumbnail strip

All layouts include the card's metadata (category chip, title, date, pets, location, cost, notes) and the `COZYPUP 🐾 yyyy.MM.dd` brand footer.

Image generated via `ImageRenderer` at 3× scale. Share via `ShareLink` (system share sheet: save to Photos, WeChat, AirDrop, etc.).

## Design Tokens

All colors/fonts/spacing must use existing `Tokens.*`. New constants needed:

```swift
// Tokens.swift — additions
extension Tokens {
    static let dimOverlay = Color.black.opacity(0.45) // verify this already exists
    // Peek carousel
    struct Peek {
        static let sideWidth: CGFloat = 28
        static let mainHeight: CGFloat = 200
        static let spacing: CGFloat = 6
    }
}
```

Verify before adding — some may already exist.

## File Changes

### New files (iOS)

- `Views/Calendar/EventPreviewOverlay.swift` — root overlay with matched geometry, dim/blur, dismissal
- `Views/Calendar/EventPreviewCard.swift` — card body (preview state)
- `Views/Calendar/EventEditCard.swift` — card body (edit state); replaces EventEditSheet for this flow
- `Views/Calendar/PeekPhotoCarousel.swift` — new reusable component
- `Views/Calendar/EventShareLayoutPicker.swift` — bottom sheet for multi-photo layout choice
- `Views/Calendar/EventShareRenderer.swift` — `ImageRenderer`-based export for 4 layouts
- `Views/Calendar/MapSnapshotView.swift` — MapKit snapshot fallback for hero

### Modified files (iOS)

- `Views/Calendar/EventRow.swift` — remove `.contextMenu`, add `.onLongPressGesture` → open overlay
- `Views/Calendar/TimelineEventCard.swift` — same change
- `Views/Calendar/MultiDayTimelineView.swift` — same change
- `Views/Calendar/CalendarDrawer.swift` — host the overlay at drawer root (so animation can rise above all content)
- `Views/Calendar/DayChatSheet.swift` — same (host overlay)
- `Models/CalendarEvent.swift` — add `notes: String?` field
- `Stores/CalendarStore.swift` — pass `notes` through create/update
- `CozyPup/Theme/Tokens.swift` — add `Peek` constants (if not already)

### Delete
- `Views/Calendar/EventEditSheet.swift` — superseded by `EventEditCard.swift` (confirm no other callers before deleting; search first)

### Backend

- `backend/app/models.py` — add `notes` column to `CalendarEvent`
- `alembic revision --autogenerate -m "add notes to calendar_events"`
- `backend/app/schemas/calendar.py` — add `notes` to request/response
- `backend/app/routers/calendar.py` — thread `notes` through CRUD
- `backend/app/agents/tools/calendar.py` (if exists) — allow LLM to set `notes` when recording events

## Testing

- **Unit**: `PeekPhotoCarousel` — scroll-to-index, correct clamping at endpoints, dot indicator state
- **Unit**: `EventShareRenderer` — each of 4 layouts renders without crashing with 0/1/3/9 photos
- **Integration**: matched-geometry transition — visual smoke test via `#Preview`
- **Manual (golden path)**:
  1. Long-press event → preview rises
  2. Tap outside → collapses
  3. Tap edit → edit mode, modify title + add reminder + save → preview reflects changes
  4. Tap share with 3 photos → picker appears; select 九宫格 → share sheet opens with generated image
  5. Tap delete → confirms + removes event
  6. Cover all three entry points (EventRow / TimelineEventCard / MultiDayTimelineView)

## Accessibility

- All action buttons labeled (`.accessibilityLabel`)
- Carousel swipe also works via `.accessibilityAdjustableAction` (increment/decrement)
- Minimum touch target 44pt for all action buttons (they already are via `Tokens.size.buttonMedium`)

## Migration / Rollout

- No feature flag; ship behind current release cycle
- On app update, old data (events without `notes`) renders normally (nullable)
- Backend migration is additive only — safe under concurrent writes

## Open Questions

None — all design decisions confirmed in brainstorming.

## Reference

Design mockups live in `.superpowers/brainstorm/2386-1776568589/content/`:
- `final-design.html` — preview card fields + layout
- `edit-mode.html` — edit state fields
- `preview-vs-edit.html` — side-by-side comparison
- `peek-carousel.html` — carousel behavior
- `share-picker.html` — share layout picker
