import SwiftUI
import PhotosUI

struct TimelineEventCard: View {
    let event: CalendarEvent
    let petColor: Color
    let petName: String
    var allowPhotoUpload: Bool = false
    var onUpdate: ((String, EventCategory, String, String?) -> Void)?
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

                // Title
                Text(event.title)
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.text)
                    .lineLimit(3)

                // Photo grid
                if !event.photos.isEmpty {
                    photoGrid
                }

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
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Tokens.spacing.xs) {
                ForEach(event.photos, id: \.self) { urlStr in
                    ZStack(alignment: .topTrailing) {
                        CachedAsyncImage(url: photoURL(urlStr)) { image in
                            image.resizable().scaledToFill()
                        } placeholder: {
                            Tokens.placeholderBg
                        }
                        .frame(width: 72, height: 72)
                        .clipped()
                        .cornerRadius(Tokens.radiusSmall)
                        .onTapGesture {
                            loadFullScreenImage(from: urlStr)
                        }

                        if onPhotoDelete != nil {
                            Button {
                                onPhotoDelete?(urlStr)
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 16))
                                    .foregroundColor(.white)
                                    .shadow(radius: 2)
                            }
                            .offset(x: 4, y: -4)
                        }
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
