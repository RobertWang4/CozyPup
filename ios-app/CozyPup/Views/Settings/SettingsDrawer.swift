import SwiftUI

struct SettingsDrawer: View {
    @EnvironmentObject var auth: AuthStore
    @EnvironmentObject var petStore: PetStore
    @Binding var isPresented: Bool

    @State private var notifications = true
    @State private var medReminders = true
    @State private var weeklyInsights = false
    @State private var editingPet: Pet?
    @State private var showAddPet = false
    @State private var showDeleteConfirm: Pet?

    private let prefsKey = "cozypup_notification_prefs"

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 12) {
                        Circle()
                            .fill(Tokens.accent)
                            .frame(width: 44, height: 44)
                            .overlay(
                                Text(String(auth.user?.name.prefix(1) ?? "U"))
                                    .foregroundColor(.white)
                                    .font(.system(size: 18, weight: .semibold))
                            )
                        VStack(alignment: .leading, spacing: 2) {
                            Text(auth.user?.name ?? "User")
                                .font(.system(size: 16, weight: .medium))
                                .foregroundColor(Tokens.text)
                            Text(auth.user?.email ?? "")
                                .font(.system(size: 13))
                                .foregroundColor(Tokens.textSecondary)
                        }
                    }
                    .listRowBackground(Tokens.surface)
                }

                Section("My Pets") {
                    ForEach(petStore.pets) { pet in
                        HStack(spacing: 12) {
                            Image(systemName: pet.species == .cat ? "cat" : "dog")
                                .foregroundColor(pet.color)
                            VStack(alignment: .leading) {
                                Text(pet.name).font(.system(size: 15, weight: .medium))
                                Text(pet.breed).font(.system(size: 12)).foregroundColor(Tokens.textSecondary)
                            }
                            Spacer()
                            Button { editingPet = pet } label: {
                                Image(systemName: "pencil")
                                    .font(.system(size: 13))
                                    .foregroundColor(Tokens.textSecondary)
                            }
                            Button { showDeleteConfirm = pet } label: {
                                Image(systemName: "trash")
                                    .font(.system(size: 13))
                                    .foregroundColor(Tokens.red)
                            }
                        }
                        .listRowBackground(Tokens.surface)
                    }
                    Button { showAddPet = true } label: {
                        Label("Add Pet", systemImage: "plus")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(Tokens.accent)
                    }
                    .listRowBackground(Tokens.surface)
                }

                Section("Notifications") {
                    Toggle("Push Notifications", isOn: $notifications)
                    Toggle("Medication Reminders", isOn: $medReminders)
                    Toggle("Weekly Insights", isOn: $weeklyInsights)
                }
                .tint(Tokens.green)
                .listRowBackground(Tokens.surface)

                Section {
                    NavigationLink { LegalPageView(title: "Privacy Policy", content: privacyText) } label: {
                        Label("Privacy Policy", systemImage: "shield")
                    }
                    NavigationLink { LegalPageView(title: "Disclaimer", content: disclaimerText) } label: {
                        Label("Disclaimer", systemImage: "doc.text")
                    }
                    NavigationLink { LegalPageView(title: "About", content: aboutText) } label: {
                        Label("About", systemImage: "info.circle")
                    }
                }
                .listRowBackground(Tokens.surface)

                Section {
                    Button(role: .destructive) {
                        Haptics.medium()
                        auth.logout()
                        withAnimation(.easeInOut(duration: 0.3)) { isPresented = false }
                    } label: {
                        Label("Log Out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                    .listRowBackground(Tokens.surface)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Tokens.bg)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { withAnimation(.easeInOut(duration: 0.3)) { isPresented = false } } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Tokens.textSecondary)
                            .frame(width: 32, height: 32)
                            .background(Tokens.surface)
                            .cornerRadius(10)
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Tokens.border))
                    }
                }
            }
            .sheet(item: $editingPet) { pet in
                NavigationStack {
                    PetFormView(editingPet: pet) { name, species, breed, birthday, weight in
                        Task {
                            await petStore.update(pet.id, name: name, species: species, breed: breed,
                                                  birthday: birthday, weight: weight)
                        }
                        editingPet = nil
                    } onCancel: {
                        editingPet = nil
                    }
                    .padding(20)
                    .navigationTitle("Edit Pet")
                    .navigationBarTitleDisplayMode(.inline)
                }
            }
            .sheet(isPresented: $showAddPet) {
                NavigationStack {
                    PetFormView { name, species, breed, birthday, weight in
                        Task {
                            await petStore.add(name: name, species: species, breed: breed,
                                               birthday: birthday, weight: weight)
                        }
                        showAddPet = false
                    } onCancel: {
                        showAddPet = false
                    }
                    .padding(20)
                    .navigationTitle("Add Pet")
                    .navigationBarTitleDisplayMode(.inline)
                }
            }
            .alert("Delete Pet?", isPresented: Binding(
                get: { showDeleteConfirm != nil },
                set: { if !$0 { showDeleteConfirm = nil } }
            )) {
                Button("Delete", role: .destructive) {
                    if let pet = showDeleteConfirm {
                        Task { await petStore.remove(pet.id) }
                    }
                }
                Button("Cancel", role: .cancel) { }
            }
        }
        .onAppear { loadPrefs() }
        .onChange(of: notifications) { savePrefs() }
        .onChange(of: medReminders) { savePrefs() }
        .onChange(of: weeklyInsights) { savePrefs() }
    }

    private func loadPrefs() {
        guard let data = UserDefaults.standard.data(forKey: prefsKey),
              let prefs = try? JSONDecoder().decode([String: Bool].self, from: data) else { return }
        notifications = prefs["notifications"] ?? true
        medReminders = prefs["medReminders"] ?? true
        weeklyInsights = prefs["weeklyInsights"] ?? false
    }

    private func savePrefs() {
        let prefs = ["notifications": notifications, "medReminders": medReminders, "weeklyInsights": weeklyInsights]
        if let data = try? JSONEncoder().encode(prefs) {
            UserDefaults.standard.set(data, forKey: prefsKey)
        }
    }

    private let privacyText = "CozyPup values your privacy. We only collect data necessary to provide personalized pet health suggestions. Your data is stored locally on your device and is not shared with third parties."
    private let disclaimerText = "CozyPup provides AI-generated suggestions for informational purposes only. These suggestions do not constitute professional veterinary advice. Always consult a qualified veterinarian for medical concerns."
    private let aboutText = "CozyPup v1.0\n\nYour pet's personal health butler, powered by AI.\n\nBuilt with love for pet parents everywhere. 🐾"
}
