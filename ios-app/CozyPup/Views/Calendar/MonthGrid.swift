import SwiftUI

struct MonthGrid: View {
    let days: [CalendarDay]
    let events: [CalendarEvent]
    let pets: [Pet]
    @Binding var selectedDate: String?
    var filterPetId: String?

    private let columns = Array(repeating: GridItem(.flexible()), count: 7)

    var body: some View {
        VStack(spacing: 0) {
            LazyVGrid(columns: columns) {
                ForEach(CalendarHelper.weekdays, id: \.self) { day in
                    Text(day)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(Tokens.textTertiary)
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 4)

            LazyVGrid(columns: columns, spacing: 2) {
                ForEach(days) { day in
                    let dateStr = CalendarHelper.dateString(year: day.year, month: day.month, day: day.date)
                    let dayEvents = filteredEvents(for: dateStr)
                    let isSelected = selectedDate == dateStr

                    Button {
                        selectedDate = dateStr
                    } label: {
                        VStack(spacing: 3) {
                            Text("\(day.date)")
                                .font(.system(size: 14, weight: day.isToday ? .bold : .medium))
                                .foregroundColor(
                                    day.isToday ? .white :
                                    day.isCurrentMonth ? Tokens.text : Tokens.textTertiary
                                )
                                .frame(width: 30, height: 30)
                                .background(day.isToday ? Tokens.accent : Color.clear)
                                .clipShape(Circle())

                            HStack(spacing: 3) {
                                ForEach(uniquePetColors(dayEvents).prefix(2), id: \.self) { color in
                                    Circle().fill(color).frame(width: 5, height: 5)
                                }
                            }
                            .frame(height: 5)
                        }
                        .padding(.vertical, 6)
                        .background(isSelected ? Tokens.accentSoft : Color.clear)
                        .cornerRadius(10)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func filteredEvents(for date: String) -> [CalendarEvent] {
        events.filter { e in
            e.eventDate == date && (filterPetId == nil || e.petId == filterPetId)
        }
    }

    private func uniquePetColors(_ evts: [CalendarEvent]) -> [Color] {
        var seen = Set<String>()
        var colors: [Color] = []
        for e in evts {
            if seen.insert(e.petId).inserted, let pet = pets.first(where: { $0.id == e.petId }) {
                colors.append(pet.color)
            }
        }
        return colors
    }
}
