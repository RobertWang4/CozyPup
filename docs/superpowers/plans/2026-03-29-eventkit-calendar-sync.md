# EventKit Calendar Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync CozyPup calendar events to the native Apple Calendar app (one-way: app → system calendar), with per-pet calendars, location sync, and deep links back to the app.

**Architecture:** New `CalendarSyncService` wraps EventKit. CalendarStore and PetStore call it after each CRUD operation. Two UserDefaults dictionaries store petId→ekCalendarId and eventId→ekEventId mappings. Deep links via `cozypup://` URL scheme.

**Tech Stack:** EventKit, CoreLocation (for CLLocation in structuredLocation), SwiftUI

**Spec:** `docs/superpowers/specs/2026-03-29-eventkit-calendar-sync.md`

---

### Task 1: Create CalendarSyncService

**Files:**
- Create: `ios-app/CozyPup/Services/CalendarSyncService.swift`

- [ ] **Step 1: Create CalendarSyncService with authorization**

```swift
import EventKit
import CoreLocation

final class CalendarSyncService {
    static let shared = CalendarSyncService()
    private let store = EKEventStore()

    private let calendarMapKey = "cozypup_ek_calendars"
    private let eventMapKey = "cozypup_ek_events"
    private let syncEnabledKey = "cozypup_calendar_sync_enabled"

    private init() {}

    // MARK: - Authorization

    var isSyncEnabled: Bool {
        // Default true for new users (key not set yet)
        if UserDefaults.standard.object(forKey: syncEnabledKey) == nil { return true }
        return UserDefaults.standard.bool(forKey: syncEnabledKey)
    }

    func setSyncEnabled(_ enabled: Bool) {
        UserDefaults.standard.set(enabled, forKey: syncEnabledKey)
    }

    var isAuthorized: Bool {
        EKEventStore.authorizationStatus(for: .event) == .fullAccess
    }

    func requestAccess() async -> Bool {
        guard isSyncEnabled else { return false }
        do {
            return try await store.requestFullAccessToEvents()
        } catch {
            print("CalendarSyncService: access denied — \(error)")
            return false
        }
    }

    /// Ensure authorized before any operation. Returns false if not authorized.
    private func ensureAccess() async -> Bool {
        if isAuthorized { return true }
        if EKEventStore.authorizationStatus(for: .event) == .notDetermined {
            return await requestAccess()
        }
        return false
    }

    // MARK: - Calendar Mapping (petId → ekCalendarIdentifier)

    private var calendarMap: [String: String] {
        get { UserDefaults.standard.dictionary(forKey: calendarMapKey) as? [String: String] ?? [:] }
        set { UserDefaults.standard.set(newValue, forKey: calendarMapKey) }
    }

    // MARK: - Event Mapping (eventId → ekEventIdentifier)

    private var eventMap: [String: String] {
        get { UserDefaults.standard.dictionary(forKey: eventMapKey) as? [String: String] ?? [:] }
        set { UserDefaults.standard.set(newValue, forKey: eventMapKey) }
    }

    // MARK: - Calendar Management

    /// Get or create an EKCalendar for a pet.
    func ensureCalendar(petId: String, petName: String, colorHex: String) -> EKCalendar? {
        // Check existing mapping
        if let identifier = calendarMap[petId],
           let calendar = store.calendar(withIdentifier: identifier) {
            return calendar
        }

        // Find a suitable source (prefer iCloud/CalDAV, fallback to local)
        let source = store.sources.first(where: { $0.sourceType == .calDAV })
            ?? store.sources.first(where: { $0.sourceType == .local })
            ?? store.defaultCalendarForNewEvents?.source

        guard let src = source else {
            print("CalendarSyncService: no calendar source available")
            return nil
        }

        let calendar = EKCalendar(for: .event, eventStore: store)
        calendar.title = petName
        calendar.source = src
        calendar.cgColor = UIColor(hex: colorHex).cgColor

        do {
            try store.saveCalendar(calendar, commit: true)
            var map = calendarMap
            map[petId] = calendar.calendarIdentifier
            calendarMap = map
            return calendar
        } catch {
            print("CalendarSyncService: failed to create calendar — \(error)")
            return nil
        }
    }

    // MARK: - Event Sync

    func syncEvent(_ event: CalendarEvent) async {
        guard isSyncEnabled, await ensureAccess() else { return }

        let petId = event.petId ?? event.petTags.first?.id ?? ""
        let petName = event.petName ?? event.petTags.first?.name ?? "Pet"
        let colorHex = event.petColorHex ?? event.petTags.first?.color_hex ?? "E8835C"

        guard let calendar = ensureCalendar(petId: petId, petName: petName, colorHex: colorHex) else { return }

        let ekEvent = EKEvent(eventStore: store)
        configureEKEvent(ekEvent, from: event, calendar: calendar)

        do {
            try store.save(ekEvent, span: .thisEvent)
            var map = eventMap
            map[event.id] = ekEvent.eventIdentifier
            eventMap = map
        } catch {
            print("CalendarSyncService: failed to save event — \(error)")
        }
    }

    func updateEvent(_ event: CalendarEvent) async {
        guard isSyncEnabled, await ensureAccess() else { return }

        guard let ekId = eventMap[event.id],
              let ekEvent = store.event(withIdentifier: ekId) else {
            // No mapping — create instead
            await syncEvent(event)
            return
        }

        let petId = event.petId ?? event.petTags.first?.id ?? ""
        let petName = event.petName ?? event.petTags.first?.name ?? "Pet"
        let colorHex = event.petColorHex ?? event.petTags.first?.color_hex ?? "E8835C"

        if let calendar = ensureCalendar(petId: petId, petName: petName, colorHex: colorHex) {
            configureEKEvent(ekEvent, from: event, calendar: calendar)
        }

        do {
            try store.save(ekEvent, span: .thisEvent)
        } catch {
            print("CalendarSyncService: failed to update event — \(error)")
        }
    }

    func deleteEvent(eventId: String) async {
        guard isSyncEnabled, await ensureAccess() else { return }

        guard let ekId = eventMap[eventId],
              let ekEvent = store.event(withIdentifier: ekId) else { return }

        do {
            try store.remove(ekEvent, span: .thisEvent)
            var map = eventMap
            map.removeValue(forKey: eventId)
            eventMap = map
        } catch {
            print("CalendarSyncService: failed to delete event — \(error)")
        }
    }

    func deleteEvents(eventIds: Set<String>) async {
        for id in eventIds {
            await deleteEvent(eventId: id)
        }
    }

    // MARK: - Pet Calendar Management

    func renamePetCalendar(petId: String, newName: String) async {
        guard isSyncEnabled, await ensureAccess() else { return }
        guard let identifier = calendarMap[petId],
              let calendar = store.calendar(withIdentifier: identifier) else { return }

        calendar.title = newName
        do {
            try store.saveCalendar(calendar, commit: true)
        } catch {
            print("CalendarSyncService: failed to rename calendar — \(error)")
        }
    }

    func deletePetCalendar(petId: String) async {
        guard isSyncEnabled, await ensureAccess() else { return }
        guard let identifier = calendarMap[petId],
              let calendar = store.calendar(withIdentifier: identifier) else { return }

        do {
            try store.removeCalendar(calendar, commit: true)
            var map = calendarMap
            map.removeValue(forKey: petId)
            calendarMap = map
            // Clean up event mappings for this pet's events
            // (calendar deletion removes all events automatically)
        } catch {
            print("CalendarSyncService: failed to delete calendar — \(error)")
        }
    }

    // MARK: - Bulk Sync

    func bulkSync(events: [CalendarEvent]) async {
        guard isSyncEnabled, await ensureAccess() else { return }
        for event in events {
            // Skip if already synced
            if eventMap[event.id] != nil { continue }
            await syncEvent(event)
        }
    }

    // MARK: - Private Helpers

    private func configureEKEvent(_ ekEvent: EKEvent, from event: CalendarEvent, calendar: EKCalendar) {
        ekEvent.calendar = calendar

        // Title: include other pet names if multi-pet
        if event.petTags.count > 1 {
            let otherNames = event.petTags.dropFirst().map(\.name).joined(separator: ", ")
            ekEvent.title = "\(event.title) (\(otherNames))"
        } else {
            ekEvent.title = event.title
        }

        // Date & Time
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        guard let date = dateFormatter.date(from: event.eventDate) else { return }

        if let timeStr = event.eventTime {
            dateFormatter.dateFormat = "yyyy-MM-dd HH:mm"
            if let startDate = dateFormatter.date(from: "\(event.eventDate) \(timeStr)") {
                ekEvent.startDate = startDate
                ekEvent.endDate = startDate.addingTimeInterval(3600) // 1 hour default
                ekEvent.isAllDay = false
            } else {
                ekEvent.startDate = date
                ekEvent.endDate = date
                ekEvent.isAllDay = true
            }
        } else {
            ekEvent.startDate = date
            ekEvent.endDate = date
            ekEvent.isAllDay = true
        }

        // Notes
        var notes = "[\(event.category.rawValue)]"
        if !event.rawText.isEmpty { notes += "\n\(event.rawText)" }
        ekEvent.notes = notes

        // Location
        if let locName = event.locationName {
            let structured = EKStructuredLocation(title: locName)
            if let lat = event.locationLat, let lng = event.locationLng {
                structured.geoLocation = CLLocation(latitude: lat, longitude: lng)
            }
            ekEvent.structuredLocation = structured
        } else {
            ekEvent.structuredLocation = nil
        }

        // Deep link
        ekEvent.url = URL(string: "cozypup://calendar/event/\(event.id)")

        // Alarm for reminders/appointments
        if event.type == .reminder || event.type == .appointment {
            if ekEvent.alarms == nil || ekEvent.alarms!.isEmpty {
                ekEvent.addAlarm(EKAlarm(relativeOffset: -3600))
            }
        }
    }
}

// MARK: - UIColor hex helper (for cgColor)

private extension UIColor {
    convenience init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xFF) / 255.0
        let g = Double((int >> 8) & 0xFF) / 255.0
        let b = Double(int & 0xFF) / 255.0
        self.init(red: r, green: g, blue: b, alpha: 1.0)
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Services/CalendarSyncService.swift
git commit -m "feat: add CalendarSyncService for EventKit integration"
```

---

### Task 2: Integrate CalendarSyncService into CalendarStore

**Files:**
- Modify: `ios-app/CozyPup/Stores/CalendarStore.swift`

- [ ] **Step 1: Add sync calls to CalendarStore CRUD methods**

Add to `add(_ event:)` — after `events.append(event)` and `saveLocal()` (line 52), before the Task block:

```swift
// Sync to system calendar
Task { await CalendarSyncService.shared.syncEvent(event) }
```

Add to `update(...)` — after `saveLocal()` (line 104):

```swift
// Sync updated event to system calendar
let updatedEvent = events[idx]
Task { await CalendarSyncService.shared.updateEvent(updatedEvent) }
```

Add to `remove(_ id:)` — after `saveLocal()` (line 132):

```swift
// Remove from system calendar
Task { await CalendarSyncService.shared.deleteEvent(eventId: id) }
```

Add to `removeMultiple(_ ids:)` — after `saveLocal()` (line 145):

```swift
// Remove from system calendar
Task { await CalendarSyncService.shared.deleteEvents(eventIds: ids) }
```

Add to `updateLocation(...)` — after `saveLocal()` (line 192):

```swift
// Sync location to system calendar
if let event = events.first(where: { $0.id == eventId }) {
    Task { await CalendarSyncService.shared.updateEvent(event) }
}
```

Add to `removeLocation(...)` — after `saveLocal()` (line 225):

```swift
// Sync location removal to system calendar
if let event = events.first(where: { $0.id == eventId }) {
    Task { await CalendarSyncService.shared.updateEvent(event) }
}
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Stores/CalendarStore.swift
git commit -m "feat: hook CalendarStore CRUD into EventKit sync"
```

---

### Task 3: Integrate CalendarSyncService into PetStore

**Files:**
- Modify: `ios-app/CozyPup/Stores/PetStore.swift`

- [ ] **Step 1: Add sync calls for pet rename and delete**

In `update(_ id:name:species:breed:birthday:weight:)` — after the successful API response updates the pet (line 93, inside the `do` block after `saveLocal()`), add:

```swift
// Sync pet name change to system calendar
Task { await CalendarSyncService.shared.renamePetCalendar(petId: id, newName: name) }
```

Also in the `catch` fallback (line 105, after `saveLocal()`), add the same line:

```swift
Task { await CalendarSyncService.shared.renamePetCalendar(petId: id, newName: name) }
```

In `remove(_ id:)` — before `pets.removeAll` (line 135), add:

```swift
// Remove pet calendar from system
Task { await CalendarSyncService.shared.deletePetCalendar(petId: id) }
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Stores/PetStore.swift
git commit -m "feat: sync pet rename/delete to EventKit calendars"
```

---

### Task 4: Add Deep Link URL Scheme and Handler

**Files:**
- Modify: `ios-app/CozyPup/CozyPupApp.swift`
- Modify: `ios-app/CozyPup.xcodeproj` (via Info.plist or Xcode target settings)

- [ ] **Step 1: Add URL scheme to Info.plist**

Add `CFBundleURLTypes` to the app's Info.plist (via Xcode target > Info > URL Types, or directly):

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>cozypup</string>
        </array>
        <key>CFBundleURLName</key>
        <string>com.robertwang.cozypup.dev</string>
    </dict>
</array>
```

- [ ] **Step 2: Add NSCalendarsFullAccessUsageDescription to Info.plist**

```xml
<key>NSCalendarsFullAccessUsageDescription</key>
<string>CozyPup syncs pet health events to your calendar so you can see appointments alongside your schedule.</string>
```

- [ ] **Step 3: Add onOpenURL handler in CozyPupApp.swift**

After `.environmentObject(Lang.shared)` (line 43), add:

```swift
.onOpenURL { url in
    // Handle cozypup://calendar/event/{id}
    guard url.scheme == "cozypup",
          url.host == "calendar",
          url.pathComponents.count >= 3,
          url.pathComponents[1] == "event" else { return }
    let eventId = url.pathComponents[2]
    // Post notification for ChatView to open calendar with this event
    NotificationCenter.default.post(
        name: .openCalendarEvent,
        object: nil,
        userInfo: ["eventId": eventId]
    )
}
```

Add notification name extension (at the bottom of CozyPupApp.swift or in a shared location):

```swift
extension Notification.Name {
    static let openCalendarEvent = Notification.Name("openCalendarEvent")
}
```

- [ ] **Step 4: Verify it compiles**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```
Expected: BUILD SUCCEEDED

- [ ] **Step 5: Commit**

```bash
git add ios-app/
git commit -m "feat: add cozypup:// URL scheme and deep link handler for calendar events"
```

---

### Task 5: Add Calendar Sync Toggle in Settings

**Files:**
- Modify: `ios-app/CozyPup/Views/Settings/SettingsDrawer.swift`

- [ ] **Step 1: Add sync toggle state and UI**

Add a state variable near line 9 (with the other `@State` vars):

```swift
@State private var calendarSync = CalendarSyncService.shared.isSyncEnabled
```

In the `Section(L.notifications)` block (line 191), add a new section right before it:

```swift
Section("Calendar") {
    Toggle("Sync to Apple Calendar", isOn: $calendarSync)
        .onChange(of: calendarSync) { _, newValue in
            CalendarSyncService.shared.setSyncEnabled(newValue)
            if newValue {
                // Request access and bulk sync existing events
                Task {
                    let granted = await CalendarSyncService.shared.requestAccess()
                    if granted {
                        await CalendarSyncService.shared.bulkSync(events: calendarStore.events)
                    } else {
                        calendarSync = false
                    }
                }
            }
        }
}
.tint(Tokens.green)
.listRowBackground(Tokens.surface)
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Views/Settings/SettingsDrawer.swift
git commit -m "feat: add calendar sync toggle in settings"
```

---

### Task 6: Wire Up First-Time Authorization on Event Creation

**Files:**
- Modify: `ios-app/CozyPup/Stores/CalendarStore.swift`

The `syncEvent` call in Task 2 already handles authorization lazily inside `CalendarSyncService.ensureAccess()`. But we also want to trigger bulk sync the first time access is granted.

- [ ] **Step 1: Add first-sync tracking**

In `CalendarSyncService.swift`, add a UserDefaults key:

```swift
private let didBulkSyncKey = "cozypup_ek_did_bulk_sync"
```

Update `syncEvent` — after `guard isSyncEnabled, await ensureAccess() else { return }`, add:

```swift
// First time sync: mark for bulk sync later
if !UserDefaults.standard.bool(forKey: didBulkSyncKey) {
    UserDefaults.standard.set(true, forKey: didBulkSyncKey)
    // Bulk sync will be triggered by the caller providing all events
}
```

In `CalendarStore.swift`, add a method to trigger initial bulk sync:

After `fetchMonth` method, add:

```swift
/// Called after first EventKit authorization to sync all cached events.
func triggerInitialSync() {
    Task {
        await CalendarSyncService.shared.bulkSync(events: events)
    }
}
```

In the `add(_ event:)` method, replace the simple sync call with:

```swift
// Sync to system calendar (handles first-time auth + bulk sync)
Task {
    let wasAuthorized = CalendarSyncService.shared.isAuthorized
    await CalendarSyncService.shared.syncEvent(event)
    // If this was the first authorization, bulk sync all existing events
    if !wasAuthorized && CalendarSyncService.shared.isAuthorized {
        await CalendarSyncService.shared.bulkSync(events: events)
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -5
```
Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Services/CalendarSyncService.swift ios-app/CozyPup/Stores/CalendarStore.swift
git commit -m "feat: trigger bulk sync on first EventKit authorization"
```

---

### Task 7: Build and Manual Test

- [ ] **Step 1: Full build**

```bash
cd ios-app && xcodebuild -project CozyPup.xcodeproj -scheme CozyPup \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build 2>&1 | tail -10
```
Expected: BUILD SUCCEEDED

- [ ] **Step 2: Manual test checklist (on simulator)**

1. Open app → go to Settings → verify "Sync to Apple Calendar" toggle exists and is ON
2. Send a chat message that creates a calendar event (e.g., "记录 Mochi 今天吃了狗粮")
3. System should prompt for calendar access → grant it
4. Open Apple Calendar app on simulator → verify:
   - A "Mochi" calendar exists with the pet's color
   - The event appears with correct title, date, category in notes
5. Edit the event in CozyPup (change title) → verify Apple Calendar updates
6. Delete the event in CozyPup → verify it disappears from Apple Calendar
7. Toggle sync OFF in settings → create another event → verify it does NOT appear in Apple Calendar
8. Test deep link: in Safari, navigate to `cozypup://calendar/event/some-id` → app should open

- [ ] **Step 3: Commit any fixes needed**
