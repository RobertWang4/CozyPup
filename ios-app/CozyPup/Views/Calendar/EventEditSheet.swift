import SwiftUI
import PhotosUI

struct EventEditSheet: View {
    let event: CalendarEvent
    var onSave: (String, EventCategory, String, String?) -> Void
    var onPhotoUpload: ((Data) async -> String?)?  // returns photo URL on success
    var onPhotoDelete: ((String) -> Void)?
    @Environment(\.dismiss) private var dismiss

    @State private var title: String
    @State private var category: EventCategory
    @State private var date: String
    @State private var time: String
    @State private var photos: [String]
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var cropImage: UIImage?
    @State private var showCropSheet = false
    @State private var photoToDelete: String?

    init(event: CalendarEvent, onSave: @escaping (String, EventCategory, String, String?) -> Void, onPhotoUpload: ((Data) async -> String?)? = nil, onPhotoDelete: ((String) -> Void)? = nil) {
        self.event = event
        self.onSave = onSave
        self.onPhotoUpload = onPhotoUpload
        self.onPhotoDelete = onPhotoDelete
        _title = State(initialValue: event.title)
        _category = State(initialValue: event.category)
        _date = State(initialValue: event.eventDate)
        _time = State(initialValue: event.eventTime ?? "")
        _photos = State(initialValue: event.photos)
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
                                    Button {
                                        withAnimation(.easeInOut(duration: 0.15)) {
                                            category = c
                                        }
                                    } label: {
                                        Text(c.label)
                                            .font(Tokens.fontSubheadline.weight(.medium))
                                            .foregroundColor(category == c ? Tokens.accent : Tokens.textSecondary)
                                            .padding(.horizontal, 14)
                                            .padding(.vertical, 8)
                                            .background(
                                                category == c ? Tokens.accentSoft : Tokens.surface
                                            )
                                            .cornerRadius(Tokens.radiusSmall)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }

                    // Card 3: Photos
                    photoSection

                    // Card 4: Location
                    if let locName = event.locationName, let lat = event.locationLat, let lng = event.locationLng {
                        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                            Text(Lang.shared.isZh ? "地点" : "Location")
                                .font(Tokens.fontCaption.weight(.medium))
                                .foregroundColor(Tokens.textTertiary)
                                .padding(.leading, Tokens.spacing.xs)

                            HStack {
                                Button {
                                    openGoogleMaps(lat: lat, lng: lng, placeId: event.placeId, name: locName)
                                } label: {
                                    HStack(spacing: Tokens.spacing.xs) {
                                        Image(systemName: "mappin.circle.fill")
                                            .foregroundColor(Tokens.accent)
                                        Text(locName)
                                            .font(Tokens.fontBody)
                                            .foregroundColor(Tokens.accent)
                                        if let addr = event.locationAddress, !addr.isEmpty {
                                            Text(addr)
                                                .font(Tokens.fontCaption)
                                                .foregroundColor(Tokens.textSecondary)
                                                .lineLimit(1)
                                        }
                                    }
                                }
                                Spacer()
                            }
                            .padding(Tokens.spacing.md)
                            .background(Tokens.surface)
                            .cornerRadius(Tokens.radius)
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
                        onSave(title, category, date, time.isEmpty ? nil : time)
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
                            AsyncImage(url: photoURL(urlStr)) { image in
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
}
