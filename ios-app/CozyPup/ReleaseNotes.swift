import Foundation

struct ReleaseNote: Identifiable {
    let id = UUID()
    let version: String
    let date: String
    let highlights: [String]
}

enum ReleaseNotes {
    static let all: [ReleaseNote] = [
        ReleaseNote(
            version: "1.0",
            date: "April 2026",
            highlights: [
                "First public release",
                "AI pet health assistant with chat",
                "Calendar and reminders",
                "Duo Plan for sharing with a partner",
            ]
        ),
    ]
}
