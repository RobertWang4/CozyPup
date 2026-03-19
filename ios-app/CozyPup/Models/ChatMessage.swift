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

enum CardData: Codable, Equatable {
    case record(RecordCardData)
    case map(MapCardData)
    case email(EmailCardData)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let r = try? container.decode(RecordCardData.self), r.type == "record" {
            self = .record(r)
        } else if let m = try? container.decode(MapCardData.self), m.type == "map" {
            self = .map(m)
        } else if let e = try? container.decode(EmailCardData.self), e.type == "email" {
            self = .email(e)
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
