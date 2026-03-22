import SwiftUI

struct CalendarDrawer: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @Binding var isPresented: Bool

    @State private var year: Int
    @State private var month: Int
    @State private var selectedDate: String?
    @State private var filterPetId: String?

    init(isPresented: Binding<Bool>) {
        _isPresented = isPresented
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
        ZStack(alignment: .topTrailing) {
            ScrollView(showsIndicators: false) {
                VStack(spacing: 0) {
                    
                    // Pet avatars
                    HStack(spacing: 16) {
                        ForEach(petStore.pets) { pet in
                            Button {
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    filterPetId = filterPetId == pet.id ? nil : pet.id
                                }
                            } label: {
                                PetAvatarCircle(
                                    pet: pet,
                                    size: 56,
                                    isActiveFilter: filterPetId == pet.id,
                                    isDimmed: filterPetId != nil && filterPetId != pet.id
                                )
                            }
                            .buttonStyle(.plain)
                        }
                        Spacer()
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 70)
                    .padding(.bottom, 0) // No bottom padding so triangle touches card

                    // Calendar Card
                    calendarCard
                        .padding(.horizontal, 16)
                        .padding(.bottom, 16)
                        .shadow(color: .black.opacity(0.03), radius: 8, y: 2)

                    // Events List
                    if selectedDate != nil {
                        eventsList
                            .padding(.horizontal, 16)
                            .padding(.bottom, 30)
                    } else {
                        Spacer().frame(height: 30)
                    }
                }
            }
            
            // Close button
            Button {
                withAnimation(.easeInOut(duration: 0.3)) { isPresented = false }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: 36, height: 36)
                    .background(Tokens.surface)
                    .clipShape(Circle())
            }
            .padding(.trailing, 16)
            .padding(.top, 16)
        }
        .task { await calendarStore.fetchMonth(year: year, month: month + 1) }
        .onChange(of: month) { Task { await calendarStore.fetchMonth(year: year, month: month + 1) } }
        .onChange(of: year) { Task { await calendarStore.fetchMonth(year: year, month: month + 1) } }
        .background(Tokens.bg)
        .foregroundColor(Tokens.text)
    }

    // MARK: - Calendar Card

    private var calendarCard: some View {
        VStack(spacing: 0) {
            // Month navigation
            HStack {
                Button { prevMonth() } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(Tokens.textSecondary)
                }
                .buttonStyle(.plain)
                
                Spacer()
                
                Text("\(CalendarHelper.monthNames[month]) \(String(year))")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(Tokens.text)
                
                Spacer()
                
                Button { nextMonth() } label: {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(Tokens.textSecondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.top, 20)
            .padding(.bottom, 16)

            // Weekday headers
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7)) {
                ForEach(["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"], id: \.self) { day in
                    Text(day)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(Tokens.textSecondary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 8)

            // Month grid
            MonthGrid(
                days: CalendarHelper.getCalendarDays(year: year, month: month),
                events: monthEvents,
                pets: petStore.pets,
                selectedDate: $selectedDate,
                filterPetId: filterPetId
            )
            .padding(.horizontal, 12)
            .padding(.bottom, 20)
        }
        .background(Tokens.surface)
        .cornerRadius(24)
    }

    // MARK: - Events

    private var eventsList: some View {
        VStack(spacing: 12) {
            if selectedEvents.isEmpty {
                Text(Lang.shared.isZh ? "该日期没有事件" : "No events for this date")
                    .font(.system(size: 14))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
            } else {
                ForEach(selectedEvents) { evt in
                    let pet = petStore.getById(evt.petId)
                    let petColor = pet?.color ?? Tokens.accent
                    EventRow(event: evt, petColor: petColor, pet: pet) { title, category, date, time in
                        calendarStore.update(evt.id, title: title, category: category,
                                             eventDate: date, eventTime: time)
                    } onDelete: {
                        calendarStore.remove(evt.id)
                    }
                }
            }
        }
    }

    private func prevMonth() {
        if month == 0 { month = 11; year -= 1 } else { month -= 1 }
    }
    private func nextMonth() {
        if month == 11 { month = 0; year += 1 } else { month += 1 }
    }
}

// MARK: - Pet Avatar Circle

struct PetAvatarCircle: View {
    let pet: Pet
    var size: CGFloat = 56
    var isActiveFilter: Bool
    var isDimmed: Bool = false

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .fill(Tokens.surface)
                    .frame(width: size, height: size)

                if !pet.avatarUrl.isEmpty {
                    AsyncImage(url: URL(string: pet.avatarUrl)) { image in
                        image.resizable().scaledToFill()
                    } placeholder: {
                        Color.gray.opacity(0.2)
                    }
                    .frame(width: size - 4, height: size - 4)
                    .clipShape(Circle())
                } else {
                    Image(systemName: pet.species == .cat ? "cat.fill" : "dog.fill")
                        .font(.system(size: size * 0.4))
                        .foregroundColor(pet.color)
                }
                
                // Border
                Circle()
                    .stroke(isActiveFilter ? Tokens.accent : Tokens.accent.opacity(0.3), lineWidth: 2)
                    .frame(width: size, height: size)
            }
            
            // Speech bubble tail pointing UP
            if isActiveFilter {
                UpTriangle()
                    .fill(Tokens.surface)
                    .frame(width: 16, height: 8)
            } else {
                Spacer().frame(height: 8)
            }
        }
        .opacity(isDimmed ? 0.6 : 1.0)
    }
}

struct UpTriangle: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}
