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
    static let white = Color.white                       // semantic: text on accent/dark backgrounds
    static let dimOverlay = Color.black                  // use with .opacity() for overlays
    static let placeholderBg = Color.gray.opacity(0.2)   // AsyncImage placeholder, skeleton

    // Typography system
    static let fontLargeTitle = Font.system(.largeTitle, design: .serif)
    static let fontTitle = Font.system(.title2, design: .serif)
    static let fontDisplay = Font.system(.title2, design: .serif)
    static let fontHeadline = Font.system(.headline, design: .default)
    static let fontBody = Font.system(.body, design: .default)
    static let fontCallout = Font.system(.callout, design: .default)
    static let fontSubheadline = Font.system(.subheadline, design: .default)
    static let fontCaption = Font.system(.caption, design: .default)
    static let fontCaption2 = Font.system(.caption2, design: .default)

    // Radius system
    static let radius: CGFloat = 20
    static let radiusSmall: CGFloat = 12
    static let radiusIcon: CGFloat = 14

    // Spacing system
    enum spacing {
        static let xxs: CGFloat = 2
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 16
        static let lg: CGFloat = 24
        static let xl: CGFloat = 32
    }

    // Component sizes
    enum size {
        static let buttonSmall: CGFloat = 36
        static let buttonMedium: CGFloat = 44
        static let avatarSmall: CGFloat = 32
        static let avatarMedium: CGFloat = 44
        static let avatarLarge: CGFloat = 80
        static let iconSmall: CGFloat = 28
        static let iconMedium: CGFloat = 40
    }
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
