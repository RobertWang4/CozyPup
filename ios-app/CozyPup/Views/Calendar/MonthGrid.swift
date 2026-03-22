import SwiftUI

struct MonthGrid: View {
    let days: [CalendarDay]
    let events: [CalendarEvent]
    let pets: [Pet]
    @Binding var selectedDate: String?
    var filterPetId: String?

    private let columns = Array(repeating: GridItem(.flexible()), count: 7)

    var body: some View {
        LazyVGrid(columns: columns, spacing: 4) {
            ForEach(days) { day in
                let dateStr = CalendarHelper.dateString(year: day.year, month: day.month, day: day.date)
                let dayEvents = filteredEvents(for: dateStr)
                let isSelected = selectedDate == dateStr
                let hasEvents = !dayEvents.isEmpty

                Button {
                    selectedDate = dateStr
                } label: {
                    VStack(spacing: 4) {
                        Text("\(day.date)")
                            .font(.system(size: 15, weight: isSelected ? .semibold : .regular))
                            .foregroundColor(
                                isSelected ? .white : (day.isCurrentMonth ? Tokens.text : Tokens.textTertiary)
                            )
                            .frame(width: 36, height: 36)
                            .background(
                                Group {
                                    if isSelected {
                                        Circle().fill(Tokens.accent.opacity(0.85))
                                    } else if day.isToday {
                                        Circle().fill(Tokens.accent.opacity(0.15))
                                    }
                                }
                            )

                        // Event dot
                        Circle()
                            .fill(hasEvents ? Tokens.accent.opacity(0.6) : Color.clear)
                            .frame(width: 5, height: 5)
                    }
                    .padding(.vertical, 4)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 4)
    }

    private func filteredEvents(for date: String) -> [CalendarEvent] {
        events.filter { e in
            e.eventDate == date && (filterPetId == nil || e.petId == filterPetId)
        }
    }
}
