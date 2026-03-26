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
                VStack(alignment: .leading, spacing: Tokens.spacing.md) {
                    field(label: L.title) {
                        TextField(L.title, text: $title)
                            .textFieldStyle(.plain)
                            .foregroundColor(Tokens.text)
                    }

                    HStack(spacing: 12) {
                        field(label: L.date) {
                            TextField("YYYY-MM-DD", text: $date)
                                .textFieldStyle(.plain)
                                .foregroundColor(Tokens.text)
                        }
                        field(label: L.time) {
                            TextField("HH:MM", text: $time)
                                .textFieldStyle(.plain)
                                .foregroundColor(Tokens.text)
                        }
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text(Lang.shared.isZh ? "分类" : "Category")
                            .font(Tokens.fontSubheadline.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(EventCategory.allCases, id: \.self) { c in
                                    Button {
                                        category = c
                                    } label: {
                                        Text(c.label)
                                            .font(Tokens.fontCaption.weight(.medium))
                                            .padding(.horizontal, 12)
                                            .padding(.vertical, 6)
                                            .background(category == c ? Tokens.accent : Tokens.surface)
                                            .foregroundColor(category == c ? Tokens.white : Tokens.text)
                                            .cornerRadius(16)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 16)
                                                    .stroke(category == c ? Color.clear : Tokens.border)
                                            )
                                    }
                                }
                            }
                        }
                    }

                    // Photos section
                    photoSection
                }
                .padding(Tokens.spacing.md)
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
        VStack(alignment: .leading, spacing: 6) {
            Text(Lang.shared.isZh ? "照片" : "Photos")
                .font(Tokens.fontSubheadline.weight(.medium))
                .foregroundColor(Tokens.textSecondary)

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

    private func photoURL(_ path: String) -> URL? {
        if path.hasPrefix("http") { return URL(string: path) }
        return APIClient.shared.avatarURL(path)
    }

    @ViewBuilder
    private func field(label: String, @ViewBuilder content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(Tokens.fontSubheadline.weight(.medium))
                .foregroundColor(Tokens.textSecondary)
            content()
                .padding(12)
                .background(Tokens.surface)
                .cornerRadius(12)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
        }
    }
}
