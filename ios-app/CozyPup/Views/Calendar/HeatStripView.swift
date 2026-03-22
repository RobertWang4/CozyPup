import SwiftUI

struct HeatStripView: View {
    let events: [CalendarEvent]
    let pets: [Pet]
    @GestureState private var magnification: CGFloat = 1.0

    var body: some View {
        VStack(spacing: Tokens.spacing.xs) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    // Background bar
                    RoundedRectangle(cornerRadius: Tokens.spacing.sm)
                        .fill(Tokens.accentSoft)

                    // Event blocks positioned by time
                    ForEach(events, id: \.id) { evt in
                        if let pct = timeToPercent(evt.eventTime) {
                            let pet = pets.first { $0.id == evt.petId }
                            RoundedRectangle(cornerRadius: Tokens.spacing.xs)
                                .fill(petColor(for: evt, pet: pet))
                                .frame(width: max(geo.size.width * 0.035, 6))
                                .offset(x: geo.size.width * pct)
                                .padding(.vertical, 5)
                        }
                    }
                }
            }
            .frame(height: Tokens.size.avatarSmall - 4) // 28pt
            .scaleEffect(x: magnification, anchor: .center)
            .gesture(
                MagnificationGesture()
                    .updating($magnification) { value, state, _ in
                        state = min(max(value, 1.0), 3.0)
                    }
            )

            // Time labels
            HStack {
                ForEach(["6am", "9", "12pm", "3", "6pm", "9pm"], id: \.self) { t in
                    Text(t)
                        .font(Tokens.fontCaption2)
                        .foregroundColor(Tokens.textTertiary)
                    if t != "9pm" { Spacer() }
                }
            }
        }
        .padding(.horizontal, Tokens.spacing.md)
    }

    /// Convert "HH:mm" time string to a 0…1 percentage within the 6am–9pm range.
    private func timeToPercent(_ time: String?) -> CGFloat? {
        guard let time = time else { return nil }
        let parts = time.split(separator: ":")
        guard parts.count >= 2,
              let hour = Int(parts[0]),
              let minute = Int(parts[1]) else { return nil }
        let totalMin = CGFloat(hour * 60 + minute)
        let start: CGFloat = 360   // 6:00am
        let end: CGFloat = 1260    // 9:00pm
        let pct = (totalMin - start) / (end - start)
        return Swift.max(0, Swift.min(pct, 1.0))
    }

    /// Resolve pet color: prefer the event's embedded petColorHex, then the Pet model, then accent fallback.
    private func petColor(for event: CalendarEvent, pet: Pet?) -> Color {
        if let hex = event.petColorHex, !hex.isEmpty {
            return Color(hex: hex)
        }
        if let pet = pet {
            return pet.color
        }
        return Tokens.accent
    }
}
