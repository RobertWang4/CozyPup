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

    @State private var showEditSheet = false
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var cropImage: UIImage?
    @State private var showCropSheet = false

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
                EventEditSheet(event: event, onSave: onUpdate, onPhotoUpload: onPhotoUpload, onPhotoDelete: onPhotoDelete)
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
                        AsyncImage(url: photoURL(urlStr)) { image in
                            image.resizable().scaledToFill()
                        } placeholder: {
                            Tokens.placeholderBg
                        }
                        .frame(width: 72, height: 72)
                        .clipped()
                        .cornerRadius(Tokens.radiusSmall)

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
    }

    private func photoURL(_ path: String) -> URL? {
        if path.hasPrefix("http") { return URL(string: path) }
        return APIClient.shared.avatarURL(path)
    }

    private var categoryColor: Color {
        switch event.category {
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
