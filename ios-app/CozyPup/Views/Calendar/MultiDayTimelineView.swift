import SwiftUI

struct MultiDayTimelineView: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @Binding var filterPetId: String?
    var onSelectDay: (String) -> Void

    enum ZoomLevel: Int, CaseIterable {
        case day = 0, week, month, year
        var dayRange: (future: Int, past: Int) {
            switch self {
            case .day: return (365, 365)
            case .week: return (365, 365)
            case .month: return (365, 365)
            case .year: return (365, 730)
            }
        }
        var label: String {
            switch self { case .day: return "DAY"; case .week: return "WEEK"; case .month: return "MONTH"; case .year: return "YEAR" }
        }
    }

    @State private var zoomLevel: ZoomLevel = .day
    @GestureState private var pinchScale: CGFloat = 1.0

    private var days: [Date] {
        let cal = Calendar.current
        let today = Date()
        let range = zoomLevel.dayRange
        let total = range.future + range.past + 1
        return (0..<total).compactMap { i in
            cal.date(byAdding: .day, value: range.future - i, to: today)
        }
    }

    private var todayIndex: Int {
        zoomLevel.dayRange.future
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(showsIndicators: false) {
                LazyVStack(spacing: 0) {
                    ForEach(Array(days.enumerated()), id: \.offset) { index, date in
                        let dateKey = dateString(date)
                        let dayEvents = eventsForDate(dateKey)

                        // Month header when day is 1st of month
                        if isFirstOfMonth(date) {
                            monthHeader(for: date)
                                .id("month-\(index)")
                        }

                        DayRow(
                            date: date,
                            events: dayEvents,
                            pets: petStore.pets,
                            zoomLevel: zoomLevel,
                            isToday: index == todayIndex,
                            onTap: { onSelectDay(dateKey) },
                            onUpdate: { id, title, category, date, time in
                                calendarStore.update(id, title: title, category: category,
                                                     eventDate: date, eventTime: time)
                            },
                            onDelete: { id in calendarStore.remove(id) }
                        )
                        .id(index)
                    }
                }
                .padding(.bottom, Tokens.spacing.xl)
            }
            .onAppear {
                proxy.scrollTo(todayIndex, anchor: .top)
            }
        }
        .animation(.easeInOut(duration: 0.35), value: zoomLevel)
    }

    // MARK: - Month Header

    private func monthHeader(for date: Date) -> some View {
        let f = DateFormatter()
        f.dateFormat = "MMMM yyyy"
        let title = f.string(from: date)

        return HStack {
            Text(title.uppercased())
                .font(Tokens.fontCaption.weight(.semibold))
                .foregroundColor(Tokens.accent)
                .tracking(1.2)
            Spacer()
        }
        .padding(.horizontal, Tokens.spacing.lg)
        .padding(.top, Tokens.spacing.lg)
        .padding(.bottom, Tokens.spacing.sm)
    }

    private func isFirstOfMonth(_ date: Date) -> Bool {
        Calendar.current.component(.day, from: date) == 1
    }

    private func eventsForDate(_ dateKey: String) -> [CalendarEvent] {
        calendarStore.eventsForDate(dateKey).filter {
            filterPetId == nil || $0.petId == filterPetId
        }
    }

    private func dateString(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: date)
    }
}

// MARK: - DayRow

struct DayRow: View {
    let date: Date
    let events: [CalendarEvent]
    let pets: [Pet]
    let zoomLevel: MultiDayTimelineView.ZoomLevel
    let isToday: Bool
    let onTap: () -> Void
    var onUpdate: ((String, String, EventCategory, String, String?) -> Void)?
    var onDelete: ((String) -> Void)?

    private var cal: Calendar { Calendar.current }
    private var dayNum: Int { cal.component(.day, from: date) }
    private var weekdayShort: String {
        let f = DateFormatter()
        f.dateFormat = "EEE"
        return f.string(from: date).uppercased()
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            // Left: date column
            dateColumn
                .onTapGesture { onTap() }

            // Center: vertical timeline line + dot
            timelineLine

            // Right: event content
            eventContent
        }
        .padding(.horizontal, Tokens.spacing.md)
    }

    // MARK: - Date Column

    private var dateColumn: some View {
        VStack(alignment: .trailing, spacing: 1) {
            Text(weekdayShort)
                .font(Tokens.fontCaption2.weight(.medium))
                .foregroundColor(isToday ? Tokens.accent : Tokens.textTertiary)

            Text("\(dayNum)")
                .font(.system(size: dateSize, weight: isToday ? .bold : .regular, design: .serif))
                .foregroundColor(isToday ? Tokens.accent : Tokens.text)
        }
        .frame(width: dateColumnWidth, alignment: .trailing)
        .padding(.trailing, Tokens.spacing.sm)
        .padding(.vertical, rowVerticalPadding)
    }

    // MARK: - Timeline Line

    private var timelineLine: some View {
        VStack(spacing: 0) {
            Rectangle()
                .fill(isToday ? Tokens.accent.opacity(0.3) : Tokens.border)
                .frame(width: 1)
                .frame(maxHeight: .infinity)
        }
        .frame(width: Tokens.spacing.lg)
        .overlay {
            Circle()
                .fill(isToday ? Tokens.accent : (events.isEmpty ? Tokens.border : Tokens.textSecondary))
                .frame(width: isToday ? 8 : 5, height: isToday ? 8 : 5)
        }
    }

    // MARK: - Event Content

    private var eventContent: some View {
        VStack(alignment: .leading, spacing: eventCardSpacing) {
            if events.isEmpty {
                Color.clear.frame(height: emptyRowHeight)
            } else {
                switch zoomLevel {
                case .day:
                    dayContent
                case .week:
                    weekContent
                case .month:
                    monthContent
                case .year:
                    yearContent
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, Tokens.spacing.xs)
        .padding(.vertical, rowVerticalPadding)
    }

    // MARK: - Zoom-dependent sizing

    private var dateColumnWidth: CGFloat { [56, 44, 36, 28][zoomLevel.rawValue] }
    private var dateSize: CGFloat { [26, 20, 14, 11][zoomLevel.rawValue] }
    private var rowVerticalPadding: CGFloat { [10, 6, 3, 1][zoomLevel.rawValue] }
    private var emptyRowHeight: CGFloat { [28, 16, 8, 4][zoomLevel.rawValue] }
    private var eventCardSpacing: CGFloat { [Tokens.spacing.sm, Tokens.spacing.xs, 2, 1][zoomLevel.rawValue] }

    // MARK: - Day: event cards

    @ViewBuilder var dayContent: some View {
        ForEach(events, id: \.id) { evt in
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: Tokens.spacing.sm) {
                    // Category accent bar
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(categoryColor(evt.category))
                        .frame(width: 3, height: 36)

                    VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                        Text(evt.title)
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.text)
                            .lineLimit(2)

                        HStack(spacing: Tokens.spacing.xs) {
                            if let time = evt.eventTime {
                                Text(time)
                                    .font(Tokens.fontCaption2)
                                    .foregroundColor(Tokens.textTertiary)
                            }
                            Circle()
                                .fill(petColor(for: evt))
                                .frame(width: 6, height: 6)
                            if let name = evt.petName {
                                Text(name)
                                    .font(Tokens.fontCaption2)
                                    .foregroundColor(Tokens.textTertiary)
                            }
                        }
                    }
                    Spacer()
                }

                // Show photos if any
                if !evt.photos.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 4) {
                            ForEach(evt.photos, id: \.self) { urlStr in
                                AsyncImage(url: APIClient.shared.avatarURL(urlStr)) { image in
                                    image.resizable().scaledToFill()
                                } placeholder: {
                                    Tokens.placeholderBg
                                }
                                .frame(width: 48, height: 36)
                                .clipped()
                                .cornerRadius(6)
                            }
                        }
                        .padding(.leading, Tokens.spacing.md)
                        .padding(.top, 4)
                    }
                }
            }
            .padding(.vertical, Tokens.spacing.sm)
            .padding(.horizontal, Tokens.spacing.sm)
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
            .contextMenu {
                if let onUpdate {
                    Button {
                        onUpdate(evt.id, evt.title, evt.category, evt.eventDate, evt.eventTime)
                    } label: {
                        Label(Lang.shared.isZh ? "编辑" : "Edit", systemImage: "pencil")
                    }
                }
                if let onDelete {
                    Button(role: .destructive) { Haptics.medium(); onDelete(evt.id) } label: {
                        Label(L.delete, systemImage: "trash")
                    }
                }
            }
        }
    }

    // MARK: - Week: compact single line per event

    @ViewBuilder var weekContent: some View {
        ForEach(events.prefix(3), id: \.id) { evt in
            HStack(spacing: Tokens.spacing.xs) {
                RoundedRectangle(cornerRadius: 1)
                    .fill(categoryColor(evt.category))
                    .frame(width: 2, height: 14)
                Text(evt.title)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.text)
                    .lineLimit(1)
                Spacer()
                if let time = evt.eventTime {
                    Text(time)
                        .font(Tokens.fontCaption2)
                        .foregroundColor(Tokens.textTertiary)
                }
            }
            .padding(.vertical, 3)
            .padding(.horizontal, Tokens.spacing.sm)
            .background(Tokens.surface)
            .cornerRadius(Tokens.spacing.sm)
        }
        if events.count > 3 {
            Text("+\(events.count - 3) more")
                .font(Tokens.fontCaption2)
                .foregroundColor(Tokens.textTertiary)
                .padding(.leading, Tokens.spacing.sm)
        }
    }

    // MARK: - Month: colored dots

    @ViewBuilder var monthContent: some View {
        if !events.isEmpty {
            HStack(spacing: 4) {
                ForEach(events.prefix(6), id: \.id) { evt in
                    Circle()
                        .fill(petColor(for: evt))
                        .frame(width: 7, height: 7)
                }
                if events.count > 6 {
                    Text("+\(events.count - 6)")
                        .font(.system(size: 9))
                        .foregroundColor(Tokens.textTertiary)
                }
            }
            .padding(.vertical, 2)
        }
    }

    // MARK: - Year: thin bar

    @ViewBuilder var yearContent: some View {
        if !events.isEmpty {
            HStack(spacing: 1) {
                ForEach(events.prefix(5), id: \.id) { evt in
                    RoundedRectangle(cornerRadius: 1)
                        .fill(petColor(for: evt))
                        .frame(width: 10, height: 3)
                }
            }
        }
    }

    // MARK: - Helpers

    private func petColor(for event: CalendarEvent) -> Color {
        if let hex = event.petColorHex, !hex.isEmpty {
            return Color(hex: hex)
        }
        if let pet = pets.first(where: { $0.id == event.petId }) {
            return pet.color
        }
        return Tokens.accent
    }

    private func categoryColor(_ category: EventCategory) -> Color {
        switch category {
        case .diet: return Tokens.green
        case .medical: return Tokens.blue
        case .daily: return Tokens.accent
        case .abnormal: return Tokens.red
        case .vaccine: return Tokens.purple
        case .deworming: return Tokens.orange
        case .excretion: return Tokens.textSecondary
        }
    }
}
