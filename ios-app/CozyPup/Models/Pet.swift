import SwiftUI

let petColors: [Color] = [
    Color(hex: "E8835C"), Color(hex: "6BA3BE"), Color(hex: "7BAE7F"),
    Color(hex: "9B7ED8"), Color(hex: "E8A33C"),
]

let petColorHexes = ["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]

enum Species: String, Codable, CaseIterable {
    case dog, cat, other
}

struct Pet: Identifiable, Codable, Equatable {
    let id: String
    var name: String
    var species: Species
    var breed: String
    var birthday: String?
    var weight: Double?
    var avatarUrl: String
    var colorHex: String
    let createdAt: String

    var color: Color { Color(hex: colorHex) }

    init(name: String, species: Species, breed: String, birthday: String?, weight: Double?, colorIndex: Int) {
        self.id = UUID().uuidString
        self.name = name
        self.species = species
        self.breed = breed
        self.birthday = birthday
        self.weight = weight
        self.avatarUrl = ""
        self.colorHex = petColorHexes[colorIndex % petColorHexes.count]
        self.createdAt = ISO8601DateFormatter().string(from: Date())
    }
}
