import SwiftUI

struct EventRow: View {
    let event: CalendarEvent
    let petColor: Color
    var pet: Pet?
    var onUpdate: (String, EventCategory, String, String?, Double?) -> Void
    var onDelete: () -> Void
    var onLocationUpdate: ((String, String, Double, Double, String) -> Void)?
    var onLocationRemove: (() -> Void)?

    @State private var showEditSheet = false

    var body: some View {
        HStack(spacing: 0) {
            // Left color bar — use first pet tag color, fallback to petColor
            Capsule()
                .fill(barColor)
                .frame(width: 5, height: Tokens.size.avatarMedium)

            VStack(alignment: .leading, spacing: 2) {
                // Title + optional time
                Text(titleText)
                    .font(Tokens.fontSubheadline.weight(.medium))
                    .foregroundColor(Tokens.text)
                    .lineLimit(2)

                // Pet tags: colored dots with names
                if !event.petTags.isEmpty {
                    HStack(spacing: Tokens.spacing.xs) {
                        ForEach(event.petTags, id: \.id) { tag in
                            HStack(spacing: 3) {
                                Circle()
                                    .fill(Color(hex: tag.color_hex) ?? Tokens.accent)
                                    .frame(width: 6, height: 6)
                                Text(tag.name)
                                    .font(Tokens.fontCaption)
                                    .foregroundColor(Tokens.textSecondary)
                            }
                        }
                    }
                } else if let name = pet?.name ?? event.petName, !name.isEmpty {
                    HStack(spacing: 3) {
                        Circle()
                            .fill(petColor)
                            .frame(width: 6, height: 6)
                        Text(name)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                    }
                }
            }
            .padding(.leading, 12)

            Spacer(minLength: Tokens.spacing.sm)

            Image(systemName: "pawprint.fill")
                .font(Tokens.fontCallout)
                .foregroundColor(Tokens.accent.opacity(0.5))
        }
        .padding(.horizontal, Tokens.spacing.md)
        .padding(.vertical, 14)
        .background(Tokens.surface)
        .cornerRadius(12)
        .contextMenu {
            Button { showEditSheet = true } label: {
                Label(Lang.shared.isZh ? "编辑" : "Edit", systemImage: "pencil")
            }
            Button(role: .destructive) { Haptics.medium(); onDelete() } label: {
                Label(L.delete, systemImage: "trash")
            }
        }
        .sheet(isPresented: $showEditSheet) {
            EventEditSheet(event: event, onSave: onUpdate, onLocationUpdate: onLocationUpdate, onLocationRemove: onLocationRemove)
        }
    }

    private var titleText: String {
        if let time = event.eventTime, !time.isEmpty {
            return "\(time) · \(event.title)"
        }
        return event.title
    }

    private var barColor: Color {
        switch event.category {
        case .daily: return Tokens.accent
        case .diet: return Tokens.green
        case .medical: return Tokens.blue
        case .abnormal: return Tokens.red
        }
    }
}

#Preview("Diet") {
    EventRow(
        event: CalendarEvent(petId: "p1", eventDate: "2026-04-01", eventTime: "08:30", title: "吃了狗粮200g + 鸡胸肉", type: .log, category: .diet, rawText: "", source: .chat),
        petColor: Color(hex: "E8835C"),
        onUpdate: { _, _, _, _, _ in },
        onDelete: {}
    )
    .padding()
    .background(Tokens.bg)
}

#Preview("Medical") {
    EventRow(
        event: CalendarEvent(petId: "p1", eventDate: "2026-04-01", eventTime: "14:00", title: "狂犬疫苗接种", type: .appointment, category: .medical, rawText: "", source: .chat),
        petColor: Color(hex: "6BA3BE"),
        pet: Pet(name: "豆豆", species: .dog, breed: "金毛", birthday: nil, weight: 30, colorIndex: 0),
        onUpdate: { _, _, _, _, _ in },
        onDelete: {}
    )
    .padding()
    .background(Tokens.bg)
}
