import SwiftUI
import PhotosUI
import StoreKit

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
    @State private var showManagePaywall = false
    @State private var showDeleteConfirm = false
    @State private var isDeleting = false

    @State private var avatarItem: PhotosPickerItem?
    @State private var pendingAvatarImage: UIImage?
    @State private var showAvatarConfirm = false
    @State private var isUploadingAvatar = false
    @State private var avatarErrorMessage: String?

    @State private var safariURL: URL?
    @State private var showDisclaimer = false
    @State private var showAcknowledgements = false

    var body: some View {
        NavigationStack {
            List {
                avatarSection
                accountSection
                subscriptionSection
                legalSection
                deleteSection
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
        .onChange(of: avatarItem) { _, newItem in
            guard let newItem else { return }
            Task {
                if let data = try? await newItem.loadTransferable(type: Data.self),
                   let image = UIImage(data: data) {
                    pendingAvatarImage = image
                    showAvatarConfirm = true
                }
            }
        }
        .fullScreenCover(isPresented: $showFamilySettings) {
            FamilySettingsView { showFamilySettings = false }
        }
        .sheet(isPresented: $showDuoPaywall) {
            PaywallSheet(isHard: false, initialDuo: true) { showDuoPaywall = false }
                .presentationDetents([.large])
                .environmentObject(subscriptionStore)
        }
        .sheet(isPresented: $showManagePaywall) {
            PaywallSheet(isHard: false) { showManagePaywall = false }
                .presentationDetents([.large])
                .environmentObject(subscriptionStore)
        }
        .sheet(item: Binding(
            get: { safariURL.map { IdentifiableURL(url: $0) } },
            set: { safariURL = $0?.url }
        )) { wrapped in
            SafariWebView(url: wrapped.url)
                .ignoresSafeArea()
        }
        .sheet(isPresented: $showDisclaimer) {
            NavigationStack {
                LegalPageView(title: L.disclaimer, content: disclaimerText)
            }
        }
        .sheet(isPresented: $showAcknowledgements) {
            NavigationStack {
                AcknowledgementsView()
            }
        }
        .alert(
            lang.isZh ? "更换头像？" : "Change Avatar?",
            isPresented: $showAvatarConfirm
        ) {
            Button(lang.isZh ? "取消" : "Cancel", role: .cancel) {
                pendingAvatarImage = nil
            }
            Button(lang.isZh ? "确认" : "Confirm") {
                guard let item = avatarItem else { return }
                Task { await uploadAvatar(from: item) }
            }
        }
        .alert(
            lang.isZh ? "确认注销账号？" : "Delete Account?",
            isPresented: $showDeleteConfirm
        ) {
            Button(lang.isZh ? "取消" : "Cancel", role: .cancel) {}
            Button(lang.isZh ? "注销" : "Delete", role: .destructive) {
                Task { await deleteAccount() }
            }
        } message: {
            Text(lang.isZh
                ? "注销后所有数据将被永久删除，包括宠物档案、聊天记录、日历事件等，且无法恢复。"
                : "All data will be permanently deleted, including pet profiles, chat history, calendar events, etc. This cannot be undone.")
        }
        .alert(
            lang.isZh ? "头像上传失败" : "Avatar Upload Failed",
            isPresented: Binding(
                get: { avatarErrorMessage != nil },
                set: { if !$0 { avatarErrorMessage = nil } }
            )
        ) {
            Button(lang.isZh ? "好" : "OK", role: .cancel) {}
        } message: {
            Text(avatarErrorMessage ?? "")
        }
        .overlay {
            if isDeleting || isUploadingAvatar {
                Tokens.dimOverlay.opacity(0.35).ignoresSafeArea()
                ProgressView()
            }
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private var avatarSection: some View {
        Section {
            VStack(spacing: Tokens.spacing.md) {
                PhotosPicker(selection: $avatarItem, matching: .images) {
                    avatarImage
                }
                .buttonStyle(.plain)

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
    }

    @ViewBuilder
    private var avatarImage: some View {
        if let image = auth.cachedAvatarImage {
            Image(uiImage: image)
                .resizable().scaledToFill()
                .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
                .clipShape(Circle())
        } else {
            fallbackAvatar
                .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
        }
    }

    private var fallbackAvatar: some View {
        Circle()
            .fill(Tokens.accent)
            .overlay(
                Text(String((auth.user?.name ?? "U").prefix(1)))
                    .foregroundColor(Tokens.white)
                    .font(.system(size: 32, weight: .semibold))
            )
    }

    @ViewBuilder
    private var accountSection: some View {
        Section(lang.isZh ? "账号信息" : "Account") {
            infoRow(icon: "envelope", label: lang.isZh ? "邮箱" : "Email", value: auth.user?.email ?? "-")
            infoRow(icon: "person.badge.key", label: lang.isZh ? "登录方式" : "Sign-in", value: providerLabel(auth.user?.provider))
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var subscriptionSection: some View {
        Section(lang.isZh ? "订阅" : "Subscription") {
            HStack {
                Label {
                    Text(lang.isZh ? "当前计划" : "Current plan")
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.text)
                } icon: {
                    Image(systemName: "crown.fill")
                        .foregroundColor(Tokens.accent)
                }
                Spacer()
                statusLabel
                    .font(Tokens.fontSubheadline)
            }

            Button {
                showManagePaywall = true
            } label: {
                HStack {
                    Label {
                        Text(lang.isZh ? "管理订阅" : "Manage Subscription")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                    } icon: {
                        Image(systemName: "creditcard")
                            .foregroundColor(Tokens.accent)
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }

        }
        .listRowBackground(Tokens.surface)

        DuoPlanSection(
            showFamilySettings: $showFamilySettings,
            showDuoPaywall: $showDuoPaywall
        )
        .environmentObject(subscriptionStore)
    }

    @ViewBuilder
    private var statusLabel: some View {
        switch subscriptionStore.status {
        case .trial(let days):
            Text("Trial · \(days)d").foregroundColor(Tokens.orange)
        case .active:
            Text(lang.isZh ? "已激活" : "Active").foregroundColor(Tokens.green)
        case .expired:
            Text(lang.isZh ? "已过期" : "Expired").foregroundColor(Tokens.red)
        case .loading:
            ProgressView().controlSize(.small)
        }
    }

    @ViewBuilder
    private var legalSection: some View {
        Section(lang.isZh ? "法律条款" : "Legal") {
            Button {
                if let url = URL(string: AppConfig.privacyPolicyURL) {
                    safariURL = url
                }
            } label: {
                legalRow(icon: "shield", title: L.privacyPolicy)
            }

            Button {
                if let url = URL(string: AppConfig.termsOfUseURL) {
                    safariURL = url
                }
            } label: {
                legalRow(icon: "doc.text", title: lang.isZh ? "使用条款" : "Terms of Use")
            }

            Button {
                showDisclaimer = true
            } label: {
                legalRow(icon: "exclamationmark.triangle", title: L.disclaimer)
            }

            Button {
                showAcknowledgements = true
            } label: {
                legalRow(icon: "heart", title: lang.isZh ? "开源致谢" : "Acknowledgements")
            }
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var deleteSection: some View {
        Section {
            Button(role: .destructive) {
                showDeleteConfirm = true
            } label: {
                HStack {
                    Spacer()
                    Label(lang.isZh ? "注销账号" : "Delete Account", systemImage: "trash")
                    Spacer()
                }
            }
            .listRowBackground(Tokens.surface)
        }

        Section {
            HStack {
                Spacer()
                Text("CozyPup \(AppConfig.versionString)")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
                Spacer()
            }
            .listRowBackground(Color.clear)
        }
    }

    // MARK: - Row builders

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

    private func legalRow(icon: String, title: String) -> some View {
        HStack {
            Label {
                Text(title)
                    .font(Tokens.fontBody)
                    .foregroundColor(Tokens.text)
            } icon: {
                Image(systemName: icon)
                    .foregroundColor(Tokens.accent)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textTertiary)
        }
    }

    // MARK: - Actions

    private func providerLabel(_ provider: String?) -> String {
        switch provider {
        case "google": return "Google"
        case "apple": return "Apple"
        case "dev": return "Dev"
        default: return provider ?? "-"
        }
    }

    private func uploadAvatar(from item: PhotosPickerItem) async {
        isUploadingAvatar = true
        defer { isUploadingAvatar = false; avatarItem = nil }

        let data: Data
        do {
            guard let loaded = try await item.loadTransferable(type: Data.self) else {
                avatarErrorMessage = lang.isZh ? "无法读取所选图片。" : "Couldn't read the selected image."
                return
            }
            data = loaded
        } catch {
            avatarErrorMessage = lang.isZh ? "无法读取所选图片。" : "Couldn't read the selected image."
            return
        }

        struct Resp: Decodable { let avatar_url: String }
        do {
            let raw = try await APIClient.shared.uploadMultipart(
                "/auth/me/avatar",
                fileData: data,
                fileName: "avatar.jpg",
                mimeType: "image/jpeg"
            )
            let resp = try JSONDecoder().decode(Resp.self, from: raw)
            auth.updateAvatarURL(resp.avatar_url)
        } catch APIError.badStatus(let code) {
            avatarErrorMessage = lang.isZh
                ? "服务器拒绝了上传（HTTP \(code)）。稍后再试。"
                : "Server rejected the upload (HTTP \(code)). Please try again later."
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain && ns.code == NSURLErrorTimedOut {
                avatarErrorMessage = lang.isZh
                    ? "上传超时。请检查网络后重试。"
                    : "Upload timed out. Check your connection and try again."
            } else {
                avatarErrorMessage = lang.isZh
                    ? "上传失败：\(ns.localizedDescription)"
                    : "Upload failed: \(ns.localizedDescription)"
            }
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
            struct UserResp: Decodable {
                let id: String
                let email: String
                let name: String?
                let avatar_url: String?
                let auth_provider: String
            }
            do {
                let resp: UserResp = try await APIClient.shared.request("PATCH", "/auth/me", body: UpdateBody(name: trimmed))
                auth.updateName(resp.name ?? trimmed)
                if let av = resp.avatar_url { auth.updateAvatarURL(av) }
            } catch {
                nameText = auth.user?.name ?? ""
            }
        }
    }

    private func deleteAccount() async {
        isDeleting = true
        struct DeleteResp: Decodable { let status: String }
        do {
            let _: DeleteResp = try await APIClient.shared.request("DELETE", "/auth/me")
            auth.logout()
            dismiss()
        } catch {
            print("[Account] delete failed: \(error)")
        }
        isDeleting = false
    }

    // MARK: - Copy

    private let disclaimerText = "CozyPup provides AI-generated suggestions for informational purposes only. These suggestions do not constitute professional veterinary advice. Always consult a qualified veterinarian for medical concerns."
}

private struct IdentifiableURL: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

#Preview {
    UserProfileSheet(auth: AuthStore())
        .environmentObject(SubscriptionStore())
}
