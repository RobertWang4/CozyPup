import Foundation

enum EventType: String, Codable, CaseIterable {
    case log, appointment, reminder
}

enum EventCategory: String, Codable, CaseIterable {
    case diet, excretion, abnormal, vaccine, deworming, medical, daily

    var label: String {
        switch self {
        case .diet: return "Diet"
        case .excretion: return "Excretion"
        case .abnormal: return "Abnormal"
        case .vaccine: return "Vaccine"
        case .deworming: return "Deworming"
        case .medical: return "Medical"
        case .daily: return "Daily"
        }
    }
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
    }
}
