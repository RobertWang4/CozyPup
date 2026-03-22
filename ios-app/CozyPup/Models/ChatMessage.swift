import Foundation

enum MessageRole: String, Codable {
    case user, assistant
}

struct RecordCardData: Codable, Equatable {
    let type: String
    let pet_name: String
    let date: String
    let category: String
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

enum CardData: Codable, Equatable {
    case record(RecordCardData)
    case map(MapCardData)
    case email(EmailCardData)
    case petCreated(PetCreatedCardData)
    case reminder(ReminderCardData)

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
        } else if let d = try? container.decode(ReminderCardData.self), d.type == "reminder" {
            self = .reminder(d)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unknown card type")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .record(let d): try container.encode(d)
        case .map(let d): try container.encode(d)
        case .email(let d): try container.encode(d)
        case .petCreated(let d): try container.encode(d)
        case .reminder(let d): try container.encode(d)
        }
    }
}

struct ChatMessage: Identifiable, Codable, Equatable {
    let id: String
    let role: MessageRole
    var content: String
    var cards: [CardData]

    init(role: MessageRole, content: String = "", cards: [CardData] = []) {
        self.id = UUID().uuidString
        self.role = role
        self.content = content
        self.cards = cards
    }
}

struct EmergencyData: Equatable {
    let message: String
    let action: String
}
