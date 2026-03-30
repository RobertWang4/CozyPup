import SwiftUI

enum CalendarMode {
    case calendar, timeline, singleDay
}

struct CalendarDrawer: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @EnvironmentObject var dailyTaskStore: DailyTaskStore
    @Binding var isPresented: Bool

    @State private var year: Int
    @State private var month: Int
    @State private var selectedDate: String?
    @State private var filterPetId: String?
    @State private var mode: CalendarMode = .timeline
    @State private var previousMode: CalendarMode = .timeline
    @State private var singleDayDate: String?
    @State private var timelineTargetDate: String?
    @State private var showTaskManager = false
    @State private var filterCategory: EventCategory?
    @State private var isSelecting = false
    @State private var selectedEventIds: Set<String> = []

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
        var evts = calendarStore.eventsForDate(date)
        if let pid = filterPetId {
            evts = evts.filter { $0.petId == pid }
        }
        if let cat = filterCategory {
            evts = evts.filter { $0.category == cat }
        }
        return evts
    }

    var body: some View {
        VStack(spacing: 0) {
            // Pet avatars + action buttons (fixed header)
            HStack(spacing: Tokens.spacing.md) {
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
                            isDimmed: filterPetId != nil && filterPetId != pet.id,
                            avatarRevision: petStore.avatarRevision
                        )
                    }
                    .buttonStyle(.plain)
                }
                Spacer()

                // Task indicator
                Button {
                    showTaskManager = true
                } label: {
                    ZStack {
                        Circle()
                            .fill(dailyTaskStore.allCompleted ? Tokens.green.opacity(0.15) : Tokens.surface)
                            .frame(width: Tokens.size.buttonSmall, height: Tokens.size.buttonSmall)
                        Image(systemName: dailyTaskStore.allCompleted ? "checkmark.circle.fill" : "checkmark.circle")
                            .font(.system(size: 16))
                            .foregroundColor(dailyTaskStore.allCompleted ? Tokens.green : Tokens.textSecondary)
                    }
                }
                .sheet(isPresented: $showTaskManager) {
                    DailyTaskManagerSheet()
                        .environmentObject(dailyTaskStore)
                        .environmentObject(petStore)
                }

            }
            .padding(.horizontal, Tokens.spacing.lg)
            .padding(.top, 70)

            // Category filter pills
            categoryFilterRow
                .padding(.horizontal, Tokens.spacing.lg)
                .padding(.top, Tokens.spacing.sm)

            // Scrollable content area
            switch mode {
            case .calendar:
                EmptyView() // Calendar grid removed — use Apple Calendar

            case .timeline:
                MultiDayTimelineView(filterPetId: $filterPetId, filterCategory: filterCategory, scrollToDate: timelineTargetDate, isSelecting: $isSelecting, selectedEventIds: $selectedEventIds) { date in
                    singleDayDate = date
                    previousMode = .timeline
                    withAnimation(.easeInOut(duration: 0.3)) { mode = .singleDay }
                }

            case .singleDay:
                if let date = singleDayDate {
                    SingleDayTimelineView(date: date, filterPetId: filterPetId, filterCategory: filterCategory) {
                        withAnimation(.easeInOut(duration: 0.3)) { mode = previousMode }
                    }
                }
            }
        }
        .overlay(alignment: .bottom) {
            if isSelecting {
                HStack(spacing: Tokens.spacing.md) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            selectedEventIds.removeAll()
                            isSelecting = false
                        }
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(Tokens.textSecondary)
                            .frame(width: 32, height: 32)
                            .background(Tokens.bg.opacity(0.8))
                            .clipShape(Circle())
                    }

                    Text(Lang.shared.isZh
                         ? "已选 \(selectedEventIds.count) 项"
                         : "\(selectedEventIds.count) selected")
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.text)

                    Button {
                        Haptics.medium()
                        calendarStore.removeMultiple(selectedEventIds)
                        withAnimation(.easeInOut(duration: 0.2)) {
                            selectedEventIds.removeAll()
                            isSelecting = false
                        }
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(selectedEventIds.isEmpty ? Tokens.textTertiary : Tokens.red)
                            .frame(width: 32, height: 32)
                            .background(selectedEventIds.isEmpty ? Tokens.bg.opacity(0.5) : Tokens.redSoft)
                            .clipShape(Circle())
                    }
                    .disabled(selectedEventIds.isEmpty)
                }
                .padding(.horizontal, Tokens.spacing.lg)
                .padding(.vertical, Tokens.spacing.sm)
                .background(
                    Capsule()
                        .fill(.ultraThinMaterial)
                        .shadow(color: .black.opacity(0.1), radius: 12, y: 4)
                )
                .padding(.bottom, Tokens.spacing.lg)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: isSelecting)
        .padding(.horizontal, Tokens.spacing.sm)
        .task {
            await calendarStore.fetchMonth(year: year, month: month + 1)
            await petStore.fetchFromAPI()
        }
        .onChange(of: month) { Task { await calendarStore.fetchMonth(year: year, month: month + 1) } }
        .onChange(of: year) { Task { await calendarStore.fetchMonth(year: year, month: month + 1) } }
        .background(Tokens.bg)
        .foregroundColor(Tokens.text)
    }

    // MARK: - Category Filter

    private var categoryFilterRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(EventCategory.allCases, id: \.self) { cat in
                    categoryPill(cat)
                }
            }
        }
    }

    private func categoryPill(_ cat: EventCategory) -> some View {
        let active = filterCategory == cat
        let fillColor = active ? categoryColor(cat) : Tokens.surface
        let textColor = active ? Tokens.white : Tokens.textSecondary
        let borderColor = active ? Color.clear : Tokens.border
        return Button {
            withAnimation(.easeInOut(duration: 0.15)) {
                filterCategory = filterCategory == cat ? nil : cat
            }
        } label: {
            Text(cat.label)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(textColor)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(Capsule().fill(fillColor))
                .overlay(Capsule().strokeBorder(borderColor, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }

    private func categoryColor(_ cat: EventCategory) -> Color {
        switch cat {
        case .daily: return Tokens.accent
        case .diet: return Tokens.green
        case .medical: return Tokens.blue
        case .abnormal: return Tokens.red
        }
    }

    // MARK: - Calendar Card

    private var calendarCard: some View {
        VStack(spacing: 0) {
            // Month navigation
            HStack {
                Button { prevMonth() } label: {
                    Image(systemName: "chevron.left")
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.textSecondary)
                }
                .buttonStyle(.plain)
                
                Spacer()
                
                Text("\(CalendarHelper.monthNames[month]) \(String(year))")
                    .font(Tokens.fontHeadline.weight(.medium))
                    .foregroundColor(Tokens.text)
                
                Spacer()
                
                Button { nextMonth() } label: {
                    Image(systemName: "chevron.right")
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.textSecondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, Tokens.spacing.md)
            .padding(.top, 20)
            .padding(.bottom, Tokens.spacing.md)

            // Weekday headers
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7)) {
                ForEach(["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"], id: \.self) { day in
                    Text(day)
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.textSecondary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.bottom, Tokens.spacing.sm)

            // Month grid
            MonthGrid(
                days: CalendarHelper.getCalendarDays(year: year, month: month),
                events: monthEvents,
                pets: petStore.pets,
                selectedDate: $selectedDate,
                filterPetId: filterPetId,
                onLongPress: { date in
                    singleDayDate = date
                    selectedDate = date
                    previousMode = .calendar
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                        mode = .singleDay
                    }
                },
                onDoubleTap: { date in
                    timelineTargetDate = date
                    selectedDate = date
                    previousMode = .calendar
                    withAnimation(.easeInOut(duration: 0.35)) {
                        mode = .timeline
                    }
                }
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
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Tokens.spacing.md)
            } else {
                ForEach(selectedEvents) { evt in
                    let pet = evt.petId.flatMap(petStore.getById)
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
    var avatarRevision: Int = 0

    var body: some View {
        VStack(spacing: Tokens.spacing.sm) {
            ZStack {
                Circle()
                    .fill(Tokens.surface)
                    .frame(width: size, height: size)

                if !pet.avatarUrl.isEmpty,
                   let baseURL = APIClient.shared.avatarURL(pet.avatarUrl),
                   let url = URL(string: "\(baseURL.absoluteString)?v=\(avatarRevision)") {
                    CachedAsyncImage(url: url) { image in
                        image.resizable().scaledToFill()
                    } placeholder: {
                        Tokens.placeholderBg
                    }
                    .frame(width: size - 4, height: size - 4)
                    .clipShape(Circle())
                } else {
                    Image(systemName: pet.species == .cat ? "cat.fill" : "dog.fill")
                        .font(.system(size: size * 0.4))
                        .foregroundColor(pet.color)
                }
                
                // Border — pet's own color
                Circle()
                    .stroke(isActiveFilter ? pet.color : pet.color.opacity(0.3), lineWidth: 2)
                    .frame(width: size, height: size)
            }
            
            // Speech bubble tail pointing UP
            if isActiveFilter {
                UpTriangle()
                    .fill(Tokens.surface)
                    .frame(width: Tokens.spacing.md, height: Tokens.spacing.sm)
            } else {
                Spacer().frame(height: Tokens.spacing.sm)
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
