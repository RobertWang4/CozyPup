import SwiftUI

struct MultiDayTimelineView: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @Binding var filterPetId: String?
    var onSelectDay: (String) -> Void

    enum ZoomLevel: Int, CaseIterable {
        case day = 0, week, month, year
        var dayCount: Int {
            switch self { case .day: return 14; case .week: return 35; case .month: return 90; case .year: return 365 }
        }
        var label: String {
            switch self { case .day: return "DAY"; case .week: return "WEEK"; case .month: return "MONTH"; case .year: return "YEAR" }
        }
    }

    @State private var zoomLevel: ZoomLevel = .day
    @GestureState private var pinchScale: CGFloat = 1.0

    // Generate array of dates going back from today
    private var days: [Date] {
        let cal = Calendar.current
        let today = Date()
        return (0..<zoomLevel.dayCount).compactMap { cal.date(byAdding: .day, value: -$0, to: today) }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Zoom level label
            Text(zoomLevel.label)
                .font(Tokens.fontCaption2.weight(.semibold))
                .foregroundColor(Tokens.textTertiary)
                .tracking(1.5)
                .frame(maxWidth: .infinity)
                .padding(.vertical, Tokens.spacing.sm)

            ScrollView(showsIndicators: false) {
                LazyVStack(spacing: 0) {
                    ForEach(Array(days.enumerated()), id: \.offset) { index, date in
                        let dateKey = dateString(date)
                        let dayEvents = eventsForDate(dateKey)

                        DayRow(
                            date: date,
                            events: dayEvents,
                            pets: petStore.pets,
                            zoomLevel: zoomLevel,
                            isToday: index == 0,
                            onTap: { onSelectDay(dateKey) }
                        )
                    }
                }
            }
        }
        .gesture(
            MagnificationGesture()
                .updating($pinchScale) { value, state, _ in state = value }
                .onEnded { value in
                    withAnimation(.easeInOut(duration: 0.35)) {
                        if value < 0.7, let next = ZoomLevel(rawValue: zoomLevel.rawValue + 1) {
                            zoomLevel = next  // Pinch in -> zoom out (more days)
                        } else if value > 1.4, let prev = ZoomLevel(rawValue: zoomLevel.rawValue - 1) {
                            zoomLevel = prev  // Pinch out -> zoom in (fewer days, more detail)
                        }
                    }
                }
        )
        .animation(.easeInOut(duration: 0.35), value: zoomLevel)
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

    private var cal: Calendar { Calendar.current }
    private var dayNum: Int { cal.component(.day, from: date) }
    private var weekdayShort: String {
        let f = DateFormatter()
        f.dateFormat = "EEE"
        return f.string(from: date).uppercased()
    }
    private var isFirstOfMonth: Bool { dayNum == 1 }
    private var monthShort: String {
        let f = DateFormatter()
        f.dateFormat = "MMM"
        return f.string(from: date).uppercased()
    }

    // Zoom-dependent sizing
    private var leftWidth: CGFloat { [64, 48, 36, 24][zoomLevel.rawValue] }
    private var dateFont: Font {
        [Font.system(size: 32, design: .serif),
         .system(size: 22, design: .serif),
         .system(size: 14, design: .serif),
         .system(size: 10, design: .serif)][zoomLevel.rawValue]
    }
    private var weekdayFont: Font {
        [Tokens.fontCaption, Tokens.fontCaption2, Tokens.fontCaption2, Tokens.fontCaption2][zoomLevel.rawValue]
    }
    private var bottomPadding: CGFloat { [18, 8, 2, 0][zoomLevel.rawValue] }
    private var eventSpacing: CGFloat { [Tokens.spacing.xs, 2, 0, 0][zoomLevel.rawValue] }
    private var dateColor: Color {
        isToday ? Tokens.accent : Tokens.text
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            // Left: date column
            VStack(alignment: .trailing, spacing: Tokens.spacing.xxs) {
                if isFirstOfMonth && zoomLevel.rawValue >= 2 {
                    Text(monthShort)
                        .font(Tokens.fontCaption2.weight(.semibold))
                        .foregroundColor(Tokens.accent)
                }
                Text("\(dayNum)")
                    .font(dateFont)
                    .foregroundColor(dateColor)
                if zoomLevel.rawValue <= 1 {
                    Text(weekdayShort)
                        .font(weekdayFont)
                        .foregroundColor(isToday ? Tokens.accent : Tokens.textTertiary)
                }
            }
            .frame(width: leftWidth, alignment: .trailing)
            .padding(.trailing, Tokens.spacing.sm)
            .onTapGesture { onTap() }

            // Right: events column with vertical line
            VStack(alignment: .leading, spacing: eventSpacing) {
                if events.isEmpty && zoomLevel == .day {
                    Text("\u{2014}")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
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
            .padding(.leading, Tokens.spacing.sm)
            .padding(.bottom, bottomPadding)
            .overlay(alignment: .leading) {
                if zoomLevel != .year {
                    Rectangle()
                        .fill(Tokens.border)
                        .frame(width: 1)
                }
            }
        }
        .padding(.horizontal, Tokens.spacing.md)
    }

    // MARK: - Day zoom: full title + time + pet color dot

    @ViewBuilder var dayContent: some View {
        ForEach(events, id: \.id) { evt in
            HStack(spacing: Tokens.spacing.sm) {
                Circle()
                    .fill(petColor(for: evt))
                    .frame(width: 8, height: 8)
                VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                    Text(evt.title)
                        .font(Tokens.fontSubheadline)
                        .foregroundColor(Tokens.text)
                        .lineLimit(2)
                    if let time = evt.eventTime {
                        Text(time)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
            }
        }
    }

    // MARK: - Week zoom: one-line truncated

    @ViewBuilder var weekContent: some View {
        ForEach(events.prefix(3), id: \.id) { evt in
            HStack(spacing: Tokens.spacing.xs) {
                Circle()
                    .fill(petColor(for: evt))
                    .frame(width: 6, height: 6)
                Text(evt.title)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.text)
                    .lineLimit(1)
            }
        }
        if events.count > 3 {
            Text("+\(events.count - 3)")
                .font(Tokens.fontCaption2)
                .foregroundColor(Tokens.textTertiary)
        }
    }

    // MARK: - Month zoom: colored dots

    @ViewBuilder var monthContent: some View {
        if !events.isEmpty {
            HStack(spacing: 3) {
                ForEach(events.prefix(5), id: \.id) { evt in
                    Circle()
                        .fill(petColor(for: evt))
                        .frame(width: 6, height: 6)
                }
            }
            .padding(.vertical, 1)
        }
    }

    // MARK: - Year zoom: thin colored bar

    @ViewBuilder var yearContent: some View {
        if !events.isEmpty {
            HStack(spacing: 1) {
                ForEach(events.prefix(4), id: \.id) { evt in
                    RoundedRectangle(cornerRadius: 1)
                        .fill(petColor(for: evt))
                        .frame(width: 12, height: 3)
                }
            }
        }
    }

    private func petColor(for event: CalendarEvent) -> Color {
        if let hex = event.petColorHex, !hex.isEmpty {
            return Color(hex: hex)
        }
        if let pet = pets.first(where: { $0.id == event.petId }) {
            return pet.color
        }
        return Tokens.accent
    }
}
