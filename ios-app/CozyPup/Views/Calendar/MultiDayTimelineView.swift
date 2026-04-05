import SwiftUI

struct MultiDayTimelineView: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @Binding var filterPetId: String?
    var filterCategory: EventCategory?
    var scrollToDate: String?
    @Binding var isSelecting: Bool
    @Binding var selectedEventIds: Set<String>
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
                            isSelecting: $isSelecting,
                            selectedEventIds: $selectedEventIds,
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
                            onUpdate: { id, title, category, date, time, cost, reminderAt in
                                calendarStore.update(id, title: title, category: category,
                                                     eventDate: date, eventTime: time, cost: cost, reminderAt: reminderAt)
                            },
                            onDelete: { id in calendarStore.remove(id) },
                            onPhotoUpload: { id, imageData in
                                return await calendarStore.uploadEventPhoto(eventId: id, imageData: imageData)
                            },
                            onPhotoDelete: { id, photoUrl in
                                Task { await calendarStore.deleteEventPhoto(eventId: id, photoUrl: photoUrl) }
                            },
                            onLocationUpdate: { id, name, address, lat, lng, placeId in
                                Task { await calendarStore.updateLocation(eventId: id, name: name, address: address, lat: lat, lng: lng, placeId: placeId) }
                            },
                            onLocationRemove: { id in
                                Task { await calendarStore.removeLocation(eventId: id) }
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
            (filterPetId == nil || $0.petId == filterPetId) &&
            (filterCategory == nil || $0.category == filterCategory)
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
    @Binding var isSelecting: Bool
    @Binding var selectedEventIds: Set<String>
    let onTap: () -> Void
    var onUpdate: ((String, String, EventCategory, String, String?, Double?, String?) -> Void)?
    var onDelete: ((String) -> Void)?
    var onPhotoUpload: ((String, Data) async -> String?)?
    var onPhotoDelete: ((String, String) -> Void)?
    var onLocationUpdate: ((String, String, String, Double, Double, String) -> Void)?  // eventId, name, address, lat, lng, placeId
    var onLocationRemove: ((String) -> Void)?  // eventId

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
                    onSave: { title, category, date, time, cost, reminderAt in
                        onUpdate(evt.id, title, category, date, time, cost, reminderAt)
                    },
                    onPhotoUpload: onPhotoUpload.map { upload in
                        { imageData in await upload(evt.id, imageData) }
                    },
                    onPhotoDelete: onPhotoDelete.map { delete in
                        { photoUrl in delete(evt.id, photoUrl) }
                    },
                    onLocationUpdate: onLocationUpdate.map { update in
                        { name, address, lat, lng, placeId in update(evt.id, name, address, lat, lng, placeId) }
                    },
                    onLocationRemove: onLocationRemove.map { remove in
                        { remove(evt.id) }
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
        .frame(width: 40, alignment: .trailing)
        .padding(.trailing, Tokens.spacing.xs)
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
                    let isSelected = selectedEventIds.contains(evt.id)

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

                            // Selection indicator — right side of card
                            if isSelecting {
                                selectionCircle(isSelected: isSelected)
                                    .transition(.opacity)
                            }
                        }

                        if !evt.photos.isEmpty {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: Tokens.spacing.sm) {
                                    ForEach(evt.photos, id: \.self) { urlStr in
                                        CachedAsyncImage(url: APIClient.shared.avatarURL(urlStr)) { image in
                                            image.resizable().scaledToFill()
                                        } placeholder: {
                                            Tokens.placeholderBg
                                        }
                                        .frame(width: 80, height: 80)
                                        .clipped()
                                        .cornerRadius(Tokens.radiusSmall)
                                        .onTapGesture {
                                            if !isSelecting {
                                                loadFullScreenImage(from: urlStr)
                                            }
                                        }
                                    }
                                }
                                .padding(.leading, Tokens.spacing.md)
                                .padding(.top, Tokens.spacing.xs)
                            }
                        }

                        if let cost = evt.cost, cost > 0 {
                            HStack(spacing: 3) {
                                Image(systemName: "yensign.circle")
                                    .font(.system(size: 8))
                                Text("¥\(cost, specifier: cost == cost.rounded() ? "%.0f" : "%.2f")")
                                    .font(Tokens.fontCaption2)
                                    .lineLimit(1)
                            }
                            .foregroundColor(Tokens.orange)
                            .padding(.leading, Tokens.spacing.md)
                            .padding(.top, 2)
                        }

                        if let loc = evt.locationName, !loc.isEmpty {
                            HStack(spacing: 3) {
                                Image(systemName: "mappin")
                                    .font(.system(size: 8))
                                Text(loc)
                                    .font(Tokens.fontCaption2)
                                    .lineLimit(1)
                            }
                            .foregroundColor(Tokens.textTertiary)
                            .padding(.leading, Tokens.spacing.md)
                            .padding(.top, 2)
                        }
                    }
                    .padding(.vertical, Tokens.spacing.sm)
                    .padding(.horizontal, Tokens.spacing.sm)
                    .background(Tokens.surface)
                    .overlay(
                        RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                            .strokeBorder(isSelecting && isSelected ? Tokens.accent.opacity(0.4) : .clear, lineWidth: 1.5)
                    )
                    .cornerRadius(Tokens.radiusSmall)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        if isSelecting {
                            Haptics.light()
                            if isSelected {
                                selectedEventIds.remove(evt.id)
                            } else {
                                selectedEventIds.insert(evt.id)
                            }
                        }
                    }
                    .contextMenu {
                        if !isSelecting {
                            if onUpdate != nil {
                                Button { editingEvent = evt } label: {
                                    Label(Lang.shared.isZh ? "编辑" : "Edit", systemImage: "pencil")
                                }
                            }
                            Button {
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    selectedEventIds.insert(evt.id)
                                    isSelecting = true
                                }
                            } label: {
                                Label(Lang.shared.isZh ? "多选" : "Select", systemImage: "checkmark.circle")
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
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, Tokens.spacing.xs)
        .padding(.vertical, 10)
    }

    @ViewBuilder
    private func selectionCircle(isSelected: Bool) -> some View {
        ZStack {
            Circle()
                .stroke(isSelected ? Tokens.accent : Tokens.border, lineWidth: 1)
                .frame(width: 20, height: 20)
            if isSelected {
                Circle()
                    .fill(Tokens.accent)
                    .frame(width: 20, height: 20)
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(Tokens.white)
            }
        }
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
        case .daily: return Tokens.accent; case .diet: return Tokens.green
        case .medical: return Tokens.blue; case .abnormal: return Tokens.red
        }
    }
}
