import Foundation

enum EventType: String, Codable, CaseIterable {
    case log, appointment, reminder
}

enum EventCategory: String, Codable, CaseIterable {
    case daily, diet, medical, abnormal

    var label: String { L.category(rawValue) }
}

enum EventSource: String, Codable {
    case chat, manual
}

struct PetTag: Codable, Equatable {
    let id: String
    let name: String
    let color_hex: String
}

struct CalendarEvent: Identifiable, Codable, Equatable {
    let id: String
    var petId: String?
    var eventDate: String
    var eventTime: String?
    var title: String
    var type: EventType
    var category: EventCategory
    var rawText: String
    var source: EventSource
    var edited: Bool
    let createdAt: String

    var photos: [String]

    // Extra fields from API
    var petName: String?
    var petColorHex: String?
    var petTags: [PetTag]

    var locationName: String?
    var locationAddress: String?
    var locationLat: Double?
    var locationLng: Double?
    var placeId: String?

    enum CodingKeys: String, CodingKey {
        case id, title, type, category, source, edited, photos
        case petId = "pet_id"
        case eventDate = "event_date"
        case eventTime = "event_time"
        case rawText = "raw_text"
        case createdAt = "created_at"
        case petName = "pet_name"
        case petColorHex = "pet_color_hex"
        case petTags = "pet_tags"
        case locationName = "location_name"
        case locationAddress = "location_address"
        case locationLat = "location_lat"
        case locationLng = "location_lng"
        case placeId = "place_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        petId = try c.decodeIfPresent(String.self, forKey: .petId)
        eventDate = try c.decode(String.self, forKey: .eventDate)
        eventTime = try c.decodeIfPresent(String.self, forKey: .eventTime)
        title = try c.decode(String.self, forKey: .title)
        type = try c.decode(EventType.self, forKey: .type)
        category = try c.decode(EventCategory.self, forKey: .category)
        rawText = try c.decode(String.self, forKey: .rawText)
        source = try c.decode(EventSource.self, forKey: .source)
        edited = try c.decode(Bool.self, forKey: .edited)
        createdAt = try c.decode(String.self, forKey: .createdAt)
        photos = try c.decodeIfPresent([String].self, forKey: .photos) ?? []
        petName = try c.decodeIfPresent(String.self, forKey: .petName)
        petColorHex = try c.decodeIfPresent(String.self, forKey: .petColorHex)
        petTags = (try? c.decode([PetTag].self, forKey: .petTags)) ?? []
        locationName = try c.decodeIfPresent(String.self, forKey: .locationName)
        locationAddress = try c.decodeIfPresent(String.self, forKey: .locationAddress)
        locationLat = try c.decodeIfPresent(Double.self, forKey: .locationLat)
        locationLng = try c.decodeIfPresent(Double.self, forKey: .locationLng)
        placeId = try c.decodeIfPresent(String.self, forKey: .placeId)
    }

    init(petId: String?, eventDate: String, eventTime: String?, title: String,
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
        self.photos = []
        self.petName = nil
        self.petColorHex = nil
        self.petTags = []
        self.locationName = nil
        self.locationAddress = nil
        self.locationLat = nil
        self.locationLng = nil
        self.placeId = nil
    }
}
