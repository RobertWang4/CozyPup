import SwiftUI

struct UserProfileSheet: View {
    @ObservedObject var auth: AuthStore
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    @ObservedObject private var lang = Lang.shared
    @Environment(\.dismiss) private var dismiss

    @State private var editingName = false
    @State private var nameText = ""
    @FocusState private var nameFocused: Bool
    @State private var showFamilySettings = false
    @State private var showDuoPaywall = false

    var body: some View {
        NavigationStack {
            List {
                // Avatar + name
                Section {
                    VStack(spacing: Tokens.spacing.md) {
                        Circle()
                            .fill(Tokens.accent)
                            .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
                            .overlay(
                                Text(String(nameText.prefix(1).isEmpty ? "U" : nameText.prefix(1)))
                                    .foregroundColor(Tokens.white)
                                    .font(.system(size: 32, weight: .semibold))
                            )

                        if editingName {
                            TextField(lang.isZh ? "输入名字" : "Enter name", text: $nameText)
                                .font(Tokens.fontTitle.weight(.semibold))
                                .foregroundColor(Tokens.text)
                                .multilineTextAlignment(.center)
                                .focused($nameFocused)
                                .onSubmit { saveName() }
                        } else {
                            Button {
                                editingName = true
                                nameFocused = true
                            } label: {
                                HStack(spacing: Tokens.spacing.xs) {
                                    Text(auth.user?.name ?? "User")
                                        .font(Tokens.fontTitle.weight(.semibold))
                                        .foregroundColor(Tokens.text)
                                    Image(systemName: "pencil")
                                        .font(Tokens.fontCaption)
                                        .foregroundColor(Tokens.textTertiary)
                                }
                            }
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Tokens.spacing.md)
                    .listRowBackground(Color.clear)
                }

                // Account info
                Section(lang.isZh ? "账号信息" : "Account") {
                    infoRow(icon: "envelope", label: lang.isZh ? "邮箱" : "Email", value: auth.user?.email ?? "-")
                    infoRow(icon: "person.badge.key", label: lang.isZh ? "登录方式" : "Sign-in", value: providerLabel(auth.user?.provider))
                }
                .listRowBackground(Tokens.surface)

                // Duo Plan — opens family settings or paywall based on status
                Section {
                    Button {
                        if subscriptionStore.isDuo {
                            showFamilySettings = true
                        } else {
                            showDuoPaywall = true
                        }
                    } label: {
                        HStack {
                            Label {
                                Text("Duo Plan")
                                    .font(Tokens.fontBody)
                                    .foregroundColor(Tokens.text)
                            } icon: {
                                Image(systemName: "person.2.fill")
                                    .foregroundColor(Tokens.accent)
                            }
                            Spacer()
                            if !subscriptionStore.isDuo {
                                Text("Upgrade")
                                    .font(Tokens.fontCaption)
                                    .foregroundColor(Tokens.accent)
                            }
                            Image(systemName: "chevron.right")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                    }
                }
                .listRowBackground(Tokens.surface)

                // Legal
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

                // Logout
                Section {
                    Button(role: .destructive) {
                        Haptics.medium()
                        auth.logout()
                        dismiss()
                    } label: {
                        HStack {
                            Spacer()
                            Label(L.logOut, systemImage: "rectangle.portrait.and.arrow.right")
                            Spacer()
                        }
                    }
                    .listRowBackground(Tokens.surface)
                }

                // Version
                Section {
                    HStack {
                        Spacer()
                        Text("CozyPup v1.0")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                        Spacer()
                    }
                    .listRowBackground(Color.clear)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Tokens.bg)
            .foregroundColor(Tokens.text)
            .navigationTitle(lang.isZh ? "个人信息" : "Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .tint(Tokens.text)
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .presentationBackground(Tokens.bg)
        .onAppear { nameText = auth.user?.name ?? "" }
        .fullScreenCover(isPresented: $showFamilySettings) {
            FamilySettingsView {
                showFamilySettings = false
            }
        }
        .sheet(isPresented: $showDuoPaywall) {
            PaywallSheet(isHard: false, initialDuo: true) { showDuoPaywall = false }
                .presentationDetents([.large])
                .environmentObject(subscriptionStore)
        }
    }

    private func saveName() {
        let trimmed = nameText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed != auth.user?.name else {
            editingName = false
            return
        }
        editingName = false
        Task {
            struct UpdateBody: Encodable { let name: String }
            struct UserResp: Decodable { let id: String; let email: String; let name: String?; let auth_provider: String }
            do {
                let resp: UserResp = try await APIClient.shared.request("PATCH", "/auth/me", body: UpdateBody(name: trimmed))
                let updated = UserInfo(name: resp.name ?? trimmed, email: resp.email, provider: resp.auth_provider)
                auth.user = updated
                if let data = try? JSONEncoder().encode(updated) {
                    UserDefaults.standard.set(data, forKey: "cozypup_auth")
                }
            } catch {
                nameText = auth.user?.name ?? ""
            }
        }
    }

    private func infoRow(icon: String, label: String, value: String) -> some View {
        HStack {
            Label(label, systemImage: icon)
                .font(Tokens.fontBody)
                .foregroundColor(Tokens.text)
            Spacer()
            Text(value)
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)
        }
    }

    private func providerLabel(_ provider: String?) -> String {
        switch provider {
        case "google": return "Google"
        case "apple": return "Apple"
        case "dev": return "Dev"
        default: return provider ?? "-"
        }
    }

    private let privacyText = "CozyPup values your privacy. We only collect data necessary to provide personalized pet health suggestions. Your data is stored locally on your device and is not shared with third parties."
    private let disclaimerText = "CozyPup provides AI-generated suggestions for informational purposes only. These suggestions do not constitute professional veterinary advice. Always consult a qualified veterinarian for medical concerns."
    private let aboutText = "CozyPup v1.0\n\nYour pet's personal health butler, powered by AI.\n\nBuilt with love for pet parents everywhere. 🐾"
}
