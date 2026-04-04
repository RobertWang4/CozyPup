import SwiftUI
import PhotosUI

struct EventEditSheet: View {
    let event: CalendarEvent
    var onSave: (String, EventCategory, String, String?, Double?, String?) -> Void  // title, category, date, time, cost, reminderAt
    var onPhotoUpload: ((Data) async -> String?)?  // returns photo URL on success
    var onPhotoDelete: ((String) -> Void)?
    var onLocationUpdate: ((String, String, Double, Double, String) -> Void)?  // name, address, lat, lng, placeId
    var onLocationRemove: (() -> Void)?
    @Environment(\.dismiss) private var dismiss

    @State private var title: String
    @State private var category: EventCategory
    @State private var date: String
    @State private var time: String
    @State private var cost: String
    @State private var hasReminder: Bool
    @State private var reminderDate: Date
    @State private var photos: [String]
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var cropImage: UIImage?
    @State private var showCropSheet = false
    @State private var photoToDelete: String?
    @State private var showLocationPicker = false
    @State private var locationName: String?
    @State private var locationAddress: String?
    @State private var locationLat: Double?
    @State private var locationLng: Double?
    @State private var placeId: String?

    init(
        event: CalendarEvent,
        onSave: @escaping (String, EventCategory, String, String?, Double?, String?) -> Void,
        onPhotoUpload: ((Data) async -> String?)? = nil,
        onPhotoDelete: ((String) -> Void)? = nil,
        onLocationUpdate: ((String, String, Double, Double, String) -> Void)? = nil,
        onLocationRemove: (() -> Void)? = nil
    ) {
        self.event = event
        self.onSave = onSave
        self.onPhotoUpload = onPhotoUpload
        self.onPhotoDelete = onPhotoDelete
        self.onLocationUpdate = onLocationUpdate
        self.onLocationRemove = onLocationRemove
        _title = State(initialValue: event.title)
        _category = State(initialValue: event.category)
        _date = State(initialValue: event.eventDate)
        _time = State(initialValue: event.eventTime ?? "")
        _cost = State(initialValue: event.cost.map { String(Int($0)) } ?? "")
        _hasReminder = State(initialValue: event.reminderAt != nil)
        let defaultReminder: Date = {
            if let r = event.reminderAt, let d = ISO8601DateFormatter().date(from: r) { return d }
            // Default: event date + time or now + 1 hour
            if let d = Self.parseEventDateTime(event.eventDate, event.eventTime) { return d }
            return Date().addingTimeInterval(3600)
        }()
        _reminderDate = State(initialValue: defaultReminder)
        _photos = State(initialValue: event.photos)
        _locationName = State(initialValue: event.locationName)
        _locationAddress = State(initialValue: event.locationAddress)
        _locationLat = State(initialValue: event.locationLat)
        _locationLng = State(initialValue: event.locationLng)
        _placeId = State(initialValue: event.placeId)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Tokens.spacing.lg) {
                    // Card 1: Title + Date/Time
                    formCard {
                        cardField(label: L.title) {
                            TextField(L.title, text: $title)
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                        }

                        cardDivider

                        HStack(spacing: 0) {
                            cardField(label: L.date) {
                                TextField("YYYY-MM-DD", text: $date)
                                    .font(Tokens.fontBody)
                                    .foregroundColor(Tokens.text)
                            }

                            Rectangle()
                                .fill(Tokens.divider)
                                .frame(width: 0.5)
                                .padding(.vertical, Tokens.spacing.sm)

                            cardField(label: L.time) {
                                TextField("HH:MM", text: $time)
                                    .font(Tokens.fontBody)
                                    .foregroundColor(Tokens.text)
                            }
                        }
                    }

                    // Card 2: Category
                    VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                        Text(Lang.shared.isZh ? "分类" : "Category")
                            .font(Tokens.fontCaption.weight(.medium))
                            .foregroundColor(Tokens.textTertiary)
                            .padding(.leading, Tokens.spacing.xs)

                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: Tokens.spacing.sm) {
                                ForEach(EventCategory.allCases, id: \.self) { c in
                                    categoryChip(c)
                                }
                            }
                        }
                    }

                    // Card 3: Cost
                    formCard {
                        cardField(label: Lang.shared.isZh ? "花费" : "Cost") {
                            HStack {
                                Text("$")
                                    .font(Tokens.fontBody)
                                    .foregroundColor(Tokens.textTertiary)
                                TextField(Lang.shared.isZh ? "金额（选填）" : "Amount (optional)", text: $cost)
                                    .font(Tokens.fontBody)
                                    .foregroundColor(Tokens.text)
                                    .keyboardType(.decimalPad)
                            }
                        }
                    }

                    // Card 4: Reminder
                    formCard {
                        Toggle(isOn: $hasReminder.animation(.easeInOut(duration: 0.2))) {
                            HStack(spacing: Tokens.spacing.xs) {
                                Image(systemName: hasReminder ? "bell.fill" : "bell")
                                    .font(.system(size: 14))
                                    .foregroundColor(hasReminder ? Tokens.accent : Tokens.textTertiary)
                                Text(Lang.shared.isZh ? "提醒" : "Reminder")
                                    .font(Tokens.fontBody)
                                    .foregroundColor(Tokens.text)
                            }
                        }
                        .tint(Tokens.accent)
                        .padding(.horizontal, Tokens.spacing.md)
                        .padding(.vertical, Tokens.spacing.sm + 2)

                        if hasReminder {
                            cardDivider
                            HStack {
                                Text(Lang.shared.isZh ? "时间" : "When")
                                    .font(Tokens.fontBody)
                                    .foregroundColor(Tokens.textSecondary)
                                Spacer()
                                DatePicker("", selection: $reminderDate)
                                    .datePickerStyle(.compact)
                                    .labelsHidden()
                                    .tint(Tokens.accent)
                            }
                            .padding(.horizontal, Tokens.spacing.md)
                            .padding(.vertical, Tokens.spacing.sm)
                        }
                    }

                    // Card 5: Photos
                    photoSection

                    // Card 4: Location
                    VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                        Text(Lang.shared.isZh ? "地点" : "Location")
                            .font(Tokens.fontCaption.weight(.medium))
                            .foregroundColor(Tokens.textTertiary)
                            .padding(.leading, Tokens.spacing.xs)

                        if let locName = locationName {
                            // Has location — show it with option to change/remove
                            HStack {
                                Button {
                                    if let lat = locationLat, let lng = locationLng {
                                        openGoogleMaps(lat: lat, lng: lng, placeId: placeId, name: locName)
                                    }
                                } label: {
                                    HStack(spacing: Tokens.spacing.xs) {
                                        Image(systemName: "mappin.circle.fill")
                                            .foregroundColor(Tokens.accent)
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(locName)
                                                .font(Tokens.fontBody)
                                                .foregroundColor(Tokens.accent)
                                            if let addr = locationAddress, !addr.isEmpty {
                                                Text(addr)
                                                    .font(Tokens.fontCaption)
                                                    .foregroundColor(Tokens.textSecondary)
                                                    .lineLimit(1)
                                            }
                                        }
                                    }
                                }
                                Spacer()
                                Button {
                                    locationName = nil
                                    locationAddress = nil
                                    locationLat = nil
                                    locationLng = nil
                                    placeId = nil
                                    onLocationRemove?()
                                } label: {
                                    Image(systemName: "xmark.circle.fill")
                                        .foregroundColor(Tokens.textTertiary)
                                }
                            }
                            .padding(Tokens.spacing.md)
                            .background(Tokens.surface)
                            .cornerRadius(Tokens.radius)
                        } else {
                            // No location — show add button
                            Button {
                                showLocationPicker = true
                            } label: {
                                HStack(spacing: Tokens.spacing.xs) {
                                    Image(systemName: "mappin.circle")
                                        .foregroundColor(Tokens.textTertiary)
                                    Text(Lang.shared.isZh ? "添加地点" : "Add Location")
                                        .font(Tokens.fontBody)
                                        .foregroundColor(Tokens.textSecondary)
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                        .font(.system(size: 12))
                                        .foregroundColor(Tokens.textTertiary)
                                }
                                .padding(Tokens.spacing.md)
                                .background(Tokens.surface)
                                .cornerRadius(Tokens.radius)
                            }
                        }
                    }
                }
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.top, Tokens.spacing.sm)
                .padding(.bottom, Tokens.spacing.xl)
            }
            .background(Tokens.bg)
            .navigationTitle(Lang.shared.isZh ? "编辑事件" : "Edit Event")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(L.cancel) { dismiss() }
                        .foregroundColor(Tokens.textSecondary)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L.save) {
                        let costVal = Double(cost)
                        let reminderAtVal = hasReminder ? ISO8601DateFormatter().string(from: reminderDate) : nil
                        onSave(title, category, date, time.isEmpty ? nil : time, costVal, reminderAtVal)
                        // Also persist location if it was added/changed in this session
                        if let name = locationName, let lat = locationLat, let lng = locationLng {
                            onLocationUpdate?(name, locationAddress ?? "", lat, lng, placeId ?? "")
                        } else if event.locationName != nil && locationName == nil {
                            // Location was removed
                            onLocationRemove?()
                        }
                        dismiss()
                    }
                    .fontWeight(.semibold)
                    .foregroundColor(Tokens.accent)
                    .disabled(title.isEmpty)
                }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .onChange(of: selectedPhotoItem) { _, item in
            guard let item else { return }
            Task {
                if let data = try? await item.loadTransferable(type: Data.self),
                   let uiImage = UIImage(data: data) {
                    await MainActor.run {
                        cropImage = uiImage
                        showCropSheet = true
                    }
                }
                await MainActor.run { selectedPhotoItem = nil }
            }
        }
        .sheet(isPresented: $showCropSheet) {
            if let cropImage {
                PhotoCropSheet(
                    image: cropImage,
                    onConfirm: { jpeg in
                        showCropSheet = false
                        self.cropImage = nil
                        Task {
                            if let url = await onPhotoUpload?(jpeg) {
                                photos.append(url)
                            }
                        }
                    },
                    onCancel: {
                        showCropSheet = false
                        self.cropImage = nil
                    }
                )
            }
        }
        .sheet(isPresented: $showLocationPicker) {
            LocationPickerSheet(
                currentLat: LocationService.lastLat,
                currentLng: LocationService.lastLng,
                onSelect: { place in
                    locationName = place.name
                    locationAddress = place.address
                    locationLat = place.lat
                    locationLng = place.lng
                    placeId = place.id
                    onLocationUpdate?(place.name, place.address, place.lat, place.lng, place.id)
                }
            )
        }
        .alert(Lang.shared.isZh ? "删除照片" : "Delete Photo",
               isPresented: Binding(
                   get: { photoToDelete != nil },
                   set: { if !$0 { photoToDelete = nil } }
               )) {
            Button(L.cancel, role: .cancel) { photoToDelete = nil }
            Button(L.delete, role: .destructive) {
                if let url = photoToDelete {
                    photos.removeAll { $0 == url }
                    onPhotoDelete?(url)
                    photoToDelete = nil
                }
            }
        } message: {
            Text(Lang.shared.isZh ? "确定要删除这张照片吗？" : "Are you sure you want to delete this photo?")
        }
    }

    // MARK: - Photo Section

    private var photoSection: some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            Text(Lang.shared.isZh ? "照片" : "Photos")
                .font(Tokens.fontCaption.weight(.medium))
                .foregroundColor(Tokens.textTertiary)
                .padding(.leading, Tokens.spacing.xs)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Tokens.spacing.sm) {
                    ForEach(photos, id: \.self) { urlStr in
                        ZStack(alignment: .topTrailing) {
                            CachedAsyncImage(url: photoURL(urlStr)) { image in
                                image.resizable().scaledToFill()
                            } placeholder: {
                                Tokens.placeholderBg
                            }
                            .frame(width: 80, height: 80)
                            .clipped()
                            .cornerRadius(Tokens.radiusSmall)

                            Button {
                                photoToDelete = urlStr
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 18))
                                    .foregroundColor(.white)
                                    .shadow(radius: 2)
                            }
                            .offset(x: 4, y: -4)
                        }
                    }

                    // Add photo button
                    if photos.count < 4 {
                        PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                            VStack(spacing: 4) {
                                Image(systemName: "plus")
                                    .font(.system(size: 20))
                                Text(Lang.shared.isZh ? "添加" : "Add")
                                    .font(Tokens.fontCaption2)
                            }
                            .foregroundColor(Tokens.textTertiary)
                            .frame(width: 80, height: 80)
                            .background(Tokens.surface)
                            .cornerRadius(Tokens.radiusSmall)
                            .overlay(
                                RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                    .stroke(Tokens.border, style: StrokeStyle(lineWidth: 1, dash: [5]))
                            )
                        }
                    }
                }
            }
        }
    }

    private func openGoogleMaps(lat: Double, lng: Double, placeId: String?, name: String) {
        let gmapsURL = URL(string: "comgooglemaps://?q=\(lat),\(lng)")!
        if UIApplication.shared.canOpenURL(gmapsURL) {
            UIApplication.shared.open(gmapsURL)
        } else {
            var urlStr = "https://www.google.com/maps/search/?api=1&query=\(lat),\(lng)"
            if let pid = placeId, !pid.isEmpty {
                urlStr += "&query_place_id=\(pid)"
            }
            if let url = URL(string: urlStr) {
                UIApplication.shared.open(url)
            }
        }
    }

    private func photoURL(_ path: String) -> URL? {
        if path.hasPrefix("http") { return URL(string: path) }
        return APIClient.shared.avatarURL(path)
    }

    // MARK: - Form Card Components

    @ViewBuilder
    private func formCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        VStack(spacing: 0) {
            content()
        }
        .background(Tokens.surface)
        .cornerRadius(Tokens.radius)
    }

    private var cardDivider: some View {
        Rectangle()
            .fill(Tokens.divider)
            .frame(height: 0.5)
            .padding(.leading, Tokens.spacing.md)
    }

    @ViewBuilder
    private func cardField<Content: View>(label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
            Text(label)
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textTertiary)
            content()
        }
        .padding(.horizontal, Tokens.spacing.md)
        .padding(.vertical, Tokens.spacing.sm + 2)
    }

    private func categoryChip(_ c: EventCategory) -> some View {
        let selected = category == c
        return Button {
            withAnimation(.easeInOut(duration: 0.15)) { category = c }
        } label: {
            Text(c.label)
                .font(Tokens.fontSubheadline.weight(.medium))
                .foregroundColor(selected ? Tokens.accent : Tokens.textSecondary)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(selected ? Tokens.accentSoft : Tokens.surface)
                .cornerRadius(Tokens.radiusSmall)
        }
        .buttonStyle(.plain)
    }

    private static func parseEventDateTime(_ dateStr: String, _ timeStr: String?) -> Date? {
        let fmt = DateFormatter()
        if let t = timeStr, !t.isEmpty {
            fmt.dateFormat = "yyyy-MM-dd HH:mm"
            return fmt.date(from: "\(dateStr) \(t)")
        }
        fmt.dateFormat = "yyyy-MM-dd"
        return fmt.date(from: dateStr)
    }
}
