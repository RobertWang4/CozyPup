import SwiftUI

struct MonthGrid: View {
    let days: [CalendarDay]
    let events: [CalendarEvent]
    let pets: [Pet]
    @Binding var selectedDate: String?
    var filterPetId: String?
    var onDoubleTap: ((String) -> Void)?

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

                    // Event dot
                    Circle()
                        .fill(hasEvents ? Tokens.accent.opacity(0.6) : Color.clear)
                        .frame(width: 5, height: 5)
                }
                .padding(.vertical, Tokens.spacing.xs)
                .onTapGesture(count: 2) {
                    onDoubleTap?(dateStr)
                }
                .onTapGesture(count: 1) {
                    selectedDate = dateStr
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
}
