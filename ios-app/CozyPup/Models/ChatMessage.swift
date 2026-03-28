import Foundation

enum MessageRole: String, Codable {
    case user, assistant
}

struct RecordCardData: Codable, Equatable {
    let type: String
    let pet_name: String
    let date: String
    let category: String
    let old_date: String?  // present when event was moved to a different date
}

struct MapItem: Codable, Equatable {
    let name: String
    let description: String
    let distance: String
}

struct MapCardData: Codable, Equatable {
    let type: String
    let title: String
    let items: [MapItem]
}

struct EmailCardData: Codable, Equatable {
    let type: String
    let subject: String
    let body: String
}

struct PetCreatedCardData: Codable, Equatable {
    let type: String
    let pet_name: String
    let species: String
    let breed: String?
}

struct ReminderCardData: Codable, Equatable {
    let type: String
    let pet_name: String
    let title: String
    let trigger_at: String
    let reminder_type: String
}

struct SetLanguageCardData: Codable, Equatable {
    let type: String
    let language: String
}

struct PetUpdatedCardData: Codable, Equatable {
    let type: String
    let pet_name: String
    let pet_id: String?
    let saved_keys: [String]?
}

struct GenericActionCardData: Codable, Equatable {
    let type: String
    let pet_name: String?
    let pet_id: String?
    let title: String?
    let saved_keys: [String]?
}

struct ConfirmActionCardData: Codable, Equatable {
    let type: String
    let action_id: String
    let message: String
    var status: ConfirmStatus = .pending

    enum ConfirmStatus: String, Codable, Equatable {
        case pending, confirmed, cancelled
    }

    enum CodingKeys: String, CodingKey {
        case type, action_id, message, status
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        action_id = try container.decode(String.self, forKey: .action_id)
        message = try container.decode(String.self, forKey: .message)
        status = (try? container.decode(ConfirmStatus.self, forKey: .status)) ?? .pending
    }
}

struct LocationOption: Codable, Equatable {
    let name: String
    let address: String
    let distance_m: Int?
    let place_id: String
    let lat: Double
    let lng: Double
}

struct LocationPickerCardData: Codable, Equatable {
    let type: String  // "location_picker"
    let event_id: String
    let options: [LocationOption]
}

enum CardData: Codable, Equatable {
    case record(RecordCardData)
    case map(MapCardData)
    case email(EmailCardData)
    case petCreated(PetCreatedCardData)
    case petUpdated(PetUpdatedCardData)
    case reminder(ReminderCardData)
    case confirmAction(ConfirmActionCardData)
    case setLanguage(SetLanguageCardData)
    case genericAction(GenericActionCardData)
    case locationPicker(LocationPickerCardData)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let d = try? container.decode(RecordCardData.self), d.type == "record" {
            self = .record(d)
        } else if let d = try? container.decode(MapCardData.self), d.type == "map" {
            self = .map(d)
        } else if let d = try? container.decode(EmailCardData.self), d.type == "email" {
            self = .email(d)
        } else if let d = try? container.decode(PetCreatedCardData.self), d.type == "pet_created" {
            self = .petCreated(d)
        } else if let d = try? container.decode(PetUpdatedCardData.self), d.type == "pet_updated" {
            self = .petUpdated(d)
        } else if let d = try? container.decode(ReminderCardData.self), d.type == "reminder" {
            self = .reminder(d)
        } else if let d = try? container.decode(ConfirmActionCardData.self), d.type == "confirm_action" {
            self = .confirmAction(d)
        } else if let d = try? container.decode(SetLanguageCardData.self), d.type == "set_language" {
            self = .setLanguage(d)
        } else if let d = try? container.decode(LocationPickerCardData.self), d.type == "location_picker" {
            self = .locationPicker(d)
        } else if let d = try? container.decode(GenericActionCardData.self) {
            // Catch-all for pet_deleted, event_deleted, reminder_deleted, profile_summarized, etc.
            self = .genericAction(d)
        } else {
            // Never crash on unknown card types — just ignore
            self = .genericAction(GenericActionCardData(type: "unknown", pet_name: nil, pet_id: nil, title: nil, saved_keys: nil))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .record(let d): try container.encode(d)
        case .map(let d): try container.encode(d)
        case .email(let d): try container.encode(d)
        case .petCreated(let d): try container.encode(d)
        case .petUpdated(let d): try container.encode(d)
        case .reminder(let d): try container.encode(d)
        case .confirmAction(let d): try container.encode(d)
        case .setLanguage(let d): try container.encode(d)
        case .genericAction(let d): try container.encode(d)
        case .locationPicker(let d): try container.encode(d)
        }
    }
}

struct ChatMessage: Identifiable, Codable, Equatable {
    let id: String
    let role: MessageRole
    var content: String
    var cards: [CardData]
    var imageData: [Data]?  // attached photos (JPEG data, not persisted to UserDefaults)

    enum CodingKeys: String, CodingKey {
        case id, role, content, cards
        // imageData intentionally excluded — too large for UserDefaults
    }

    init(role: MessageRole, content: String = "", cards: [CardData] = [], imageData: [Data]? = nil) {
        self.id = UUID().uuidString
        self.role = role
        self.content = content
        self.cards = cards
        self.imageData = imageData
    }
}

struct EmergencyData: Equatable {
    let message: String
    let action: String
}
