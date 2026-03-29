import Foundation

@MainActor
class CalendarStore: ObservableObject {
    @Published var events: [CalendarEvent] = []

    private let key = "cozypup_calendar"

    init() { loadLocal() }

    // MARK: - Local cache

    private func loadLocal() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let saved = try? JSONDecoder().decode([CalendarEvent].self, from: data) else { return }
        events = saved
    }

    private func saveLocal() {
        if let data = try? JSONEncoder().encode(events) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    // MARK: - API

    func fetchMonth(year: Int, month: Int) async {
        let startDate = String(format: "%04d-%02d-01", year, month)
        // Calculate last day of month
        var comps = DateComponents(year: year, month: month + 1, day: 0)
        let lastDay = Calendar.current.date(from: comps).map { Calendar.current.component(.day, from: $0) } ?? 28
        let endDate = String(format: "%04d-%02d-%02d", year, month, lastDay)

        do {
            let fetched: [CalendarEvent] = try await APIClient.shared.request(
                "GET", "/calendar",
                query: ["start_date": startDate, "end_date": endDate]
            )
            // Merge: replace events in this month range, keep others
            let prefix = String(format: "%04d-%02d", year, month)
            events.removeAll { $0.eventDate.hasPrefix(prefix) }
            events.append(contentsOf: fetched)
            saveLocal()
        } catch {
            print("CalendarStore.fetchMonth failed: \(error)")
        }
    }

    func add(_ event: CalendarEvent) {
        // Add locally immediately
        events.append(event)
        saveLocal()

        // Sync to system calendar
        Task { await CalendarSyncService.shared.syncEvent(event) }

        // Sync to API
        Task {
            struct CreateBody: Encodable {
                let pet_id: String
                let event_date: String
                let event_time: String?
                let title: String
                let type: String
                let category: String
                let raw_text: String
                let source: String
            }

            guard let petId = event.petId else {
                print("CalendarStore.add skipped API sync: missing petId for event \(event.id)")
                return
            }

            let body = CreateBody(
                pet_id: petId,
                event_date: event.eventDate,
                event_time: event.eventTime,
                title: event.title,
                type: event.type.rawValue,
                category: event.category.rawValue,
                raw_text: event.rawText,
                source: event.source.rawValue
            )

            do {
                let created: CalendarEvent = try await APIClient.shared.request("POST", "/calendar", body: body)
                // Replace local version with server version (has real ID)
                if let idx = events.firstIndex(where: { $0.id == event.id }) {
                    events[idx] = created
                    saveLocal()
                }
            } catch {
                print("CalendarStore.add API sync failed: \(error)")
            }
        }
    }

    func update(_ id: String, title: String? = nil, category: EventCategory? = nil,
                eventDate: String? = nil, eventTime: String? = nil) {
        guard let idx = events.firstIndex(where: { $0.id == id }) else { return }
        if let t = title { events[idx].title = t }
        if let c = category { events[idx].category = c }
        if let d = eventDate { events[idx].eventDate = d }
        if let t = eventTime { events[idx].eventTime = t }
        events[idx].edited = true
        saveLocal()

        // Sync to system calendar
        let updatedEvent = events[idx]
        Task { await CalendarSyncService.shared.syncEvent(updatedEvent) }

        // Sync to API
        Task {
            struct UpdateBody: Encodable {
                let title: String?
                let category: String?
                let event_date: String?
                let event_time: String?
            }

            let body = UpdateBody(
                title: title,
                category: category?.rawValue,
                event_date: eventDate,
                event_time: eventTime
            )

            do {
                let _: CalendarEvent = try await APIClient.shared.request("PUT", "/calendar/\(id)", body: body)
            } catch {
                print("CalendarStore.update API sync failed: \(error)")
            }
        }
    }

    func remove(_ id: String) {
        events.removeAll { $0.id == id }
        saveLocal()

        // Remove from system calendar
        CalendarSyncService.shared.deleteEvent(eventId: id)

        Task {
            do {
                try await APIClient.shared.requestNoContent("DELETE", "/calendar/\(id)")
            } catch {
                print("CalendarStore.remove API sync failed: \(error)")
            }
        }
    }

    func removeMultiple(_ ids: Set<String>) {
        events.removeAll { ids.contains($0.id) }
        saveLocal()

        // Remove from system calendar
        for id in ids { CalendarSyncService.shared.deleteEvent(eventId: id) }

        Task {
            for id in ids {
                do {
                    try await APIClient.shared.requestNoContent("DELETE", "/calendar/\(id)")
                } catch {
                    print("CalendarStore.removeMultiple API sync failed for \(id): \(error)")
                }
            }
        }
    }

    // MARK: - Photo upload

    /// Upload photo and return the new photo URL, or nil on failure.
    func uploadEventPhoto(eventId: String, imageData: Data) async -> String? {
        do {
            let data = try await APIClient.shared.uploadMultipart(
                "/calendar/\(eventId)/photos",
                fileData: imageData,
                fileName: "photo.jpg",
                mimeType: "image/jpeg"
            )
            if let updated = try? JSONDecoder().decode(CalendarEvent.self, from: data) {
                if let idx = events.firstIndex(where: { $0.id == eventId }) {
                    events[idx].photos = updated.photos
                    saveLocal()
                }
                // Return the newly added photo URL
                return updated.photos.last
            }
        } catch {
            print("CalendarStore.uploadEventPhoto failed: \(error)")
        }
        return nil
    }

    func updateLocation(eventId: String, name: String, address: String, lat: Double, lng: Double, placeId: String) async {
        // Update local
        if let idx = events.firstIndex(where: { $0.id == eventId }) {
            events[idx].locationName = name
            events[idx].locationAddress = address
            events[idx].locationLat = lat
            events[idx].locationLng = lng
            events[idx].placeId = placeId
            saveLocal()

            // Sync location to system calendar
            Task { await CalendarSyncService.shared.syncEvent(events[idx]) }
        }

        // Sync to API
        struct LocationBody: Encodable {
            let location_name: String
            let location_address: String
            let location_lat: Double
            let location_lng: Double
            let place_id: String
        }
        do {
            let _: CalendarEvent = try await APIClient.shared.request(
                "PUT", "/calendar/\(eventId)/location",
                body: LocationBody(
                    location_name: name,
                    location_address: address,
                    location_lat: lat,
                    location_lng: lng,
                    place_id: placeId
                )
            )
        } catch {
            print("Failed to update location: \(error)")
        }
    }

    func removeLocation(eventId: String) async {
        if let idx = events.firstIndex(where: { $0.id == eventId }) {
            events[idx].locationName = nil
            events[idx].locationAddress = nil
            events[idx].locationLat = nil
            events[idx].locationLng = nil
            events[idx].placeId = nil
            saveLocal()

            // Sync location removal to system calendar
            Task { await CalendarSyncService.shared.syncEvent(events[idx]) }
        }

        do {
            let _: CalendarEvent = try await APIClient.shared.request("DELETE", "/calendar/\(eventId)/location")
        } catch {
            print("Failed to remove location: \(error)")
        }
    }

    func deleteEventPhoto(eventId: String, photoUrl: String) async {
        do {
            let updated: CalendarEvent = try await APIClient.shared.request(
                "DELETE", "/calendar/\(eventId)/photos",
                query: ["photo_url": photoUrl]
            )
            if let idx = events.firstIndex(where: { $0.id == eventId }) {
                events[idx].photos = updated.photos
                saveLocal()
            }
        } catch {
            print("CalendarStore.deleteEventPhoto failed: \(error)")
        }
    }

    // MARK: - Local filtering (unchanged)

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
        // No longer needed — data comes from API
    }
}
