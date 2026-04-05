import SwiftUI

struct SettingsDrawer: View {
    @EnvironmentObject var auth: AuthStore
    @EnvironmentObject var petStore: PetStore
    @EnvironmentObject var calendarStore: CalendarStore
    @Binding var isPresented: Bool

    @State private var notifications = true
    @State private var medReminders = true
    @State private var weeklyInsights = false
    @State private var calendarSync = CalendarSyncService.shared.isSyncEnabled
    @State private var showCalendarSyncOptions = false
    @ObservedObject private var lang = Lang.shared
    @State private var editingPetId: String?
    @State private var showAddPet = false
    /// Set from outside to deep-link into a pet's edit page (pet_id or pet_name)
    @Binding var deepLinkPetId: String?
    @State private var showDeleteConfirm: Pet?
    @State private var showUserProfile = false

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
        .onChange(of: deepLinkPetId) { _, value in
            if let value {
                // Try matching by id first, then by name
                if let pet = petStore.pets.first(where: { $0.id == value }) {
                    editingPetId = pet.id
                } else if let pet = petStore.pets.first(where: { $0.name == value }) {
                    editingPetId = pet.id
                }
                deepLinkPetId = nil
            }
        }
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
                    Task {
                        await petStore.remove(pet.id)
                        let now = Calendar.current.dateComponents([.year, .month], from: Date())
                        await calendarStore.fetchMonth(year: now.year!, month: now.month!)
                    }
                }
            }
            Button(L.cancel, role: .cancel) { }
        }
        .confirmationDialog(L.syncToAppleCalendar, isPresented: $showCalendarSyncOptions, titleVisibility: .visible) {
            Button("Sync all history") {
                Task {
                    CalendarSyncService.shared.setSyncEnabled(true)
                    let granted = await CalendarSyncService.shared.requestAccess()
                    if granted {
                        await CalendarSyncService.shared.bulkSync(events: calendarStore.events)
                    } else {
                        calendarSync = false
                        CalendarSyncService.shared.setSyncEnabled(false)
                    }
                }
            }
            Button("Sync new events only") {
                Task {
                    CalendarSyncService.shared.setSyncEnabled(true)
                    let granted = await CalendarSyncService.shared.requestAccess()
                    if !granted {
                        calendarSync = false
                        CalendarSyncService.shared.setSyncEnabled(false)
                    }
                }
            }
            Button("Cancel", role: .cancel) {
                calendarSync = false
            }
        } message: {
            Text("Choose how to sync your pet events to the Apple Calendar app.")
        }
        .sheet(isPresented: $showUserProfile) {
            UserProfileSheet(auth: auth)
        }
    }

    // MARK: - Settings List

    private var settingsListView: some View {
        NavigationStack {
            List {
                Section {
                    Button {
                        showUserProfile = true
                    } label: {
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
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
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
                                CachedAsyncImage(url: url) { image in
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

                Section(L.calendar) {
                    Toggle(L.syncToAppleCalendar, isOn: $calendarSync)
                        .onChange(of: calendarSync) { _, newValue in
                            if newValue {
                                showCalendarSyncOptions = true
                            } else {
                                CalendarSyncService.shared.setSyncEnabled(false)
                            }
                        }
                }
                .tint(Tokens.green)
                .listRowBackground(Tokens.surface)

                Section(L.notifications) {
                    Toggle(L.pushNotifications, isOn: $notifications)
                    Toggle(L.medReminders, isOn: $medReminders)
                    Toggle(L.weeklyInsights, isOn: $weeklyInsights)
                }
                .tint(Tokens.green)
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
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.text)
                            .frame(width: Tokens.size.buttonMedium, height: Tokens.size.buttonMedium)
                            .contentShape(Rectangle())
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

}
