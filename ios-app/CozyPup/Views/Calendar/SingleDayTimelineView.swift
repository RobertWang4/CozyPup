import SwiftUI

struct SingleDayTimelineView: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    let date: String  // YYYY-MM-DD
    var filterPetId: String?
    var filterCategory: EventCategory?
    var onBack: () -> Void
    var onLongPressEvent: ((CalendarEvent) -> Void)? = nil

    @State private var currentDate: String
    @State private var newEventDraft: CalendarEvent?
    @State private var showDayChat = false
    @GestureState private var dragOffset: CGFloat = 0

    init(date: String, filterPetId: String?, filterCategory: EventCategory? = nil, onBack: @escaping () -> Void, onLongPressEvent: ((CalendarEvent) -> Void)? = nil) {
        self.date = date
        self.filterPetId = filterPetId
        self.filterCategory = filterCategory
        self.onBack = onBack
        self.onLongPressEvent = onLongPressEvent
        _currentDate = State(initialValue: date)
    }

    private var events: [CalendarEvent] {
        calendarStore.eventsForDate(currentDate)
            .filter {
                (filterPetId == nil || $0.petId == filterPetId) &&
                (filterCategory == nil || $0.category == filterCategory)
            }
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
                // Back button + history button
                HStack {
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
                    Spacer()
                    Button {
                        showDayChat = true
                    } label: {
                        Image(systemName: "clock.arrow.circlepath")
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.accent)
                    }
                    Button {
                        newEventDraft = CalendarEvent(
                            petId: filterPetId ?? petStore.pets.first?.id,
                            eventDate: currentDate,
                            eventTime: nil,
                            title: "",
                            type: .log,
                            category: filterCategory ?? .daily,
                            rawText: "",
                            source: .manual
                        )
                    } label: {
                        Image(systemName: "plus")
                            .font(Tokens.fontSubheadline.weight(.semibold))
                            .foregroundColor(Tokens.accent)
                            .padding(.leading, Tokens.spacing.md)
                    }
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
                        onUpdate: { title, category, date, time, cost, reminderAt in
                            calendarStore.update(evt.id, title: title, category: category,
                                                 eventDate: date, eventTime: time, cost: cost, reminderAt: reminderAt)
                        },
                        onDelete: {
                            calendarStore.remove(evt.id)
                        },
                        onPhotoUpload: { imageData in
                            return await calendarStore.uploadEventPhoto(eventId: evt.id, imageData: imageData)
                        },
                        onPhotoDelete: { photoUrl in
                            Task { await calendarStore.deleteEventPhoto(eventId: evt.id, photoUrl: photoUrl) }
                        },
                        onLocationUpdate: { name, address, lat, lng, placeId in
                            Task { await calendarStore.updateLocation(eventId: evt.id, name: name, address: address, lat: lat, lng: lng, placeId: placeId) }
                        },
                        onLocationRemove: {
                            Task { await calendarStore.removeLocation(eventId: evt.id) }
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
        .sheet(isPresented: $showDayChat) {
            DayChatSheet(date: currentDate)
                .presentationDetents([.medium, .large])
        }
        .sheet(item: $newEventDraft) { draft in
            EventEditSheet(
                event: draft,
                onSave: { title, category, date, time, cost, reminderAt in
                    var newEvent = CalendarEvent(
                        petId: draft.petId,
                        eventDate: date,
                        eventTime: time,
                        title: title,
                        type: .log,
                        category: category,
                        rawText: title,
                        source: .manual
                    )
                    newEvent.cost = cost
                    newEvent.reminderAt = reminderAt
                    calendarStore.add(newEvent)
                }
            )
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
