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
    @State private var gender = ""
    @State private var birthday = ""
    @State private var weight = ""
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var avatarImage: UIImage?
    @State private var isUploadingAvatar = false
    @State private var avatarVersion = 0  // bust AsyncImage cache after upload
    @State private var showProfileEditor = false
    @FocusState private var customSpeciesFocused: Bool
    @State private var showSpeciesConfirm = false
    @State private var showGenderConfirm = false
    @State private var pendingSpecies: Species?
    @State private var pendingGender: String?
    @State private var speciesLocked = false
    @State private var genderLocked = false

    /// Live pet from store (updates after avatar upload)
    private var currentPet: Pet? {
        if let store = petStore, let id = editingPet?.id {
            return store.getById(id)
        }
        return editingPet
    }

    private var speciesDisplayText: String {
        if !speciesDisplay.isEmpty { return speciesDisplay }
        if species == .other && !customSpecies.isEmpty { return customSpecies }
        return speciesLabel(species)
    }

    private var speciesMenuLabel: some View {
        Text(speciesDisplayText)
            .font(Tokens.fontBody)
            .foregroundColor(speciesLocked ? Tokens.textTertiary : Tokens.text)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Tokens.surface)
            .cornerRadius(12)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
    }

    private var genderMenuLabel: some View {
        Text(gender.isEmpty ? "-" : genderLabel(gender))
            .font(Tokens.fontBody)
            .foregroundColor(gender.isEmpty ? Tokens.textTertiary : (genderLocked ? Tokens.textTertiary : Tokens.text))
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Tokens.surface)
            .cornerRadius(12)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
    }

    @State private var speciesDisplay = ""

    private var allPetTypes: [(String, String, Species)] {
        let z = Lang.shared.isZh
        return [
            ("dog", z ? "狗" : "Dog", .dog),
            ("cat", z ? "猫" : "Cat", .cat),
            ("rabbit", z ? "兔子" : "Rabbit", .other),
            ("hamster", z ? "仓鼠" : "Hamster", .other),
            ("bird", z ? "鸟" : "Bird", .other),
            ("parrot", z ? "鹦鹉" : "Parrot", .other),
            ("fish", z ? "鱼" : "Fish", .other),
            ("turtle", z ? "乌龟/龟" : "Turtle", .other),
            ("snake", z ? "蛇" : "Snake", .other),
            ("lizard", z ? "蜥蜴" : "Lizard", .other),
            ("guinea_pig", z ? "豚鼠" : "Guinea Pig", .other),
            ("chinchilla", z ? "龙猫" : "Chinchilla", .other),
            ("hedgehog", z ? "刺猬" : "Hedgehog", .other),
            ("ferret", z ? "雪貂" : "Ferret", .other),
            ("duck", z ? "鸭子" : "Duck", .other),
            ("pig", z ? "猪/小香猪" : "Pig", .other),
            ("horse", z ? "马/小马" : "Horse/Pony", .other),
            ("alpaca", z ? "羊驼" : "Alpaca", .other),
            ("spider", z ? "蜘蛛" : "Spider", .other),
            ("crab", z ? "螃蟹/寄居蟹" : "Crab/Hermit Crab", .other),
        ]
    }

    private func selectSpecies(_ s: Species, display: String) {
        if editingPet != nil && !speciesLocked {
            pendingSpecies = s
            speciesDisplay = display
            showSpeciesConfirm = true
        } else if editingPet == nil {
            species = s
            speciesDisplay = display
            if display.isEmpty { customSpecies = "" }
            else { customSpecies = display }
        }
    }

    private func confirmSpecies(_ s: Species) {
        if editingPet != nil && !speciesLocked {
            pendingSpecies = s
            showSpeciesConfirm = true
        } else {
            species = s
        }
    }

    private func confirmGender(_ g: String) {
        if editingPet != nil && !genderLocked {
            pendingGender = g
            showGenderConfirm = true
        } else {
            gender = g
        }
    }

    private func genderLabel(_ g: String) -> String {
        let isZh = Lang.shared.isZh
        switch g {
        case "male": return isZh ? "公 ♂" : "Male ♂"
        case "female": return isZh ? "母 ♀" : "Female ♀"
        default: return isZh ? "未知" : "Unknown"
        }
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

            // Row 2: Species + Gender
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L.species).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                    Menu {
                        ForEach(allPetTypes, id: \.0) { key, label, sp in
                            Button(label) { selectSpecies(sp, display: label) }
                        }
                    } label: {
                        speciesMenuLabel
                    }
                    .disabled(speciesLocked)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text(Lang.shared.isZh ? "性别" : "Gender")
                        .font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                    Menu {
                        Button(genderLabel("male")) { confirmGender("male") }
                        Button(genderLabel("female")) { confirmGender("female") }
                    } label: {
                        genderMenuLabel
                    }
                    .disabled(genderLocked)
                }
            }

            // Row 3: Breed
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

            // Row 4: Birthday + Weight
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L.birthday).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                    TextField("YYYY-MM-DD", text: $birthday)
                        .keyboardType(.numbersAndPunctuation)
                        .autocorrectionDisabled()
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
                // Save gender separately if editing
                if let pet = editingPet, let store = petStore, !gender.isEmpty {
                    Task { await store.updateGender(pet.id, gender: gender) }
                }
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
        .onTapGesture { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
        .onAppear {
            if let pet = editingPet {
                name = pet.name
                species = pet.species
                breed = pet.breed
                birthday = pet.birthday ?? ""
                weight = pet.weight.map { String($0) } ?? ""
                gender = pet.gender ?? ""
                speciesLocked = pet.speciesLocked ?? false
                genderLocked = !(pet.gender ?? "").isEmpty
                // Set display text for species
                if pet.species == .dog { speciesDisplay = L.dog }
                else if pet.species == .cat { speciesDisplay = L.cat }
                else if !pet.breed.isEmpty { speciesDisplay = pet.breed }
                else { speciesDisplay = L.other }
            }
        }
        .alert(
            Lang.shared.isZh ? "确认类型" : "Confirm Species",
            isPresented: $showSpeciesConfirm
        ) {
            Button(Lang.shared.isZh ? "确认（不可再改）" : "Confirm (cannot change later)") {
                if let s = pendingSpecies, let pet = editingPet, let store = petStore {
                    species = s
                    if !speciesDisplay.isEmpty && s == .other {
                        customSpecies = speciesDisplay
                    }
                    speciesLocked = true
                    Task { await store.update(pet.id, name: name, species: s, breed: breed,
                                              birthday: birthday.isEmpty ? nil : birthday,
                                              weight: Double(weight)) }
                }
            }
            Button(L.cancel, role: .cancel) { pendingSpecies = nil }
        } message: {
            Text(Lang.shared.isZh
                 ? "类型设置后将无法修改，请确认选择。"
                 : "Species cannot be changed after this. Please confirm.")
        }
        .alert(
            Lang.shared.isZh ? "确认性别" : "Confirm Gender",
            isPresented: $showGenderConfirm
        ) {
            Button(Lang.shared.isZh ? "确认（不可再改）" : "Confirm (cannot change later)") {
                if let g = pendingGender, let pet = editingPet, let store = petStore {
                    gender = g
                    genderLocked = true
                    Task { await store.updateGender(pet.id, gender: g) }
                }
            }
            Button(L.cancel, role: .cancel) { pendingGender = nil }
        } message: {
            Text(Lang.shared.isZh
                 ? "性别设置后将无法修改，请确认选择。"
                 : "Gender cannot be changed after this. Please confirm.")
        }
    }
}
