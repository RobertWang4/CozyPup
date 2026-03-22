import Foundation

enum EventType: String, Codable, CaseIterable {
    case log, appointment, reminder
}

enum EventCategory: String, Codable, CaseIterable {
    case diet, excretion, abnormal, vaccine, deworming, medical, daily

    var label: String { L.category(rawValue) }
}

enum EventSource: String, Codable {
    case chat, manual
}

struct CalendarEvent: Identifiable, Codable, Equatable {
    let id: String
    var petId: String
    var eventDate: String
    var eventTime: String?
    var title: String
    var type: EventType
    var category: EventCategory
    var rawText: String
    var source: EventSource
    var edited: Bool
    let createdAt: String

    // Extra fields from API (optional, not used for local creation)
    var petName: String?
    var petColorHex: String?

    enum CodingKeys: String, CodingKey {
        case id, title, type, category, source, edited
        case petId = "pet_id"
        case eventDate = "event_date"
        case eventTime = "event_time"
        case rawText = "raw_text"
        case createdAt = "created_at"
        case petName = "pet_name"
        case petColorHex = "pet_color_hex"
    }

    init(petId: String, eventDate: String, eventTime: String?, title: String,
         type: EventType, category: EventCategory, rawText: String,
         source: EventSource, edited: Bool = false) {
        self.id = UUID().uuidString
        self.petId = petId
        self.eventDate = eventDate
        self.eventTime = eventTime
        self.title = title
        self.type = type
        self.category = category
        self.rawText = rawText
        self.source = source
        self.edited = edited
        self.createdAt = ISO8601DateFormatter().string(from: Date())
        self.petName = nil
        self.petColorHex = nil
    }
}
