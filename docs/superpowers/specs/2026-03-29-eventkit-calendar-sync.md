# EventKit Calendar Sync Design

Date: 2026-03-29

## Goal

Integrate iOS EventKit to sync CozyPup calendar events to the native Apple Calendar app. Single-direction sync (App → System Calendar). Replace the in-app calendar page with a simpler timeline view — users see pet events in Apple Calendar alongside their personal schedule.

## Core Principles

- **One-way sync**: App creates/updates/deletes → system calendar reflects. Changes made directly in Apple Calendar are NOT synced back.
- **Per-pet calendars**: Each pet gets its own `EKCalendar` with the pet's color from the palette.
- **Lazy authorization**: Request EventKit permission only when the first calendar operation occurs, not during onboarding.
- **Silent degradation**: If user denies permission, everything else works — just no system calendar sync.
- **Zero backend changes**: All work is iOS-side.

## New Component: `CalendarSyncService`

New file: `ios-app/CozyPup/Services/CalendarSyncService.swift`

A stateless utility wrapping EventKit operations. Not an ObservableObject — called by stores as needed.

### Public API

```swift
final class CalendarSyncService {
    static let shared = CalendarSyncService()

    /// Request calendar access. Returns true if granted.
    func requestAccess() async -> Bool

    /// Check current authorization status without prompting.
    var isAuthorized: Bool { get }

    /// Create or retrieve the EKCalendar for a pet. Stores mapping in UserDefaults.
    func ensureCalendar(petId: String, petName: String, colorHex: String) -> EKCalendar?

    /// Sync a CalendarEvent to system calendar. Creates EKEvent, stores identifier mapping.
    func syncEvent(_ event: CalendarEvent) -> Bool

    /// Update an existing synced event.
    func updateEvent(_ event: CalendarEvent) -> Bool

    /// Delete a synced event by its CozyPup event ID.
    func deleteEvent(eventId: String) -> Bool

    /// Delete multiple synced events.
    func deleteEvents(eventIds: Set<String>)

    /// Rename a pet's calendar.
    func renamePetCalendar(petId: String, newName: String)

    /// Delete a pet's calendar and all its events.
    func deletePetCalendar(petId: String)

    /// Bulk sync all existing events for a pet (used after first authorization).
    func bulkSync(events: [CalendarEvent])
}
```

### EKEvent Field Mapping

| CalendarEvent field | EKEvent field |
|---------------------|---------------|
| `title` | `title` |
| `eventDate` + `eventTime` | `startDate` / `endDate` (1-hour default if time set, all-day if no time) |
| `category` | `notes` (prefixed with category label) |
| `rawText` | `notes` (appended) |
| `locationName` | `structuredLocation.title` |
| `locationLat` + `locationLng` | `structuredLocation.geoLocation` |
| `id` | `url` = `cozypup://calendar/event/{id}` |
| reminder type events | `addAlarm(EKAlarm(relativeOffset: -3600))` (1hr before) |

### Local Storage (UserDefaults)

Two dictionaries:
- `cozypup_ek_calendars`: `[petId: String → ekCalendarIdentifier: String]`
- `cozypup_ek_events`: `[calendarEventId: String → ekEventIdentifier: String]`

## Integration Points (Minimal Changes)

### CalendarStore

Each CRUD method gets one line added at the end:

- `add(_ event:)` → `CalendarSyncService.shared.syncEvent(event)`
- `update(...)` → `CalendarSyncService.shared.updateEvent(updatedEvent)`
- `remove(_ id:)` → `CalendarSyncService.shared.deleteEvent(eventId: id)`
- `removeMultiple(_ ids:)` → `CalendarSyncService.shared.deleteEvents(eventIds: ids)`

### PetStore

- Pet rename → `CalendarSyncService.shared.renamePetCalendar(petId:newName:)`
- Pet delete → `CalendarSyncService.shared.deletePetCalendar(petId:)`

### Deep Link

- Register `cozypup` URL scheme in Info.plist (`CFBundleURLSchemes`)
- `CozyPupApp.swift`: add `.onOpenURL { url in ... }` to route `cozypup://calendar/event/{id}` to the event detail view

### Settings

- Add a toggle in Settings for "Sync to Apple Calendar" (on/off)
- When toggled on for the first time → request authorization → bulk sync existing events
- When toggled off → stop syncing (keep existing system calendar events, just stop writing new ones)
- Store preference in UserDefaults: `cozypup_calendar_sync_enabled`

### Info.plist

- `NSCalendarsFullAccessUsageDescription`: "CozyPup syncs pet health events to your calendar so you can see appointments alongside your schedule."
- `CFBundleURLSchemes`: `["cozypup"]`

## Authorization Flow

```
User triggers calendar-related action (e.g., AI creates event)
  → Check cozypup_calendar_sync_enabled (default: true for new users)
  → Check EKEventStore.authorizationStatus
  → .notDetermined → requestFullAccessToEvents()
    → Granted → ensureCalendar() → syncEvent() → bulkSync existing events
    → Denied → set cozypup_calendar_sync_enabled = false, continue silently
  → .fullAccess → ensureCalendar() → syncEvent()
  → .denied/.restricted → skip silently
```

## Per-Pet Calendar Structure

```
Apple Calendar App
├── Personal          (user's own)
├── Work              (user's own)
├── Mochi             (CozyPup, color #E8835C)
└── Luna              (CozyPup, color #6BA3BE)
```

Colors use the existing pet color palette: `["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]`

Calendar source: use `EKSource` with type `.local` (or `.calDAV` if iCloud is available).

## Edge Cases

- **Pet has no events yet**: Calendar created lazily on first event sync, not on pet creation.
- **App reinstalled**: Mappings lost. On next sync attempt, check if calendar with pet name exists in CozyPup source before creating a new one. Orphaned events in old calendars are harmless.
- **Multiple devices**: Each device creates its own calendars. If user has iCloud Calendar, events may appear on all devices (this is a feature, not a bug).
- **Event has no time**: Create as all-day event (`isAllDay = true`).
- **Event has multiple pets (pet_tags)**: Sync to the first pet's calendar. Add other pet names in the event title suffix.

## What This Design Does NOT Do

- No reverse sync (system calendar → app)
- No `EKEventStoreChanged` observer
- No backend changes
- No new API endpoints
- No CalendarKit or third-party calendar UI libraries
