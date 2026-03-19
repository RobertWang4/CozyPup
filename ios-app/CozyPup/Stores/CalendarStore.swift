import Foundation

@MainActor
class CalendarStore: ObservableObject {
    @Published var events: [CalendarEvent] = []

    private let key = "cozypup_calendar"

    init() { load() }

    func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let saved = try? JSONDecoder().decode([CalendarEvent].self, from: data) else { return }
        events = saved
    }

    private func save() {
        if let data = try? JSONEncoder().encode(events) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    func add(_ event: CalendarEvent) {
        events.append(event)
        save()
    }

    func update(_ id: String, title: String? = nil, category: EventCategory? = nil,
                eventDate: String? = nil, eventTime: String? = nil) {
        guard let idx = events.firstIndex(where: { $0.id == id }) else { return }
        if let t = title { events[idx].title = t }
        if let c = category { events[idx].category = c }
        if let d = eventDate { events[idx].eventDate = d }
        if let t = eventTime { events[idx].eventTime = t }
        events[idx].edited = true
        save()
    }

    func remove(_ id: String) {
        events.removeAll { $0.id == id }
        save()
    }

    func eventsForDate(_ date: String) -> [CalendarEvent] {
        events.filter { $0.eventDate == date }
    }

    func eventsForMonth(year: Int, month: Int) -> [CalendarEvent] {
        let prefix = String(format: "%04d-%02d", year, month + 1)
        return events.filter { $0.eventDate.hasPrefix(prefix) }
    }

    func eventsForPet(_ petId: String) -> [CalendarEvent] {
        events.filter { $0.petId == petId }
    }

    func seedDemoData(pets: [Pet]) {
        guard events.isEmpty, let pet = pets.first else { return }
        let cal = Calendar.current
        let now = Date()
        let year = cal.component(.year, from: now)
        let month = cal.component(.month, from: now)
        let day = cal.component(.day, from: now)
        func dateStr(_ d: Int) -> String {
            String(format: "%04d-%02d-%02d", year, month, d)
        }

        let demos: [(String, String?, String, EventType, EventCategory)] = [
            (dateStr(3), "08:30", "Morning walk & breakfast", .log, .daily),
            (dateStr(7), "10:00", "Annual vaccine booster", .appointment, .vaccine),
            (dateStr(12), nil, "Ate well, normal stool", .log, .diet),
            (dateStr(18), "14:00", "Deworming reminder", .reminder, .deworming),
            (dateStr(day), "09:00", "Morning checkup", .log, .daily),
        ]

        for (date, time, title, type, cat) in demos {
            let evt = CalendarEvent(petId: pet.id, eventDate: date, eventTime: time,
                                    title: title, type: type, category: cat,
                                    rawText: title, source: .chat)
            events.append(evt)
        }
        save()
    }
}
