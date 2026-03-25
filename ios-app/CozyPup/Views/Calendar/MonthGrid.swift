import SwiftUI

struct MonthGrid: View {
    let days: [CalendarDay]
    let events: [CalendarEvent]
    let pets: [Pet]
    @Binding var selectedDate: String?
    var filterPetId: String?
    var onLongPress: ((String) -> Void)?
    var onDoubleTap: ((String) -> Void)?

    // Track last tap for manual double-tap detection
    @State private var lastTapDate: String?
    @State private var lastTapTime: Date?

    private let columns = Array(repeating: GridItem(.flexible()), count: 7)

    var body: some View {
        LazyVGrid(columns: columns, spacing: Tokens.spacing.xs) {
            ForEach(days) { day in
                let dateStr = CalendarHelper.dateString(year: day.year, month: day.month, day: day.date)
                let dayEvents = filteredEvents(for: dateStr)
                let isSelected = selectedDate == dateStr
                let hasEvents = !dayEvents.isEmpty

                VStack(spacing: Tokens.spacing.xs) {
                    Text("\(day.date)")
                        .font(isSelected ? Tokens.fontBody.weight(.semibold) : Tokens.fontBody)
                        .foregroundColor(
                            isSelected ? Tokens.white : (day.isCurrentMonth ? Tokens.text : Tokens.textTertiary)
                        )
                        .frame(width: Tokens.size.buttonSmall, height: Tokens.size.buttonSmall)
                        .background(
                            Group {
                                if isSelected {
                                    Circle().fill(Tokens.accent.opacity(0.85))
                                } else if day.isToday {
                                    Circle().fill(Tokens.accent.opacity(0.15))
                                }
                            }
                        )

                    // Pet-colored event dots
                    HStack(spacing: 2) {
                        let petColors = uniquePetColors(for: dayEvents)
                        if petColors.isEmpty {
                            Circle().fill(Color.clear).frame(width: 5, height: 5)
                        } else {
                            ForEach(Array(petColors.prefix(3).enumerated()), id: \.offset) { _, color in
                                Circle().fill(color).frame(width: 5, height: 5)
                            }
                        }
                    }
                    .frame(height: 5)
                }
                .padding(.vertical, Tokens.spacing.xs)
                .contentShape(Rectangle())
                .onTapGesture {
                    let now = Date()
                    if lastTapDate == dateStr,
                       let last = lastTapTime,
                       now.timeIntervalSince(last) < 0.35 {
                        // Double tap detected
                        Haptics.light()
                        onDoubleTap?(dateStr)
                        lastTapDate = nil
                        lastTapTime = nil
                    } else {
                        // Single tap — select immediately
                        selectedDate = dateStr
                        lastTapDate = dateStr
                        lastTapTime = now
                    }
                }
                .onLongPressGesture(minimumDuration: 0.5) {
                    Haptics.medium()
                    onLongPress?(dateStr)
                }
            }
        }
        .padding(.horizontal, Tokens.spacing.xs)
    }

    private func filteredEvents(for date: String) -> [CalendarEvent] {
        events.filter { e in
            e.eventDate == date && (filterPetId == nil || e.petId == filterPetId)
        }
    }

    /// Returns unique pet colors for the given events (one dot per pet)
    private func uniquePetColors(for events: [CalendarEvent]) -> [Color] {
        var seen = Set<String>()
        var colors: [Color] = []
        for evt in events {
            if let petId = evt.petId {
                guard !seen.contains(petId) else { continue }
                seen.insert(petId)
            }

            if let petId = evt.petId,
               let pet = pets.first(where: { $0.id == petId }) {
                colors.append(pet.color)
            } else if let hex = evt.petColorHex, !hex.isEmpty {
                colors.append(Color(hex: hex))
            } else {
                colors.append(Tokens.accent)
            }
        }
        return colors
    }
}
