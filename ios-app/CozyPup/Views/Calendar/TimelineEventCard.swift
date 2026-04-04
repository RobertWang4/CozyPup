import SwiftUI
import PhotosUI

struct TimelineEventCard: View {
    let event: CalendarEvent
    let petColor: Color
    let petName: String
    var allowPhotoUpload: Bool = false
    var onUpdate: ((String, EventCategory, String, String?, Double?) -> Void)?
    var onDelete: (() -> Void)?
    var onPhotoUpload: ((Data) async -> String?)?
    var onPhotoDelete: ((String) -> Void)?
    var onLocationUpdate: ((String, String, Double, Double, String) -> Void)?
    var onLocationRemove: (() -> Void)?

    @State private var showEditSheet = false
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var cropImage: UIImage?
    @State private var showCropSheet = false
    @State private var fullScreenImage: UIImage?

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                // Left accent bar
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(categoryColor)
                    .frame(width: 3)
                    .padding(.vertical, 12)

                VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
                    // Header: category + time
                    HStack {
                        Text(event.category.label.uppercased())
                            .font(Tokens.fontCaption2.weight(.medium))
                            .foregroundColor(categoryColor)
                            .tracking(0.5)
                        Spacer()
                        if let time = event.eventTime {
                            Text(time)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                    }

                    // Title + cost
                    HStack(spacing: Tokens.spacing.xs) {
                        Text(event.title)
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.text)
                            .lineLimit(3)
                        if let cost = event.cost, cost > 0 {
                            Spacer()
                            Text("¥\(Int(cost))")
                                .font(Tokens.fontSubheadline.weight(.semibold))
                                .foregroundColor(Tokens.accent)
                        }
                    }

                    // Photos moved outside padding below

                // Location
                if let locName = event.locationName, let lat = event.locationLat, let lng = event.locationLng {
                    Button {
                        openGoogleMaps(lat: lat, lng: lng, placeId: event.placeId, name: locName)
                    } label: {
                        HStack(spacing: Tokens.spacing.xs) {
                            Image(systemName: "mappin.circle.fill")
                                .foregroundColor(Tokens.accent)
                                .font(.system(size: 14))
                            Text(locName)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.accent)
                                .lineLimit(1)
                        }
                    }
                }

                // Bottom row: pet name + add photo
                HStack {
                    Text(petName)
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)

                    Spacer()

                    if allowPhotoUpload {
                        PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                            HStack(spacing: 3) {
                                Image(systemName: "camera.fill")
                                    .font(.system(size: 10))
                                Text(Lang.shared.isZh ? "添加照片" : "Add Photo")
                                    .font(Tokens.fontCaption2)
                            }
                            .foregroundColor(Tokens.accent)
                        }
                    }
                }
            }
            .padding(.leading, 12)
            .padding(.vertical, 14)
            .padding(.trailing, Tokens.spacing.md)
        }

            // Photos — edge-to-edge inside card
            if !event.photos.isEmpty {
                photoGrid
                    .padding(.horizontal, Tokens.spacing.sm)
                    .padding(.bottom, Tokens.spacing.sm)
            }
        }
        .background(Tokens.surface)
        .cornerRadius(14)
        .contextMenu {
            if onUpdate != nil {
                Button {
                    showEditSheet = true
                } label: {
                    Label(Lang.shared.isZh ? "编辑" : "Edit", systemImage: "pencil")
                }
            }
            if let onDelete {
                Button(role: .destructive) { Haptics.medium(); onDelete() } label: {
                    Label(L.delete, systemImage: "trash")
                }
            }
        }
        .sheet(isPresented: $showEditSheet) {
            if let onUpdate {
                EventEditSheet(event: event, onSave: onUpdate, onPhotoUpload: onPhotoUpload, onPhotoDelete: onPhotoDelete, onLocationUpdate: onLocationUpdate, onLocationRemove: onLocationRemove)
            }
        }
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
                        Task { _ = await onPhotoUpload?(jpeg) }
                    },
                    onCancel: {
                        showCropSheet = false
                        self.cropImage = nil
                    }
                )
            }
        }
    }

    // MARK: - Photo Grid

    private var photoGrid: some View {
        VStack(spacing: Tokens.spacing.xs) {
            if event.photos.count == 1 {
                // Single photo: full width, aspect fill
                CachedAsyncImage(url: photoURL(event.photos[0])) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    Tokens.placeholderBg
                }
                .frame(maxWidth: .infinity)
                .frame(height: 200)
                .clipped()
                .cornerRadius(Tokens.radiusSmall)
                .contentShape(Rectangle())
                .onTapGesture { loadFullScreenImage(from: event.photos[0]) }
            } else if event.photos.count == 2 {
                HStack(spacing: Tokens.spacing.xs) {
                    ForEach(event.photos, id: \.self) { urlStr in
                        photoItem(urlStr)
                            .frame(maxWidth: .infinity)
                            .frame(height: 140)
                            .clipped()
                            .cornerRadius(Tokens.radiusSmall)
                    }
                }
            } else {
                let columns = [GridItem(.flexible(), spacing: Tokens.spacing.xs), GridItem(.flexible(), spacing: Tokens.spacing.xs)]
                LazyVGrid(columns: columns, spacing: Tokens.spacing.xs) {
                    ForEach(event.photos, id: \.self) { urlStr in
                        photoItem(urlStr)
                            .frame(height: 120)
                            .clipped()
                            .cornerRadius(Tokens.radiusSmall)
                    }
                }
            }
        }
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
    }

    @ViewBuilder
    private func photoItem(_ urlStr: String) -> some View {
        CachedAsyncImage(url: photoURL(urlStr)) { image in
            image.resizable().scaledToFill()
        } placeholder: {
            Tokens.placeholderBg
        }
        .contentShape(Rectangle())
        .onTapGesture {
            loadFullScreenImage(from: urlStr)
        }
    }

    private func loadFullScreenImage(from urlStr: String) {
        guard let url = photoURL(urlStr) else { return }
        Task {
            if let (data, _) = try? await URLSession.shared.data(from: url),
               let uiImage = UIImage(data: data) {
                await MainActor.run { fullScreenImage = uiImage }
            }
        }
    }

    private func photoURL(_ path: String) -> URL? {
        if path.hasPrefix("http") { return URL(string: path) }
        return APIClient.shared.avatarURL(path)
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

    private var categoryColor: Color {
        switch event.category {
        case .daily: return Tokens.accent
        case .diet: return Tokens.green
        case .medical: return Tokens.blue
        case .abnormal: return Tokens.red
        }
    }
}

#Preview("Diet Event") {
    TimelineEventCard(
        event: CalendarEvent(petId: "p1", eventDate: "2026-04-01", eventTime: "08:30", title: "吃了狗粮200g，胃口不错", type: .log, category: .diet, rawText: "", source: .chat),
        petColor: Color(hex: "E8835C"),
        petName: "豆豆"
    )
    .padding()
    .background(Tokens.bg)
}

#Preview("Medical Event") {
    TimelineEventCard(
        event: CalendarEvent(petId: "p1", eventDate: "2026-04-01", eventTime: "14:00", title: "狂犬疫苗第二针", type: .appointment, category: .medical, rawText: "", source: .chat),
        petColor: Color(hex: "6BA3BE"),
        petName: "豆豆"
    )
    .padding()
    .background(Tokens.bg)
}
