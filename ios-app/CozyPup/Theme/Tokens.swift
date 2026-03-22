import SwiftUI

enum Tokens {
    static let bg = Color(hex: "F5EBE0")           // was FFF8F0 — warm linen, 5% darker
    static let surface = Color(hex: "FBF6F1")       // was pure white — warm off-white
    static let surface2 = Color(hex: "F5ECE3")       // was FDF6EF — warmer secondary
    static let text = Color(hex: "3D2C1E")
    static let textSecondary = Color(hex: "8B7355")
    static let textTertiary = Color(hex: "B8A48E")
    static let accent = Color(hex: "E8835C")
    static let accentSoft = Color(hex: "F0DDD3")     // was FDEEE8 — muted peach
    static let green = Color(hex: "7BAE7F")
    static let blue = Color(hex: "6BA3BE")
    static let red = Color(hex: "D35F5F")
    static let redSoft = Color(hex: "F5E2DC")         // was FFF0EC — muted
    static let orange = Color(hex: "E8A33C")
    static let purple = Color(hex: "9B7ED8")
    static let border = Color(hex: "E6D5C5")          // was F0E4D6 — more visible
    static let divider = Color(hex: "E6D5C5")
    static let inputPlaceholder = Color(hex: "C4AE96")
    static let typingDot = Color(hex: "D4C4B0")
    static let drawerOverlay = Color(hex: "3D2C1E").opacity(0.3)
    static let switchBg = Color(hex: "D8CABB")         // was E0D5C8 — slightly darker
    static let switchActive = Color(hex: "7BAE7F")
    static let waveform = Color(hex: "E8835C")
    static let bubbleUser = Color(hex: "E8835C")
    static let bubbleAi = Color(hex: "FBF6F1")         // was pure white — match surface
    static let fontBody = Font.system(.body, design: .default)
    static let fontDisplay = Font.system(.title2, design: .serif)
    static let fontCaption = Font.system(.caption, design: .default)
    static let radius: CGFloat = 20
    static let radiusSmall: CGFloat = 12
    static let radiusIcon: CGFloat = 14
}

extension Color {
    init(hex: String) {
        let scanner = Scanner(string: hex.trimmingCharacters(in: .alphanumerics.inverted))
        var rgb: UInt64 = 0
        scanner.scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}
