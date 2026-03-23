import SwiftUI

struct SettingsDrawer: View {
    @EnvironmentObject var auth: AuthStore
    @EnvironmentObject var petStore: PetStore
    @Binding var isPresented: Bool

    @State private var notifications = true
    @State private var medReminders = true
    @State private var weeklyInsights = false
    @ObservedObject private var lang = Lang.shared
    @State private var editingPetId: String?
    @State private var showAddPet = false
    @State private var showDeleteConfirm: Pet?

    private let prefsKey = "cozypup_notification_prefs"

    private enum Page { case list, editPet, addPet }
    private var currentPage: Page {
        if editingPetId != nil { return .editPet }
        if showAddPet { return .addPet }
        return .list
    }

    var body: some View {
        ZStack {
            Tokens.bg.ignoresSafeArea()

            switch currentPage {
            case .list:
                settingsListView
                    .transition(.move(edge: .leading))
            case .editPet:
                if let pet = petStore.pets.first(where: { $0.id == editingPetId }) {
                    petFormPage(pet: pet, title: L.editPet)
                        .transition(.move(edge: .trailing))
                }
            case .addPet:
                petFormPage(pet: nil, title: L.addPet)
                    .transition(.move(edge: .trailing))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: currentPage == .list)
        .onAppear { loadPrefs() }
        .task { await petStore.fetchFromAPI() }
        .onChange(of: notifications) { savePrefs() }
        .onChange(of: medReminders) { savePrefs() }
        .onChange(of: weeklyInsights) { savePrefs() }
        .alert(L.deletePet, isPresented: Binding(
            get: { showDeleteConfirm != nil },
            set: { if !$0 { showDeleteConfirm = nil } }
        )) {
            Button(L.delete, role: .destructive) {
                if let pet = showDeleteConfirm {
                    Task { await petStore.remove(pet.id) }
                }
            }
            Button(L.cancel, role: .cancel) { }
        }
    }

    // MARK: - Settings List

    private var settingsListView: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 12) {
                        Circle()
                            .fill(Tokens.accent)
                            .frame(width: Tokens.size.avatarMedium, height: Tokens.size.avatarMedium)
                            .overlay(
                                Text(String(auth.user?.name.prefix(1) ?? "U"))
                                    .foregroundColor(Tokens.white)
                                    .font(Tokens.fontHeadline.weight(.semibold))
                            )
                        VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                            Text(auth.user?.name ?? "User")
                                .font(Tokens.fontCallout.weight(.medium))
                                .foregroundColor(Tokens.text)
                            Text(auth.user?.email ?? "")
                                .font(Tokens.fontSubheadline)
                                .foregroundColor(Tokens.textSecondary)
                        }
                    }
                    .listRowBackground(Tokens.surface)
                }

                Section(L.myPets) {
                    ForEach(petStore.pets) { pet in
                        HStack(spacing: 12) {
                            if !pet.avatarUrl.isEmpty,
                               let baseURL = APIClient.shared.avatarURL(pet.avatarUrl),
                               let url = URL(string: "\(baseURL.absoluteString)?v=\(petStore.avatarRevision)") {
                                AsyncImage(url: url) { image in
                                    image.resizable().scaledToFill()
                                } placeholder: {
                                    Image(systemName: pet.species == .cat ? "cat" : "dog")
                                        .font(Tokens.fontTitle)
                                        .foregroundColor(pet.color)
                                }
                                .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                                .clipShape(Circle())
                            } else {
                                Image(systemName: pet.species == .cat ? "cat" : "dog")
                                    .font(Tokens.fontTitle)
                                    .foregroundColor(pet.color)
                                    .frame(width: Tokens.size.avatarSmall)
                            }
                            VStack(alignment: .leading, spacing: 3) {
                                HStack(spacing: 6) {
                                    Text(pet.name).font(Tokens.fontBody.weight(.medium))
                                    if !pet.breed.isEmpty {
                                        Text(pet.breed)
                                            .font(Tokens.fontCaption)
                                            .foregroundColor(Tokens.textSecondary)
                                    }
                                }
                                HStack(spacing: Tokens.spacing.sm) {
                                    if let birthday = pet.birthday {
                                        Label(petAge(birthday), systemImage: "birthday.cake")
                                            .font(Tokens.fontCaption)
                                            .foregroundColor(Tokens.textTertiary)
                                    }
                                    if let weight = pet.weight {
                                        Label(String(format: "%.1fkg", weight), systemImage: "scalemass")
                                            .font(Tokens.fontCaption)
                                            .foregroundColor(Tokens.textTertiary)
                                    }
                                }
                            }
                            Spacer()
                            Button {
                                withAnimation { editingPetId = pet.id }
                            } label: {
                                Image(systemName: "pencil")
                                    .font(Tokens.fontSubheadline)
                                    .foregroundColor(Tokens.textSecondary)
                                    .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                            }
                            .buttonStyle(.borderless)
                            Button {
                                showDeleteConfirm = pet
                            } label: {
                                Image(systemName: "trash")
                                    .font(Tokens.fontSubheadline)
                                    .foregroundColor(Tokens.red)
                                    .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                            }
                            .buttonStyle(.borderless)
                        }
                        .listRowBackground(Tokens.surface)
                    }
                    Button {
                        withAnimation { showAddPet = true }
                    } label: {
                        Label(L.addPet, systemImage: "plus")
                            .font(Tokens.fontSubheadline.weight(.medium))
                            .foregroundColor(Tokens.accent)
                    }
                    .listRowBackground(Tokens.surface)
                }

                Section(L.language) {
                    Picker(L.responseLang, selection: $lang.code) {
                        Text("中文").tag("zh")
                        Text("English").tag("en")
                    }
                    .tint(Tokens.textSecondary)
                }
                .listRowBackground(Tokens.surface)

                Section(L.notifications) {
                    Toggle(L.pushNotifications, isOn: $notifications)
                    Toggle(L.medReminders, isOn: $medReminders)
                    Toggle(L.weeklyInsights, isOn: $weeklyInsights)
                }
                .tint(Tokens.green)
                .listRowBackground(Tokens.surface)

                Section {
                    NavigationLink { LegalPageView(title: L.privacyPolicy, content: privacyText) } label: {
                        Label(L.privacyPolicy, systemImage: "shield")
                    }
                    NavigationLink { LegalPageView(title: L.disclaimer, content: disclaimerText) } label: {
                        Label(L.disclaimer, systemImage: "doc.text")
                    }
                    NavigationLink { LegalPageView(title: L.about, content: aboutText) } label: {
                        Label(L.about, systemImage: "info.circle")
                    }
                }
                .listRowBackground(Tokens.surface)

                Section {
                    Button(role: .destructive) {
                        Haptics.medium()
                        auth.logout()
                        withAnimation(.easeInOut(duration: 0.3)) { isPresented = false }
                    } label: {
                        Label(L.logOut, systemImage: "rectangle.portrait.and.arrow.right")
                    }
                    .listRowBackground(Tokens.surface)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Tokens.bg)
            .foregroundColor(Tokens.text)
            .navigationTitle(L.settings)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
        }
    }

    // MARK: - Pet Form Page

    private func petFormPage(pet: Pet?, title: String) -> some View {
        NavigationStack {
            ScrollView {
                Spacer().frame(height: 40)
                PetFormView(editingPet: pet, petStore: petStore, onSave: { name, species, breed, birthday, weight in
                    Task {
                        if let pet = pet {
                            await petStore.update(pet.id, name: name, species: species, breed: breed,
                                                  birthday: birthday, weight: weight)
                        } else {
                            await petStore.add(name: name, species: species, breed: breed,
                                               birthday: birthday, weight: weight)
                        }
                    }
                    withAnimation {
                        editingPetId = nil
                        showAddPet = false
                    }
                }, onCancel: {
                    withAnimation {
                        editingPetId = nil
                        showAddPet = false
                    }
                })
                .padding(20)
            }
            .background(Tokens.bg)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        withAnimation {
                            editingPetId = nil
                            showAddPet = false
                        }
                    } label: {
                        Image(systemName: "chevron.left")
                            .font(Tokens.fontSubheadline.weight(.semibold))
                            .foregroundColor(Tokens.textSecondary)
                    }
                }
            }
        }
    }

    // MARK: - Helpers

    private func loadPrefs() {
        if let data = UserDefaults.standard.data(forKey: prefsKey),
           let prefs = try? JSONDecoder().decode([String: Bool].self, from: data) {
            notifications = prefs["notifications"] ?? true
            medReminders = prefs["medReminders"] ?? true
            weeklyInsights = prefs["weeklyInsights"] ?? false
        }
    }

    private func savePrefs() {
        let prefs = ["notifications": notifications, "medReminders": medReminders, "weeklyInsights": weeklyInsights]
        if let data = try? JSONEncoder().encode(prefs) {
            UserDefaults.standard.set(data, forKey: prefsKey)
        }
    }

    private func petAge(_ birthday: String) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let born = f.date(from: birthday) else { return birthday }
        let months = Calendar.current.dateComponents([.month], from: born, to: Date()).month ?? 0
        if months < 12 {
            return "\(months)mo"
        }
        let years = months / 12
        let rem = months % 12
        return rem > 0 ? "\(years)y\(rem)mo" : "\(years)y"
    }

    private let privacyText = "CozyPup values your privacy. We only collect data necessary to provide personalized pet health suggestions. Your data is stored locally on your device and is not shared with third parties."
    private let disclaimerText = "CozyPup provides AI-generated suggestions for informational purposes only. These suggestions do not constitute professional veterinary advice. Always consult a qualified veterinarian for medical concerns."
    private let aboutText = "CozyPup v1.0\n\nYour pet's personal health butler, powered by AI.\n\nBuilt with love for pet parents everywhere. 🐾"
}
