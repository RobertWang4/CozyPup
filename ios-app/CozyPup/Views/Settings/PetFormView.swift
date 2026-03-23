import SwiftUI
import PhotosUI

struct PetFormView: View {
    var editingPet: Pet?
    var petStore: PetStore?
    var onSave: (String, Species, String, String?, Double?) -> Void
    var onCancel: (() -> Void)?

    @State private var name = ""
    @State private var species: Species = .dog
    @State private var customSpecies = ""
    @State private var breed = ""
    @State private var birthday = ""
    @State private var weight = ""
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var avatarImage: UIImage?
    @State private var isUploadingAvatar = false
    @State private var avatarVersion = 0  // bust AsyncImage cache after upload
    @State private var showProfileEditor = false
    @FocusState private var customSpeciesFocused: Bool

    /// Live pet from store (updates after avatar upload)
    private var currentPet: Pet? {
        if let store = petStore, let id = editingPet?.id {
            return store.getById(id)
        }
        return editingPet
    }

    private func speciesLabel(_ s: Species) -> String {
        if s == .other && !customSpecies.isEmpty { return customSpecies }
        switch s {
        case .dog: return L.dog
        case .cat: return L.cat
        case .other: return L.other
        }
    }

    private var avatarColor: Color {
        if let pet = editingPet { return pet.color }
        return petColors[0]
    }

    var body: some View {
        VStack(spacing: Tokens.spacing.md) {
            // Avatar
            PhotosPicker(selection: $selectedPhoto, matching: .images) {
                ZStack {
                    if let avatarImage {
                        Image(uiImage: avatarImage)
                            .resizable()
                            .scaledToFill()
                            .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
                            .clipShape(Circle())
                    } else if let pet = currentPet, !pet.avatarUrl.isEmpty,
                              let baseURL = APIClient.shared.avatarURL(pet.avatarUrl) {
                        // Append version to bust AsyncImage cache after upload
                        let url = URL(string: "\(baseURL.absoluteString)?v=\(avatarVersion)")!
                        AsyncImage(url: url) { image in
                            image.resizable().scaledToFill()
                        } placeholder: {
                            Circle().fill(avatarColor.opacity(0.15))
                        }
                        .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
                        .clipShape(Circle())
                    } else {
                        Circle()
                            .fill(avatarColor.opacity(0.15))
                            .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
                        Image(systemName: species == .cat ? "cat.fill" : "dog.fill")
                            .font(.system(size: 34))
                            .foregroundColor(avatarColor)
                    }

                    // Camera badge
                    VStack {
                        Spacer()
                        HStack {
                            Spacer()
                            ZStack {
                                Circle()
                                    .fill(Tokens.accent)
                                    .frame(width: 24, height: 24)
                                Image(systemName: isUploadingAvatar ? "arrow.triangle.2.circlepath" : "camera.fill")
                                    .font(.system(size: 11))
                                    .foregroundColor(Tokens.white)
                            }
                        }
                    }
                    .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
                }
            }
            .onChange(of: selectedPhoto) { _, newItem in
                guard let newItem else { return }
                Task {
                    if let data = try? await newItem.loadTransferable(type: Data.self),
                       let uiImage = UIImage(data: data) {
                        avatarImage = uiImage
                        // Upload immediately if editing existing pet
                        if let pet = editingPet, let store = petStore {
                            if let jpegData = uiImage.jpegData(compressionQuality: 0.8) {
                                isUploadingAvatar = true
                                await store.uploadAvatar(pet.id, imageData: jpegData)
                                isUploadingAvatar = false
                                avatarVersion += 1
                            }
                        }
                    }
                }
            }
            .padding(.bottom, Tokens.spacing.xs)

            VStack(alignment: .leading, spacing: 6) {
                Text(L.name).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                TextField(L.namePlaceholder, text: $name)
                    .textFieldStyle(.plain)
                    .foregroundColor(Tokens.text)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(L.species).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                HStack(spacing: 10) {
                    ForEach(Species.allCases, id: \.self) { s in
                        Button {
                            species = s
                            if s == .other { customSpeciesFocused = true }
                        } label: {
                            Text(speciesLabel(s))
                                .font(Tokens.fontSubheadline.weight(.medium))
                                .padding(.horizontal, Tokens.spacing.md)
                                .padding(.vertical, Tokens.spacing.sm)
                                .background(species == s ? Tokens.accent : Tokens.surface)
                                .foregroundColor(species == s ? Tokens.white : Tokens.text)
                                .cornerRadius(20)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 20)
                                        .stroke(species == s ? Color.clear : Tokens.border)
                                )
                        }
                    }
                }
                if species == .other {
                    TextField(Lang.shared.isZh ? "输入宠物类型，如：兔子、仓鼠" : "e.g. Rabbit, Hamster", text: $customSpecies)
                        .focused($customSpeciesFocused)
                        .textFieldStyle(.plain)
                        .font(Tokens.fontSubheadline)
                        .padding(10)
                        .background(Tokens.surface)
                        .cornerRadius(10)
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Tokens.border))
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(L.breed).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                TextField(L.breedPlaceholder, text: $breed)
                    .textFieldStyle(.plain)
                    .foregroundColor(Tokens.text)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L.birthday).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                    TextField("YYYY-MM-DD", text: $birthday)
                        .textFieldStyle(.plain)
                        .foregroundColor(Tokens.text)
                        .padding(12)
                        .background(Tokens.surface)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text(L.weightKg).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                    TextField("0.0", text: $weight)
                        .keyboardType(.decimalPad)
                        .textFieldStyle(.plain)
                        .foregroundColor(Tokens.text)
                        .padding(12)
                        .background(Tokens.surface)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
            }

            // Profile MD card
            if let pet = editingPet {
                Button { showProfileEditor = true } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 6) {
                                Image(systemName: "doc.text.fill")
                                    .foregroundColor(Tokens.accent)
                                Text(Lang.shared.isZh ? "宠物档案" : "Pet Profile")
                                    .font(Tokens.fontSubheadline.weight(.medium))
                                    .foregroundColor(Tokens.text)
                            }
                            Text(pet.profileMd != nil
                                 ? (Lang.shared.isZh ? "AI 已生成，点击查看或编辑" : "AI generated — tap to view or edit")
                                 : (Lang.shared.isZh ? "AI 会在聊天中自动生成" : "AI will generate during chats"))
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                    .padding(Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
                .buttonStyle(.plain)
                .sheet(isPresented: $showProfileEditor) {
                    if let store = petStore {
                        PetProfileEditor(pet: pet, petStore: store, isPresented: $showProfileEditor)
                    }
                }
            }

            Button {
                Haptics.light()
                let bday = birthday.isEmpty ? nil : birthday
                let w = Double(weight)
                onSave(name, species, breed, bday, w)
            } label: {
                Text(editingPet != nil ? L.saveChanges : L.addPet)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(name.isEmpty ? Tokens.border : Tokens.accent)
                    .foregroundColor(Tokens.white)
                    .cornerRadius(14)
                    .font(Tokens.fontCallout.weight(.semibold))
            }
            .disabled(name.isEmpty)

            if let onCancel {
                Button(L.cancel) { onCancel() }
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .onAppear {
            if let pet = editingPet {
                name = pet.name
                species = pet.species
                breed = pet.breed
                birthday = pet.birthday ?? ""
                weight = pet.weight.map { String($0) } ?? ""
            }
        }
    }
}
