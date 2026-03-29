import EventKit
import CoreLocation
import UIKit

// MARK: - UIColor hex extension (private)

private extension UIColor {
    convenience init?(hex: String) {
        let cleaned = hex.trimmingCharacters(in: .alphanumerics.inverted)
        guard cleaned.count == 6 else { return nil }
        var rgb: UInt64 = 0
        guard Scanner(string: cleaned).scanHexInt64(&rgb) else { return nil }
        self.init(
            red: CGFloat((rgb >> 16) & 0xFF) / 255,
            green: CGFloat((rgb >> 8) & 0xFF) / 255,
            blue: CGFloat(rgb & 0xFF) / 255,
            alpha: 1
        )
    }
}

// MARK: - CalendarSyncService

final class CalendarSyncService {
    static let shared = CalendarSyncService()

    private let store = EKEventStore()

    // MARK: - UserDefaults keys

    private let calendarsKey = "cozypup_ek_calendars"
    private let eventsKey = "cozypup_ek_events"
    static let syncEnabledKey = "cozypup_calendar_sync_enabled"

    private init() {
        // Default to enabled for new users
        if UserDefaults.standard.object(forKey: Self.syncEnabledKey) == nil {
            UserDefaults.standard.set(true, forKey: Self.syncEnabledKey)
        }
    }

    // MARK: - Sync enabled

    var isSyncEnabled: Bool {
        UserDefaults.standard.bool(forKey: Self.syncEnabledKey)
    }

    func setSyncEnabled(_ enabled: Bool) {
        UserDefaults.standard.set(enabled, forKey: Self.syncEnabledKey)
    }

    // MARK: - Authorization

    func requestAccess() async -> Bool {
        do {
            return try await store.requestFullAccessToEvents()
        } catch {
            print("[CalendarSync] Authorization error: \(error)")
            return false
        }
    }

    var isAuthorized: Bool {
        EKEventStore.authorizationStatus(for: .event) == .fullAccess
    }

    // MARK: - Calendar mappings (petId → ekCalendarIdentifier)

    private var calendarMap: [String: String] {
        get { UserDefaults.standard.dictionary(forKey: calendarsKey) as? [String: String] ?? [:] }
        set { UserDefaults.standard.set(newValue, forKey: calendarsKey) }
    }

    // MARK: - Event mappings (eventId → ekEventIdentifier)

    private var eventMap: [String: String] {
        get { UserDefaults.standard.dictionary(forKey: eventsKey) as? [String: String] ?? [:] }
        set { UserDefaults.standard.set(newValue, forKey: eventsKey) }
    }

    // MARK: - Calendar source selection

    /// Prefer iCloud/CalDAV source, fall back to local.
    private func preferredSource() -> EKSource? {
        let sources = store.sources
        if let caldav = sources.first(where: { $0.sourceType == .calDAV }) {
            return caldav
        }
        if let local = sources.first(where: { $0.sourceType == .local }) {
            return local
        }
        return sources.first
    }

    // MARK: - Per-pet EKCalendar CRUD

    /// Get or create an EKCalendar for a pet. Returns the calendar identifier.
    @discardableResult
    func ensureCalendar(petId: String, petName: String, colorHex: String?) async -> String? {
        guard isSyncEnabled else { return nil }
        guard await requestAccess() else { return nil }

        // Check existing mapping
        if let existingId = calendarMap[petId],
           store.calendar(withIdentifier: existingId) != nil {
            return existingId
        }

        // Create new calendar
        let calendar = EKCalendar(for: .event, eventStore: store)
        calendar.title = "CozyPup – \(petName)"
        if let hex = colorHex, let color = UIColor(hex: hex) {
            calendar.cgColor = color.cgColor
        }
        guard let source = preferredSource() else {
            print("[CalendarSync] No calendar source available")
            return nil
        }
        calendar.source = source

        do {
            try store.saveCalendar(calendar, commit: true)
            var map = calendarMap
            map[petId] = calendar.calendarIdentifier
            calendarMap = map
            return calendar.calendarIdentifier
        } catch {
            print("[CalendarSync] Failed to create calendar: \(error)")
            return nil
        }
    }

    /// Rename a pet's calendar.
    func renameCalendar(petId: String, newName: String) {
        guard isSyncEnabled, isAuthorized else { return }
        guard let calId = calendarMap[petId],
              let calendar = store.calendar(withIdentifier: calId) else { return }
        calendar.title = "CozyPup – \(newName)"
        try? store.saveCalendar(calendar, commit: true)
    }

    /// Delete a pet's calendar and all its events.
    func deleteCalendar(petId: String) {
        guard isAuthorized else { return }
        guard let calId = calendarMap[petId],
              let calendar = store.calendar(withIdentifier: calId) else { return }

        // Remove event mappings for this calendar
        let predicate = store.predicateForEvents(
            withStart: Date.distantPast, end: Date.distantFuture, calendars: [calendar]
        )
        let ekEvents = store.events(matching: predicate)
        var evMap = eventMap
        for ekEvent in ekEvents {
            // Remove by value (ekEventIdentifier)
            evMap = evMap.filter { $0.value != ekEvent.eventIdentifier }
        }
        eventMap = evMap

        try? store.removeCalendar(calendar, commit: true)
        var map = calendarMap
        map.removeValue(forKey: petId)
        calendarMap = map
    }

    // MARK: - Event CRUD

    /// Sync a CalendarEvent to EventKit. Creates or updates the EKEvent.
    func syncEvent(_ event: CalendarEvent, allPetNames: [String] = []) async {
        guard isSyncEnabled else { return }
        guard let petId = event.petId else { return }
        guard await requestAccess() else { return }

        // Ensure we have a calendar for this pet
        guard let calId = await ensureCalendar(
            petId: petId,
            petName: event.petName ?? "Pet",
            colorHex: event.petColorHex
        ) else { return }

        guard let calendar = store.calendar(withIdentifier: calId) else { return }

        // Find or create EKEvent
        let ekEvent: EKEvent
        if let existingId = eventMap[event.id],
           let existing = store.event(withIdentifier: existingId) {
            ekEvent = existing
        } else {
            ekEvent = EKEvent(eventStore: store)
        }

        // Map fields
        configureEKEvent(ekEvent, from: event, calendar: calendar, allPetNames: allPetNames)

        do {
            try store.save(ekEvent, span: .thisEvent, commit: true)
            var map = eventMap
            map[event.id] = ekEvent.eventIdentifier
            eventMap = map
        } catch {
            print("[CalendarSync] Failed to save event: \(error)")
        }
    }

    /// Delete a CalendarEvent from EventKit.
    func deleteEvent(eventId: String) {
        guard isAuthorized else { return }
        guard let ekId = eventMap[eventId],
              let ekEvent = store.event(withIdentifier: ekId) else { return }

        do {
            try store.remove(ekEvent, span: .thisEvent, commit: true)
        } catch {
            print("[CalendarSync] Failed to delete event: \(error)")
        }

        var map = eventMap
        map.removeValue(forKey: eventId)
        eventMap = map
    }

    // MARK: - Bulk sync

    /// Sync all events for a pet. Removes stale EKEvents not in the provided list.
    func bulkSync(events: [CalendarEvent], petId: String, petName: String, colorHex: String?) async {
        guard isSyncEnabled else { return }
        guard await requestAccess() else { return }

        guard let calId = await ensureCalendar(petId: petId, petName: petName, colorHex: colorHex),
              let calendar = store.calendar(withIdentifier: calId) else { return }

        let eventIds = Set(events.map(\.id))

        // Remove stale events
        let predicate = store.predicateForEvents(
            withStart: Date.distantPast, end: Date.distantFuture, calendars: [calendar]
        )
        let existingEKEvents = store.events(matching: predicate)
        var evMap = eventMap
        for ekEvent in existingEKEvents {
            // Find the CozyPup event ID mapped to this EKEvent
            if let entry = evMap.first(where: { $0.value == ekEvent.eventIdentifier }),
               !eventIds.contains(entry.key) {
                try? store.remove(ekEvent, span: .thisEvent, commit: false)
                evMap.removeValue(forKey: entry.key)
            }
        }
        eventMap = evMap

        // Sync all current events
        for event in events {
            let ekEvent: EKEvent
            if let existingId = eventMap[event.id],
               let existing = store.event(withIdentifier: existingId) {
                ekEvent = existing
            } else {
                ekEvent = EKEvent(eventStore: store)
            }
            configureEKEvent(ekEvent, from: event, calendar: calendar, allPetNames: [])

            do {
                try store.save(ekEvent, span: .thisEvent, commit: false)
                var map = eventMap
                map[event.id] = ekEvent.eventIdentifier
                eventMap = map
            } catch {
                print("[CalendarSync] Failed to save event \(event.id): \(error)")
            }
        }

        // Commit all changes at once
        try? store.commit()
    }

    // MARK: - EKEvent configuration

    private func configureEKEvent(
        _ ekEvent: EKEvent,
        from event: CalendarEvent,
        calendar: EKCalendar,
        allPetNames: [String]
    ) {
        ekEvent.calendar = calendar

        // Title — append other pet names for multi-pet events
        var title = event.title
        let otherNames = allPetNames.filter { $0 != event.petName }
        if !otherNames.isEmpty {
            title += " (\(otherNames.joined(separator: ", ")))"
        }
        ekEvent.title = title

        // Start / end dates
        let (start, isAllDay) = parseStartDate(date: event.eventDate, time: event.eventTime)
        ekEvent.startDate = start
        ekEvent.isAllDay = isAllDay
        if isAllDay {
            ekEvent.endDate = start
        } else {
            ekEvent.endDate = start.addingTimeInterval(3600) // 1 hour default
        }

        // Notes — category label + raw text
        var notes = "[\(event.category.rawValue.capitalized)]"
        if !event.rawText.isEmpty {
            notes += "\n\(event.rawText)"
        }
        ekEvent.notes = notes

        // Location
        if let locName = event.locationName, !locName.isEmpty {
            let location = EKStructuredLocation(title: locName)
            if let lat = event.locationLat, let lng = event.locationLng {
                location.geoLocation = CLLocation(latitude: lat, longitude: lng)
            }
            ekEvent.structuredLocation = location
        }

        // Deep link URL
        ekEvent.url = URL(string: "cozypup://calendar/event/\(event.id)")

        // Alarm for reminder/appointment type events
        if event.type == .reminder || event.type == .appointment {
            // Remove existing alarms to avoid duplicates
            ekEvent.alarms?.forEach { ekEvent.removeAlarm($0) }
            ekEvent.addAlarm(EKAlarm(relativeOffset: -3600)) // 1 hour before
        }
    }

    // MARK: - Date parsing

    private func parseStartDate(date: String, time: String?) -> (Date, Bool) {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")

        if let time = time {
            formatter.dateFormat = "yyyy-MM-dd HH:mm"
            if let d = formatter.date(from: "\(date) \(time)") {
                return (d, false)
            }
        }

        formatter.dateFormat = "yyyy-MM-dd"
        let d = formatter.date(from: date) ?? Date()
        return (d, true)
    }
}
