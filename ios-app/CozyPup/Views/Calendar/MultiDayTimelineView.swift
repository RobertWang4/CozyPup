import SwiftUI

struct MultiDayTimelineView: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @Binding var filterPetId: String?
    var scrollToDate: String?
    var onSelectDay: (String) -> Void

    @State private var selectedDate: String?
    @State private var lastTapDate: String?
    @State private var lastTapTime: Date?

    private var cal: Calendar { Calendar.current }

    private var days: [Date] {
        let today = Date()
        return (0..<731).compactMap { i in
            cal.date(byAdding: .day, value: i - 365, to: today)
        }
    }

    /// Index for the target scroll date, or today (365) as default
    private var scrollTargetIndex: Int {
        guard let target = scrollToDate else { return 365 }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let targetDate = f.date(from: target) else { return 365 }
        let today = Date()
        let diff = cal.dateComponents([.day], from: cal.startOfDay(for: today), to: cal.startOfDay(for: targetDate)).day ?? 0
        let idx = 365 + diff
        return max(0, min(idx, days.count - 1))
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(showsIndicators: false) {
                LazyVStack(spacing: 0) {
                    ForEach(Array(days.enumerated()), id: \.offset) { index, date in
                        let dateKey = dateString(date)
                        let dayEvents = eventsForDate(dateKey)

                        if isFirstOfMonth(date) {
                            let m = cal.component(.month, from: date) - 1
                            let y = cal.component(.year, from: date)
                            sectionHeader("\(CalendarHelper.monthNames[m]) \(y)")
                        }

                        DayRow(
                            date: date,
                            events: dayEvents,
                            pets: petStore.pets,
                            isToday: index == 365,
                            isHighlighted: dateKey == selectedDate,
                            onTap: {
                                let now = Date()
                                if lastTapDate == dateKey,
                                   let last = lastTapTime,
                                   now.timeIntervalSince(last) < 0.35 {
                                    // Double tap → enter single day
                                    Haptics.light()
                                    onSelectDay(dateKey)
                                    lastTapDate = nil
                                    lastTapTime = nil
                                } else {
                                    // Single tap → highlight
                                    selectedDate = dateKey
                                    lastTapDate = dateKey
                                    lastTapTime = now
                                }
                            },
                            onUpdate: { id, title, category, date, time in
                                calendarStore.update(id, title: title, category: category,
                                                     eventDate: date, eventTime: time)
                            },
                            onDelete: { id in calendarStore.remove(id) },
                            onPhotoUpload: { id, imageData in
                                return await calendarStore.uploadEventPhoto(eventId: id, imageData: imageData)
                            },
                            onPhotoDelete: { id, photoUrl in
                                Task { await calendarStore.deleteEventPhoto(eventId: id, photoUrl: photoUrl) }
                            }
                        )
                        .id(index)
                    }
                }
                .padding(.bottom, Tokens.spacing.xl)
            }
            .onAppear {
                selectedDate = scrollToDate
                proxy.scrollTo(scrollTargetIndex, anchor: .center)
            }
        }
    }

    // MARK: - Helpers

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

    private func isFirstOfMonth(_ date: Date) -> Bool {
        cal.component(.day, from: date) == 1
    }

    private func sectionHeader(_ text: String) -> some View {
        HStack {
            Text(text.uppercased())
                .font(Tokens.fontCaption.weight(.semibold))
                .foregroundColor(Tokens.accent)
                .tracking(1.2)
            Spacer()
        }
        .padding(.horizontal, Tokens.spacing.lg)
        .padding(.top, Tokens.spacing.lg)
        .padding(.bottom, Tokens.spacing.sm)
    }
}

// MARK: - DayRow

struct DayRow: View {
    let date: Date
    let events: [CalendarEvent]
    let pets: [Pet]
    let isToday: Bool
    var isHighlighted: Bool = false
    let onTap: () -> Void
    var onUpdate: ((String, String, EventCategory, String, String?) -> Void)?
    var onDelete: ((String) -> Void)?
    var onPhotoUpload: ((String, Data) async -> String?)?
    var onPhotoDelete: ((String, String) -> Void)?

    @State private var editingEvent: CalendarEvent?
    @State private var fullScreenImage: UIImage?

    private var cal: Calendar { Calendar.current }
    private var dayNum: Int { cal.component(.day, from: date) }
    private var weekdayShort: String {
        let idx = cal.component(.weekday, from: date) - 1
        if Lang.shared.isZh {
            return ["日", "一", "二", "三", "四", "五", "六"][idx]
        }
        return ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][idx]
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            dateColumn
            timelineLine
            eventContent
        }
        .padding(.horizontal, Tokens.spacing.md)
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
        .background(
            isHighlighted
                ? RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                    .fill(Tokens.accent.opacity(0.08))
                    .padding(.horizontal, Tokens.spacing.sm)
                : nil
        )
        .fullScreenCover(isPresented: Binding(
            get: { fullScreenImage != nil },
            set: { if !$0 { fullScreenImage = nil } }
        )) {
            if let img = fullScreenImage {
                FullScreenImageViewer(image: img) {
                    fullScreenImage = nil
                }
                .ignoresSafeArea()
                .presentationBackground(.clear)
            }
        }
        .sheet(item: $editingEvent) { evt in
            if let onUpdate {
                EventEditSheet(
                    event: evt,
                    onSave: { title, category, date, time in
                        onUpdate(evt.id, title, category, date, time)
                    },
                    onPhotoUpload: onPhotoUpload.map { upload in
                        { imageData in await upload(evt.id, imageData) }
                    },
                    onPhotoDelete: onPhotoDelete.map { delete in
                        { photoUrl in delete(evt.id, photoUrl) }
                    }
                )
            }
        }
    }

    private var dateColumn: some View {
        VStack(alignment: .trailing, spacing: 1) {
            Text(weekdayShort)
                .font(Tokens.fontCaption2.weight(.medium))
                .foregroundColor(isToday ? Tokens.accent : Tokens.textTertiary)
            Text("\(dayNum)")
                .font(.system(size: 26, weight: isToday ? .bold : .regular, design: .serif))
                .foregroundColor(isToday ? Tokens.accent : Tokens.text)
        }
        .frame(width: 56, alignment: .trailing)
        .padding(.trailing, Tokens.spacing.sm)
        .padding(.vertical, 10)
    }

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

    private var eventContent: some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            if events.isEmpty {
                Color.clear.frame(height: 28)
            } else {
                ForEach(events, id: \.id) { evt in
                    VStack(alignment: .leading, spacing: 0) {
                        HStack(spacing: Tokens.spacing.sm) {
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
                                        .onTapGesture {
                                            loadFullScreenImage(from: urlStr)
                                        }
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
                        if onUpdate != nil {
                            Button { editingEvent = evt } label: {
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
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, Tokens.spacing.xs)
        .padding(.vertical, 10)
    }

    private func petColor(for event: CalendarEvent) -> Color {
        if let hex = event.petColorHex, !hex.isEmpty { return Color(hex: hex) }
        if let pet = pets.first(where: { $0.id == event.petId }) { return pet.color }
        return Tokens.accent
    }

    private func loadFullScreenImage(from urlStr: String) {
        guard let url = APIClient.shared.avatarURL(urlStr) else { return }
        Task {
            if let (data, _) = try? await URLSession.shared.data(from: url),
               let uiImage = UIImage(data: data) {
                await MainActor.run { fullScreenImage = uiImage }
            }
        }
    }

    private func categoryColor(_ category: EventCategory) -> Color {
        switch category {
        case .diet: return Tokens.green; case .medical: return Tokens.blue
        case .daily: return Tokens.accent; case .abnormal: return Tokens.red
        case .vaccine: return Tokens.purple; case .deworming: return Tokens.orange
        case .excretion: return Tokens.textSecondary
        }
    }
}
