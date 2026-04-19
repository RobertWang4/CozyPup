# Pet Detail Redesign

**Date**: 2026-04-18
**Status**: Approved, ready for implementation

## Goal

Replace the current **编辑宠物** modal sheet (utilitarian form) with a **journal-style pet detail page** that feels like opening a book chapter. Same data, dramatically better presentation. Split into browse / edit modes, same frame, crossfade transition.

## Non-goals

- **No new fields**. Stay 1:1 with the current `Pet` model: `name`, `species`, `breed`, `gender`, `birthday`, `weight`, `colorIndex`, `profileMd` (AI-generated).
- Structured fields like neutering / fur color / personality tags should remain in `profileMd` (AI-maintained), not added as columns.
- No changes to the AI profile-generation pipeline.

## Design — "Journal" (Direction B)

Three chapters, scrollable single screen:

### Chapter I · 封面 (Cover)
- Card: `Tokens.surface`, 20pt radius, 18pt padding
- Left column:
  - Eyebrow: `Chapter I · 主角` (letter-spaced, `textTertiary`, 9pt uppercase)
  - **Pet name**: vertical-axis serif, 38pt, `Tokens.text`. Uses Chinese vertical writing mode (`writing-mode: vertical-rl` equivalent in SwiftUI — stack characters or rotate a serif Text).
  - Ornament: `— 🐾 —` at bottom (accent color)
- Right column: Pet avatar, 100×140pt, 12pt radius. Tap to view full; edit mode shows camera badge overlay.

### Chapter II · 档案 (Index)
- Card: `Tokens.surface`, 20pt radius, 22pt horizontal padding
- Dotted-line separator rows (`border-bottom: 0.5pt dotted #D4C4B0`)
- Each row: left label (10pt uppercase letter-spaced `textTertiary`) + right value (14pt serif `text`)
- Rows (in order):
  1. 类型 (species) — 狗 / 猫 / ...
  2. 品种 (breed)
  3. 性别 (gender) — ♂ 公 / ♀ 母
  4. 生日 (birthday) — `2023 · 07 · 22` dot-separated serif
  5. 年龄 (age, computed) — `2 岁 9 月` in `accent` color
  6. 体重 (weight) — `15.0 kg`

### Chapter III · AI 档案
- Card: gradient `Tokens.surface → Tokens.surface2`, 20pt radius
- Sparkle glyph ✦ top-right in `accentSoft` tone
- Eyebrow: `Chapter III · AI 档案` (accent letter-spaced)
- Serif title: `关于维尼` (17pt)
- Preview: first ~3 lines of `profileMd`, then dashed divider + `完整档案 · 编辑 ›` (tap → existing full profile editor — reuse current `PetProfileMarkdownView` or equivalent)
- **Not editable inline** — the AI profile has its own page. Edit mode shows this card with muted/italic note: "AI 生成，此页不编辑"

### Toolbar
- Top bar: close `‹` (left) + `PROFILE` label (center, letter-spaced `textTertiary`) + accent `✎` edit button (right)
- In edit mode: `‹` becomes `✕`, center label becomes `EDITING` in accent color, right button hidden.

## Edit Mode — Same Frame, Inline Fields

Crossfade, no layout shift. Card frames, paddings, radii unchanged.

| Field | Browse | Edit |
|---|---|---|
| Name | Large vertical serif | `TextField` on warm background, `#E8B999` underline |
| Avatar | Plain image | Image + camera badge overlay (existing picker flow) |
| 类型 | Read-only | Tap → sheet picker (狗 / 猫 / 其他) |
| 品种 | Read-only | `TextField` |
| 性别 | Read-only | Tap → sheet picker (公 / 母 / 未知) |
| 生日 | Read-only | Tap → `DatePicker` sheet |
| 年龄 | Computed read-only | Hidden (derived from birthday) |
| 体重 | Read-only | Decimal `TextField` |
| AI 档案 | Preview card | Muted card, "编辑完整档案 ›" leads to dedicated page |

Bottom bar (edit mode only): floating **[取消]** + accent **[✓ 保存]** buttons. Cancel discards; Save persists and returns to browse mode without dismissing the page.

## Navigation

- Entry: replace wherever `PetEditSheet` (or current "编辑宠物" page) is presented — most likely `Views/Settings/*` or `Views/Chat/` pet switcher.
- If current entry is a sheet, keep it a sheet; if NavigationStack, push it.
- Dismiss: close button → dismiss the sheet/pop the stack (current behavior).

## File Changes (iOS only)

### New
- `Views/Pet/PetDetailView.swift` — root: browse ↔ edit state container
- `Views/Pet/PetCoverCard.swift` — Chapter I
- `Views/Pet/PetIndexCard.swift` — Chapter II (kv rows)
- `Views/Pet/PetProfileBioCard.swift` — Chapter III (AI preview)
- `Views/Pet/VerticalSerifText.swift` — helper for vertical-axis serif name
- `Views/Pet/PetAgeCalculator.swift` — helper: birthday → "X 岁 Y 月" or "X 个月" for <1yr

### Modified
- Callers of the existing `PetEditSheet`/"编辑宠物" sheet — swap in `PetDetailView`
- `Models/Pet.swift` — add computed `ageText: String` property (or compute inside view; prefer view for locale flexibility)

### Delete after verification
- Existing `PetEditSheet` (or whatever the current 编辑宠物 file is called) — confirm no other callers

## Tokens

All Tokens already exist except vertical-text helper (behavior, not color). No Tokens changes needed.

## Accessibility

- VoiceOver reads pet name, then index chapter ("品种：可卡布" etc.) naturally
- Save/Cancel buttons: clear `accessibilityLabel`
- Vertical serif name: fall back to horizontal for Dynamic Type (large accessibility sizes) — vertical writing looks bad when scaled 2×+

## Localization

- Chapter labels `Chapter I/II/III` — keep in English in zh + en (design element, not copy); can revisit
- 类型 / 品种 / 性别 / 生日 / 年龄 / 体重 labels via existing `L.*` strings (add if missing)
- Age formatter: "2 岁 9 月" / "3 months" — handle zh vs en in `PetAgeCalculator`

## Testing

- **Unit**: `PetAgeCalculator` — edge cases: today, 1 day old, 1 month, 11 months, 1 year 0 months, 2 years 9 months
- **Unit**: `VerticalSerifText` — renders CJK and Latin characters
- **Manual**:
  1. Open pet detail → see three chapters
  2. Tap ✎ → fields editable, frame unchanged
  3. Edit name + weight → Save → values reflect
  4. Cancel → edits discarded
  5. Tap AI 档案 card → opens full profile page
  6. Pet with no birthday → age row hidden
  7. Pet with no breed → breed row shows placeholder `—`
  8. Dynamic Type XXL → layout stays readable, vertical name falls back to horizontal

## Open Questions

None — scope locked to existing fields. Timeline from calendar events deferred.

## Reference mockups

`.superpowers/brainstorm/2386-1776568589/content/`:
- `pet-directions.html` — all 3 directions, B selected
- `pet-journal-lean.html` — final B with only existing fields, browse + edit side-by-side
