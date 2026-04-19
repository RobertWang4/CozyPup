import SwiftUI
import StoreKit

struct SettingsDrawer: View {
    @EnvironmentObject var auth: AuthStore
    @EnvironmentObject var petStore: PetStore
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    @Binding var isPresented: Bool

    @State private var calendarSync = CalendarSyncService.shared.isSyncEnabled
    @State private var showWhatsNew = false
    @State private var showShareSheet = false
    @State private var showFAQ = false
    @State private var pendingExternalMessage: String = ""
    @State private var pendingExternalAction: (() -> Void)?
    @State private var showCalendarSyncOptions = false
    @ObservedObject private var lang = Lang.shared
    @State private var editingPetId: String?
    @State private var showAddPet = false
    /// Set from outside to deep-link into a pet's edit page (pet_id or pet_name)
    @Binding var deepLinkPetId: String?
    @State private var showDeleteConfirm: Pet?
    @State private var showUserProfile = false
    @State private var showPaywall = false
    @State private var showScanner = false
    @State private var scannedToken: String?
    @State private var showMergeSheet = false
    @State private var scanAlertTitle: String?
    @State private var scanAlertMessage: String?
    @State private var showPetShareSheet: Pet?
    @State private var showPetUnshareSheet: Pet?

    private enum Page: Equatable { case list, editPet, addPet }
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
                    PetDetailView(petId: pet.id, onClose: {
                        withAnimation { editingPetId = nil }
                    })
                    .transition(.move(edge: .trailing))
                }
            case .addPet:
                petFormPage(pet: nil, title: L.addPet)
                    .transition(.move(edge: .trailing))
            }
        }
        .animation(.easeInOut(duration: 0.3), value: currentPage)
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
                .environmentObject(subscriptionStore)
        }
        .sheet(isPresented: $showPaywall) {
            PaywallSheet(isHard: false) { showPaywall = false }
                .presentationDetents([.large])
                .environmentObject(subscriptionStore)
        }
        .fullScreenCover(isPresented: $showScanner) {
            PetShareScannerSheet { payload in
                showScanner = false
                // Dispatch based on what we just scanned.
                if let token = parsePetShareToken(payload) {
                    scannedToken = token
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                        showMergeSheet = true
                    }
                } else if let inviteId = parseFamilyInviteId(payload) {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                        Task { await acceptFamilyInvite(inviteId: inviteId) }
                    }
                } else {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                        scanAlertTitle = Lang.shared.isZh ? "无法识别的二维码" : "Unrecognized QR"
                        scanAlertMessage = Lang.shared.isZh
                            ? "这个二维码不是 CozyPup 的邀请码。"
                            : "This QR code isn't a CozyPup invite."
                    }
                }
            }
        }
        .alert(
            scanAlertTitle ?? "",
            isPresented: Binding(
                get: { scanAlertTitle != nil },
                set: { if !$0 { scanAlertTitle = nil; scanAlertMessage = nil } }
            )
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(scanAlertMessage ?? "")
        }
        .sheet(isPresented: $showMergeSheet) {
            if let token = scannedToken {
                PetMergeSheet(shareToken: token) {
                    showMergeSheet = false
                    scannedToken = nil
                }
                .environmentObject(petStore)
                .presentationDetents([.medium, .large])
            }
        }
        .fullScreenCover(item: $showPetShareSheet) { pet in
            PetShareSheet(pet: pet, onDismiss: {
                showPetShareSheet = nil
            })
        }
        .sheet(item: $showPetUnshareSheet) { pet in
            PetUnshareSheet(petId: pet.id, petName: pet.name, onDone: {
                showPetUnshareSheet = nil
                Task {
                    await petStore.fetchFromAPI()
                    withAnimation { editingPetId = nil }
                }
            })
            .presentationDetents([.medium])
        }
    }

    // MARK: - QR payload parsing

    /// Extract the pet-share token from the legacy `cozypup://share?token=...` QR.
    private func parsePetShareToken(_ payload: String) -> String? {
        guard let url = URL(string: payload),
              url.scheme == "cozypup",
              url.host == "share",
              let token = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                  .queryItems?.first(where: { $0.name == "token" })?.value
        else { return nil }
        return token
    }

    /// Extract the invite id from a family invite landing URL, e.g.
    /// `https://backend-.../invite/{uuid}`.
    private func parseFamilyInviteId(_ payload: String) -> String? {
        guard let url = URL(string: payload) else { return nil }
        let comps = url.pathComponents  // ["/", "invite", "{id}"]
        guard comps.count >= 3, comps[comps.count - 2] == "invite" else { return nil }
        let last = comps[comps.count - 1]
        // Validate it's a UUID (rough check)
        guard UUID(uuidString: last) != nil else { return nil }
        return last
    }

    @MainActor
    private func acceptFamilyInvite(inviteId: String) async {
        struct Body: Encodable { let invite_id: String }
        struct Resp: Decodable { let status: String }
        do {
            let _: Resp = try await APIClient.shared.request(
                "POST", "/family/accept", body: Body(invite_id: inviteId)
            )
            scanAlertTitle = Lang.shared.isZh ? "已加入！" : "Joined!"
            scanAlertMessage = Lang.shared.isZh
                ? "你已接受邀请,现在可以和对方共享宠物档案了。"
                : "You've joined the Duo plan. You can now share pet care with your partner."
            await subscriptionStore.loadStatus()
        } catch {
            scanAlertTitle = Lang.shared.isZh ? "接受失败" : "Couldn't accept"
            scanAlertMessage = Lang.shared.isZh
                ? "邀请可能已过期或已被使用,请让对方重新生成一个。"
                : "The invite may be expired or already used. Ask your partner to generate a new one."
        }
    }

    // MARK: - Settings List

    private var settingsListView: some View {
        NavigationStack {
            List {
                profileCardSection
                myPetsSection
                preferencesSection
                notificationsSection
                supportSection
                aboutSection
                logOutSection
            }
            .scrollContentBackground(.hidden)
            .background(Tokens.bg)
            .foregroundColor(Tokens.text)
            .navigationTitle(L.settings)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showScanner = true
                    } label: {
                        Image(systemName: "qrcode.viewfinder")
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.text)
                            .frame(width: Tokens.size.buttonMedium, height: Tokens.size.buttonMedium)
                            .contentShape(Rectangle())
                    }
                }
            }
            .sheet(isPresented: $showWhatsNew) {
                NavigationStack { WhatsNewView() }
            }
            .sheet(isPresented: $showFAQ) {
                NavigationStack { FAQView() }
            }
            .alert(
                lang.isZh ? "离开 CozyPup？" : "Leave CozyPup?",
                isPresented: Binding(
                    get: { pendingExternalAction != nil },
                    set: { if !$0 { pendingExternalAction = nil } }
                )
            ) {
                Button(lang.isZh ? "取消" : "Cancel", role: .cancel) {
                    pendingExternalAction = nil
                }
                Button(lang.isZh ? "继续" : "Continue") {
                    let action = pendingExternalAction
                    pendingExternalAction = nil
                    action?()
                }
            } message: {
                Text(pendingExternalMessage)
            }
            .sheet(isPresented: $showShareSheet) {
                if let url = URL(string: AppConfig.appStoreURL) {
                    ShareSheet(items: [url])
                }
            }
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private var profileCardSection: some View {
        Section {
            Button {
                showUserProfile = true
            } label: {
                HStack(spacing: 12) {
                    if let image = auth.cachedAvatarImage {
                        Image(uiImage: image)
                            .resizable().scaledToFill()
                            .frame(width: Tokens.size.avatarMedium, height: Tokens.size.avatarMedium)
                            .clipShape(Circle())
                    } else {
                        Circle()
                            .fill(Tokens.accent)
                            .frame(width: Tokens.size.avatarMedium, height: Tokens.size.avatarMedium)
                            .overlay(
                                Text(String(auth.user?.name.prefix(1) ?? "U"))
                                    .foregroundColor(Tokens.white)
                                    .font(Tokens.fontHeadline.weight(.semibold))
                            )
                    }
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
    }

    @ViewBuilder
    private var myPetsSection: some View {
        Section(L.myPets) {
            ForEach(petStore.pets) { pet in
                petRow(pet)
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
    }

    @ViewBuilder
    private func petRow(_ pet: Pet) -> some View {
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

    @ViewBuilder
    private var preferencesSection: some View {
        Section(lang.isZh ? "偏好" : "Preferences") {
            Picker(L.responseLang, selection: $lang.code) {
                Text("中文").tag("zh")
                Text("English").tag("en")
            }
            .tint(Tokens.textSecondary)

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
    }

    @ViewBuilder
    private var notificationsSection: some View {
        Section(L.notifications) {
            Button {
                requestExternal(
                    message: lang.isZh
                        ? "将跳转到系统「设置」的 CozyPup 通知页面。"
                        : "You'll be taken to iOS Settings to manage CozyPup notifications."
                ) {
                    if let url = URL(string: UIApplication.openNotificationSettingsURLString) {
                        UIApplication.shared.open(url)
                    }
                }
            } label: {
                HStack {
                    Label {
                        Text(L.pushNotifications)
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                    } icon: {
                        Image(systemName: "bell")
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
    }

    @ViewBuilder
    private var supportSection: some View {
        Section(lang.isZh ? "支持" : "Support") {
            Button {
                showFAQ = true
            } label: {
                supportRow(icon: "questionmark.circle", title: lang.isZh ? "常见问题" : "FAQ")
            }

            Button {
                requestExternal(
                    message: lang.isZh
                        ? "将跳转到「邮件」发送给 \(AppConfig.supportEmail)。"
                        : "You'll be taken to Mail to contact \(AppConfig.supportEmail)."
                ) {
                    openMail(to: AppConfig.supportEmail, subject: "CozyPup Support")
                }
            } label: {
                supportRow(icon: "envelope", title: lang.isZh ? "联系我们" : "Contact Support")
            }

            Button {
                requestExternal(
                    message: lang.isZh
                        ? "将跳转到「邮件」发送反馈给 \(AppConfig.supportEmail)，邮件中会包含当前版本和设备信息。"
                        : "You'll be taken to Mail to send feedback to \(AppConfig.supportEmail). The message will include your app version and device info."
                ) {
                    let subject = "[Report] CozyPup \(AppConfig.versionString)"
                    let body = "Device: \(UIDevice.current.model)\niOS: \(UIDevice.current.systemVersion)\n\n"
                    openMail(to: AppConfig.supportEmail, subject: subject, body: body)
                }
            } label: {
                supportRow(icon: "exclamationmark.bubble", title: lang.isZh ? "反馈问题" : "Report a Problem")
            }

            Button {
                if let scene = UIApplication.shared.connectedScenes
                    .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene {
                    SKStoreReviewController.requestReview(in: scene)
                }
            } label: {
                supportRow(icon: "star", title: lang.isZh ? "给 CozyPup 评分" : "Rate CozyPup")
            }

            if AppConfig.isShareEnabled {
                Button {
                    showShareSheet = true
                } label: {
                    supportRow(icon: "square.and.arrow.up", title: lang.isZh ? "分享 CozyPup" : "Share CozyPup")
                }
            }
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var aboutSection: some View {
        Section(lang.isZh ? "关于" : "About") {
            Button {
                showWhatsNew = true
            } label: {
                supportRow(icon: "sparkles", title: lang.isZh ? "更新说明" : "What's New")
            }

            HStack {
                Label {
                    Text(lang.isZh ? "版本" : "Version")
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.text)
                } icon: {
                    Image(systemName: "info.circle")
                        .foregroundColor(Tokens.accent)
                }
                Spacer()
                Text(AppConfig.versionString)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .listRowBackground(Tokens.surface)
    }

    @ViewBuilder
    private var logOutSection: some View {
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

    // MARK: - Helpers

    private func supportRow(icon: String, title: String) -> some View {
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

    private func requestExternal(message: String, action: @escaping () -> Void) {
        pendingExternalMessage = message
        pendingExternalAction = action
    }

    private func openMail(to: String, subject: String, body: String = "") {
        var components = URLComponents()
        components.scheme = "mailto"
        components.path = to
        var items: [URLQueryItem] = [URLQueryItem(name: "subject", value: subject)]
        if !body.isEmpty { items.append(URLQueryItem(name: "body", value: body)) }
        components.queryItems = items
        if let url = components.url {
            UIApplication.shared.open(url)
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
                // Share / Leave button on top-right when editing an existing pet
                if let pet = pet {
                    ToolbarItem(placement: .topBarTrailing) {
                        if pet.isCoOwned == true {
                            Button {
                                showPetUnshareSheet = pet
                            } label: {
                                Image(systemName: "person.2.slash")
                                    .font(Tokens.fontBody.weight(.semibold))
                                    .foregroundColor(Tokens.red)
                                    .frame(width: Tokens.size.buttonMedium, height: Tokens.size.buttonMedium)
                                    .contentShape(Rectangle())
                            }
                        } else {
                            Button {
                                showPetShareSheet = pet
                            } label: {
                                Image(systemName: "qrcode")
                                    .font(Tokens.fontBody.weight(.semibold))
                                    .foregroundColor(Tokens.accent)
                                    .frame(width: Tokens.size.buttonMedium, height: Tokens.size.buttonMedium)
                                    .contentShape(Rectangle())
                            }
                        }
                    }
                }
            }
        }
    }

}
