import SwiftUI

struct CalendarDrawer: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @Environment(\.dismiss) var dismiss

    @State private var year: Int
    @State private var month: Int
    @State private var selectedDate: String?
    @State private var filterPetId: String?

    init() {
        let cal = Calendar.current
        let now = Date()
        _year = State(initialValue: cal.component(.year, from: now))
        _month = State(initialValue: cal.component(.month, from: now) - 1)
    }

    private var monthEvents: [CalendarEvent] {
        calendarStore.eventsForMonth(year: year, month: month)
    }

    private var selectedEvents: [CalendarEvent] {
        guard let date = selectedDate else { return [] }
        let dayEvts = calendarStore.eventsForDate(date)
        if let pid = filterPetId {
            return dayEvts.filter { $0.petId == pid }
        }
        return dayEvts
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 0) {
                    filterBar
                    monthNav

                    MonthGrid(
                        days: CalendarHelper.getCalendarDays(year: year, month: month),
                        events: monthEvents,
                        pets: petStore.pets,
                        selectedDate: $selectedDate,
                        filterPetId: filterPetId
                    )

                    if let _ = selectedDate {
                        eventsList
                    }
                }
            }
            .background(Tokens.bg)
            .navigationTitle("Calendar")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Tokens.textSecondary)
                            .frame(width: 32, height: 32)
                            .background(Tokens.surface)
                            .cornerRadius(10)
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Tokens.border))
                    }
                }
            }
        }
    }

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Button {
                    filterPetId = nil
                } label: {
                    Text("All")
                        .font(.system(size: 12, weight: .medium))
                        .padding(.horizontal, 14).padding(.vertical, 6)
                        .background(filterPetId == nil ? Tokens.accent : Color.clear)
                        .foregroundColor(filterPetId == nil ? .white : Tokens.textSecondary)
                        .cornerRadius(20)
                        .overlay(RoundedRectangle(cornerRadius: 20)
                            .stroke(filterPetId == nil ? Color.clear : Tokens.border))
                }

                ForEach(petStore.pets) { pet in
                    Button {
                        filterPetId = pet.id
                    } label: {
                        HStack(spacing: 6) {
                            Circle().fill(pet.color).frame(width: 8, height: 8)
                            Text(pet.name)
                        }
                        .font(.system(size: 12, weight: .medium))
                        .padding(.horizontal, 14).padding(.vertical, 6)
                        .background(filterPetId == pet.id ? Tokens.accent : Color.clear)
                        .foregroundColor(filterPetId == pet.id ? .white : Tokens.textSecondary)
                        .cornerRadius(20)
                        .overlay(RoundedRectangle(cornerRadius: 20)
                            .stroke(filterPetId == pet.id ? Color.clear : Tokens.border))
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
        }
    }

    private var monthNav: some View {
        HStack {
            Button { prevMonth() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: 32, height: 32)
                    .background(Tokens.surface)
                    .cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
            }
            Spacer()
            Text("\(CalendarHelper.monthNames[month]) \(String(year))")
                .font(.system(.body, design: .serif))
                .fontWeight(.semibold)
                .foregroundColor(Tokens.text)
            Spacer()
            Button { nextMonth() } label: {
                Image(systemName: "chevron.right")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: 32, height: 32)
                    .background(Tokens.surface)
                    .cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 16)
        .padding(.bottom, 8)
    }

    private var eventsList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("EVENTS")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Tokens.textSecondary)
                .tracking(1)
                .padding(.top, 12)

            if selectedEvents.isEmpty {
                Text("No events for this date")
                    .font(.system(size: 13))
                    .foregroundColor(Tokens.textTertiary)
                    .padding(.vertical, 12)
            } else {
                ForEach(selectedEvents) { evt in
                    let petColor = petStore.getById(evt.petId)?.color ?? Tokens.accent
                    EventRow(event: evt, petColor: petColor) { title, category, date, time in
                        calendarStore.update(evt.id, title: title, category: category,
                                             eventDate: date, eventTime: time)
                    } onDelete: {
                        calendarStore.remove(evt.id)
                    }
                }
            }
        }
        .padding(.horizontal, 20)
    }

    private func prevMonth() {
        if month == 0 { month = 11; year -= 1 } else { month -= 1 }
    }
    private func nextMonth() {
        if month == 11 { month = 0; year += 1 } else { month += 1 }
    }
}
