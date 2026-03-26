import SwiftUI

struct SingleDayTimelineView: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    let date: String  // YYYY-MM-DD
    var filterPetId: String?
    var onBack: () -> Void

    @State private var currentDate: String
    @GestureState private var dragOffset: CGFloat = 0

    init(date: String, filterPetId: String?, onBack: @escaping () -> Void) {
        self.date = date
        self.filterPetId = filterPetId
        self.onBack = onBack
        _currentDate = State(initialValue: date)
    }

    private var events: [CalendarEvent] {
        calendarStore.eventsForDate(currentDate)
            .filter { filterPetId == nil || $0.petId == filterPetId }
            .sorted { ($0.eventTime ?? "") < ($1.eventTime ?? "") }
    }

    private var dayNumber: String {
        let parts = currentDate.split(separator: "-")
        guard parts.count == 3 else { return "" }
        return String(Int(parts[2]) ?? 0)
    }

    private var monthName: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: currentDate) else { return "" }
        f.dateFormat = "MMMM"
        return f.string(from: d)
    }

    private var weekdayName: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: currentDate) else { return "" }
        f.dateFormat = "EEEE"
        return f.string(from: d)
    }

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                // Back button
                Button {
                    onBack()
                } label: {
                    HStack(spacing: Tokens.spacing.xs) {
                        Image(systemName: "chevron.left")
                            .font(Tokens.fontSubheadline)
                        Text(L.back)
                            .font(Tokens.fontSubheadline)
                    }
                    .foregroundColor(Tokens.accent)
                }
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.bottom, Tokens.spacing.sm)

                // Date header
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text(dayNumber)
                        .font(.system(size: 36, design: .serif))
                        .foregroundColor(Tokens.text)
                    VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                        Text(monthName)
                            .font(.system(size: 20, design: .serif))
                            .foregroundColor(Tokens.textSecondary)
                        Text(weekdayName)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.bottom, Tokens.spacing.md)

                // Heat strip
                HeatStripView(events: events, pets: petStore.pets)
                    .padding(.bottom, Tokens.spacing.lg)

                // Event cards (full editing + photo upload)
                ForEach(events) { evt in
                    let pet = evt.petId.flatMap(petStore.getById)
                    TimelineEventCard(
                        event: evt,
                        petColor: pet?.color ?? Tokens.accent,
                        petName: pet?.name ?? "",
                        allowPhotoUpload: true,
                        onUpdate: { title, category, date, time in
                            calendarStore.update(evt.id, title: title, category: category,
                                                 eventDate: date, eventTime: time)
                        },
                        onDelete: {
                            calendarStore.remove(evt.id)
                        },
                        onPhotoUpload: { imageData in
                            return await calendarStore.uploadEventPhoto(eventId: evt.id, imageData: imageData)
                        },
                        onPhotoDelete: { photoUrl in
                            Task { await calendarStore.deleteEventPhoto(eventId: evt.id, photoUrl: photoUrl) }
                        }
                    )
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.bottom, 12)
                }

                if events.isEmpty {
                    Text(L.noEvents)
                        .font(Tokens.fontSubheadline)
                        .foregroundColor(Tokens.textTertiary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, Tokens.spacing.xl)
                }
            }
            .padding(.top, Tokens.spacing.sm)
        }
        .offset(x: dragOffset)
        .gesture(
            DragGesture()
                .updating($dragOffset) { value, state, _ in
                    state = value.translation.width * 0.5
                }
                .onEnded { value in
                    if value.translation.width > 80 {
                        navigateDay(-1) // swipe right = previous day
                    } else if value.translation.width < -80 {
                        navigateDay(1) // swipe left = next day
                    }
                }
        )
    }

    private func navigateDay(_ offset: Int) {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let current = f.date(from: currentDate),
              let next = Calendar.current.date(byAdding: .day, value: offset, to: current) else { return }
        withAnimation(.easeInOut(duration: 0.25)) {
            currentDate = f.string(from: next)
        }
    }
}
