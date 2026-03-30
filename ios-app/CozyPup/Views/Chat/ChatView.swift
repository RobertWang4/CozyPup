import SwiftUI

struct ChatView: View {
    @EnvironmentObject var chatStore: ChatStore
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @EnvironmentObject var dailyTaskStore: DailyTaskStore
    @StateObject private var speech = SpeechService()
    @StateObject private var location = LocationService()

    @State private var inputText = ""
    @State private var isStreaming = false
    @State private var emergency: EmergencyData?
    @State private var showCalendar = false
    @State private var showSettings = false
    @State private var showCalendarSyncOptions = false
    @State private var settingsDeepLinkPetId: String?
    @State private var calendarDrag: CGFloat = 0
    @State private var settingsDrag: CGFloat = 0
    @State private var voiceDragOffset: CGFloat = 0
    @State private var pendingPhotos: [Data] = []
    @State private var voiceDetectedLanguage: String?
    @State private var scrollOffset: CGFloat = 0
    @State private var contentHeight: CGFloat = 0
    @State private var containerHeight: CGFloat = 0
    @State private var fullScreenImage: UIImage?
    @State private var showDailyTasks = false
    @State private var showTaskManager = false
    @State private var showSlashMenu = false

    private var drawerWidth: CGFloat { UIScreen.main.bounds.width * 0.90 }

    private var calendarX: CGFloat {
        let base: CGFloat = showCalendar ? 0 : -drawerWidth
        return min(0, max(-drawerWidth, base + calendarDrag))
    }

    private var settingsX: CGFloat {
        let base: CGFloat = showSettings ? 0 : drawerWidth
        return max(0, min(drawerWidth, base + settingsDrag))
    }

    private var drawerProgress: CGFloat {
        let calP = (calendarX + drawerWidth) / drawerWidth
        let setP = (drawerWidth - settingsX) / drawerWidth
        return max(calP, setP)
    }

    var body: some View {
        ZStack {
            // Main content
            VStack(spacing: 0) {
                header

                if let emergency {
                    EmergencyBanner(
                        onFind: { self.emergency = nil },
                        onDismiss: { self.emergency = nil }
                    )
                }

                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(spacing: 0) {
                            if chatStore.messages.isEmpty {
                                if petStore.pets.isEmpty {
                                    EmptyStateView(
                                        icon: "pawprint.fill",
                                        title: L.welcomeTitle,
                                        subtitle: L.welcomeSubtitle
                                    )
                                    .frame(minHeight: 400)
                                } else {
                                    EmptyStateView(
                                        icon: "bubble.left.and.bubble.right",
                                        title: L.askAnything,
                                        subtitle: L.askSubtitle
                                    )
                                    .frame(minHeight: 400)
                                }
                            }
                            VStack(spacing: 10) {
                                ForEach(chatStore.messages) { msg in
                                    VStack(spacing: Tokens.spacing.sm) {
                                        if let photos = msg.imageData, !photos.isEmpty {
                                            HStack {
                                                if msg.role == .user { Spacer() }
                                                photoGrid(photos)
                                                if msg.role != .user { Spacer() }
                                            }
                                        }
                                        if !msg.content.isEmpty {
                                            ChatBubble(role: msg.role, content: msg.content)
                                        }
                                        ForEach(Array(msg.cards.enumerated()), id: \.offset) { _, card in
                                            cardView(card)
                                        }
                                    }
                                }
                                if isStreaming, let last = chatStore.messages.last, last.content.isEmpty {
                                    TypingIndicator()
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 12)
                            Color.clear.frame(height: 1).id("bottom")
                        }
                        .background(GeometryReader { geo in
                            Color.clear.onChange(of: geo.size.height, initial: true) { _, h in
                                contentHeight = h
                            }
                            .onChange(of: geo.frame(in: .named("chatScroll")).minY, initial: true) { _, y in
                                scrollOffset = y
                            }
                        })
                    }
                    .coordinateSpace(name: "chatScroll")
                    .scrollIndicators(.hidden)
                    .scrollDismissesKeyboard(.interactively)
                    .onTapGesture {
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    }
                    .onChange(of: chatStore.messages.count) {
                        withAnimation { proxy.scrollTo("bottom") }
                    }
                    .background(GeometryReader { geo in
                        Color.clear.onChange(of: geo.size.height, initial: true) { _, h in
                            containerHeight = h
                        }
                    })
                    .modifier(ScrollIndicatorOverlay(
                        contentHeight: contentHeight,
                        containerHeight: containerHeight,
                        scrollOffset: scrollOffset,
                        onScrub: { progress in
                            let messages = chatStore.messages
                            guard !messages.isEmpty else { return }
                            let idx = min(Int(progress * CGFloat(messages.count)), messages.count - 1)
                            proxy.scrollTo(messages[idx].id, anchor: .top)
                        }
                    ))
                }

                Text(L.aiDisclaimer)
                    .font(Tokens.fontCaption2)
                    .foregroundColor(Tokens.textTertiary)
                    .padding(.vertical, 2)

                // Slash command menu
                if showSlashMenu {
                    SlashCommandMenu(onSelect: { command in
                        handleSlashCommand(command)
                    })
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                ChatInputBar(
                    text: $inputText,
                    pendingPhotos: $pendingPhotos,
                    isStreaming: isStreaming,
                    isListening: speech.isListening,
                    transcript: speech.transcript,
                    audioLevel: speech.audioLevel,
                    onSend: sendMessage,
                    onMicDown: startVoice,
                    onMicUp: releaseVoice,
                    onMicCancel: cancelVoice,
                    dragOffsetOut: $voiceDragOffset
                )
                .allowsHitTesting(!showSettings && !showCalendar)
                // Hide input bar when drawer is open so keyboard doesn't push it up
                .frame(height: (showSettings || showCalendar) ? 0 : nil)
                .clipped()
                .onChange(of: inputText) { _, newValue in
                    withAnimation(.easeOut(duration: 0.15)) {
                        showSlashMenu = newValue == "/"
                    }
                }
            }
            .background(Tokens.bg.ignoresSafeArea())

            // Daily task popover
            if showDailyTasks {
                Color.black.opacity(0.001)
                    .ignoresSafeArea()
                    .onTapGesture {
                        withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
                            showDailyTasks = false
                        }
                    }
                    .transition(.opacity)
                    .zIndex(9)
            }

            VStack {
                DailyTaskPopover(isPresented: $showDailyTasks)
                    .environmentObject(dailyTaskStore)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, Tokens.spacing.lg)
                    .padding(.top, 60)
                    .opacity(showDailyTasks ? 1 : 0)
                    .scaleEffect(showDailyTasks ? 1 : 0.9, anchor: .top)
                    .offset(y: showDailyTasks ? 0 : -10)
                    .animation(.spring(response: 0.35, dampingFraction: 0.85), value: showDailyTasks)
                Spacer()
            }
            .allowsHitTesting(showDailyTasks)
            .zIndex(10)
        }
        .overlay {
            if speech.isListening {
                VoiceRecordingOverlay(
                    transcript: speech.transcript,
                    audioLevel: speech.audioLevel,
                    dragOffset: voiceDragOffset,
                    cancelThreshold: -120
                )
                .transition(.asymmetric(
                    insertion: .scale(scale: 0.3, anchor: .bottom).combined(with: .opacity),
                    removal: .scale(scale: 0.5, anchor: .bottom).combined(with: .opacity)
                ))
                .animation(.spring(response: 0.4, dampingFraction: 0.75), value: speech.isListening)
            }
        }
        // 1. Edge swipe areas
        .overlay {
            HStack(spacing: 0) {
                Color.clear.frame(width: Tokens.size.iconSmall)
                    .contentShape(Rectangle())
                    .gesture(edgeOpenGesture(isCalendar: true))
                Spacer()
                Color.clear.frame(width: Tokens.size.iconSmall)
                    .contentShape(Rectangle())
                    .gesture(edgeOpenGesture(isCalendar: false))
            }
            .ignoresSafeArea()
        }
        // 2. Dimming overlay (covers edge areas when drawer is open)
        .overlay {
            Tokens.dimOverlay.opacity(Double(drawerProgress) * 0.3)
                .ignoresSafeArea()
                .allowsHitTesting(showCalendar || showSettings)
                .onTapGesture { closeDrawers() }
                .gesture(overlayCloseDrag)
        }
        // Timeline drawer (left)
        .overlay(alignment: .leading) {
            CalendarDrawer(isPresented: $showCalendar)
                .frame(width: drawerWidth)
                .frame(maxHeight: .infinity)
                .background(Tokens.bg)
                .clipShape(UnevenRoundedRectangle(bottomTrailingRadius: 20, topTrailingRadius: 20))
                .shadow(color: Tokens.dimOverlay.opacity(drawerProgress > 0.01 ? 0.15 : 0), radius: 10, x: 2)
                .offset(x: calendarX)
                .ignoresSafeArea()
                .gesture(calendarDrawerCloseDrag)
        }
        // Settings drawer (right)
        .overlay(alignment: .trailing) {
            SettingsDrawer(isPresented: $showSettings, deepLinkPetId: $settingsDeepLinkPetId)
                .frame(width: drawerWidth)
                .frame(maxHeight: .infinity)
                .background(Tokens.bg)
                .clipShape(UnevenRoundedRectangle(topLeadingRadius: 20, bottomLeadingRadius: 20))
                .shadow(color: Tokens.dimOverlay.opacity(drawerProgress > 0.01 ? 0.15 : 0), radius: 10, x: -2)
                .offset(x: settingsX)
                .ignoresSafeArea()
                .gesture(settingsDrawerCloseDrag)
        }
        .onChange(of: showCalendar) { _, val in
            if !val { calendarDrag = 0 }
        }
        .onChange(of: showSettings) { _, val in
            if !val {
                settingsDrag = 0
                settingsDeepLinkPetId = nil
            }
        }
        .fullScreenCover(isPresented: Binding(
            get: { fullScreenImage != nil },
            set: { if !$0 { fullScreenImage = nil } }
        )) {
            if let img = fullScreenImage {
                FullScreenImageViewer(image: img) {
                    fullScreenImage = nil
                }
                .ignoresSafeArea()
                .presentationBackground(.clear)
            }
        }
        .sheet(isPresented: $showTaskManager) {
            DailyTaskManagerSheet()
                .environmentObject(dailyTaskStore)
                .environmentObject(petStore)
        }
        .confirmationDialog("Sync to Apple Calendar", isPresented: $showCalendarSyncOptions, titleVisibility: .visible) {
            Button(Lang.shared.isZh ? "同步所有历史事件" : "Sync all history") {
                Task {
                    CalendarSyncService.shared.setSyncEnabled(true)
                    let granted = await CalendarSyncService.shared.requestAccess()
                    if granted {
                        await CalendarSyncService.shared.bulkSync(events: calendarStore.events)
                    }
                }
            }
            Button(Lang.shared.isZh ? "仅同步新事件" : "Sync new events only") {
                Task {
                    CalendarSyncService.shared.setSyncEnabled(true)
                    _ = await CalendarSyncService.shared.requestAccess()
                }
            }
            Button(Lang.shared.isZh ? "不连接" : "Don't connect", role: .cancel) {}
        } message: {
            Text(Lang.shared.isZh ? "选择如何同步宠物事件到 Apple 日历" : "Choose how to sync pet events to Apple Calendar")
        }
        .task {
            await petStore.fetchFromAPI()
            await location.requestLocation()
        }
        .task {
            await dailyTaskStore.fetchToday()
        }
    }

    // MARK: - Drawer Gestures

    private func edgeOpenGesture(isCalendar: Bool) -> some Gesture {
        DragGesture(minimumDistance: 10)
            .onChanged { value in
                dismissKeyboard()
                if isCalendar {
                    calendarDrag = max(0, value.translation.width)
                } else {
                    settingsDrag = min(0, value.translation.width)
                }
            }
            .onEnded { value in
                let threshold = drawerWidth * 0.3
                if isCalendar {
                    if value.translation.width > threshold ||
                       value.predictedEndTranslation.width > drawerWidth * 0.5 {
                        withAnimation(.easeOut(duration: 0.25)) {
                            showCalendar = true; calendarDrag = 0
                        }
                    } else {
                        withAnimation(.easeOut(duration: 0.2)) { calendarDrag = 0 }
                    }
                } else {
                    if value.translation.width < -threshold ||
                       value.predictedEndTranslation.width < -drawerWidth * 0.5 {
                        withAnimation(.easeOut(duration: 0.25)) {
                            showSettings = true; settingsDrag = 0
                        }
                    } else {
                        withAnimation(.easeOut(duration: 0.2)) { settingsDrag = 0 }
                    }
                }
            }
    }

    private var overlayCloseDrag: some Gesture {
        DragGesture(minimumDistance: 20)
            .onChanged { value in
                if showCalendar {
                    calendarDrag = min(0, value.translation.width)
                } else if showSettings {
                    settingsDrag = max(0, value.translation.width)
                }
            }
            .onEnded { value in
                let threshold = drawerWidth * 0.3
                if showCalendar {
                    if value.translation.width < -threshold ||
                       value.predictedEndTranslation.width < -drawerWidth * 0.5 {
                        withAnimation(.easeOut(duration: 0.25)) {
                            showCalendar = false; calendarDrag = 0
                        }
                    } else {
                        withAnimation(.spring(response: 0.3)) { calendarDrag = 0 }
                    }
                } else if showSettings {
                    if value.translation.width > threshold ||
                       value.predictedEndTranslation.width > drawerWidth * 0.5 {
                        withAnimation(.easeOut(duration: 0.25)) {
                            showSettings = false; settingsDrag = 0
                        }
                    } else {
                        withAnimation(.spring(response: 0.3)) { settingsDrag = 0 }
                    }
                }
            }
    }

    private var settingsDrawerCloseDrag: some Gesture {
        DragGesture(minimumDistance: 30, coordinateSpace: .local)
            .onChanged { value in
                guard showSettings, value.translation.width > 0 else { return }
                settingsDrag = value.translation.width
            }
            .onEnded { value in
                guard showSettings else { return }
                if value.translation.width > drawerWidth * 0.25 ||
                   value.predictedEndTranslation.width > drawerWidth * 0.5 {
                    withAnimation(.easeOut(duration: 0.25)) {
                        showSettings = false; settingsDrag = 0
                    }
                } else {
                    withAnimation(.spring(response: 0.3)) { settingsDrag = 0 }
                }
            }
    }

    private var calendarDrawerCloseDrag: some Gesture {
        DragGesture(minimumDistance: 30, coordinateSpace: .local)
            .onChanged { value in
                guard showCalendar, value.translation.width < 0 else { return }
                calendarDrag = value.translation.width
            }
            .onEnded { value in
                guard showCalendar else { return }
                if value.translation.width < -drawerWidth * 0.25 ||
                   value.predictedEndTranslation.width < -drawerWidth * 0.5 {
                    withAnimation(.easeOut(duration: 0.25)) {
                        showCalendar = false; calendarDrag = 0
                    }
                } else {
                    withAnimation(.spring(response: 0.3)) { calendarDrag = 0 }
                }
            }
    }

    private func closeDrawers() {
        withAnimation(.easeOut(duration: 0.25)) {
            showCalendar = false
            showSettings = false
            calendarDrag = 0
            settingsDrag = 0
        }
    }

    private func dismissKeyboard() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            if !dailyTaskStore.tasks.isEmpty {
                DailyTaskIndicator(showPopover: $showDailyTasks)
            } else {
                Color.clear.frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
            }
            Spacer()
            Text("Cozy Pup")
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textTertiary)
            Spacer()
            Color.clear.frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
        }
        .padding(.horizontal, Tokens.spacing.lg)
        .padding(.vertical, Tokens.spacing.xs)
    }

    // MARK: - Cards

    @ViewBuilder
    private func cardView(_ card: CardData) -> some View {
        switch card {
        case .record(let data):
            RecordCard(petName: data.pet_name, date: data.date, category: data.category)
        case .map(let data):
            MapCard(items: data.items)
        case .email(let data):
            EmailCard(subject: data.subject, emailBody: data.body)
        case .petCreated(let data):
            ActionCard(
                icon: "pawprint.fill", iconColor: Tokens.green,
                label: L.petAdded,
                title: data.pet_name,
                subtitle: "\(data.breed ?? data.species)"
            ) { navigateToSettings() }
        case .reminder(let data):
            ActionCard(
                icon: "bell.fill", iconColor: Tokens.accent,
                label: L.reminderSet,
                title: "\(data.pet_name) · \(data.title)",
                subtitle: data.trigger_at
            )
        case .petUpdated(let data):
            ActionCard(
                icon: "checkmark.circle.fill", iconColor: Tokens.green,
                label: Lang.shared.isZh ? "已更新" : "Updated",
                title: data.pet_name,
                subtitle: data.saved_keys?.joined(separator: ", ") ?? ""
            ) { navigateToSettings(petId: data.pet_id ?? data.pet_name) }
        case .confirmAction(let data):
            ConfirmActionCard(
                message: data.message,
                status: data.status,
                onConfirm: { handleConfirmAction(actionId: data.action_id) },
                onCancel: { handleCancelAction(actionId: data.action_id) }
            )
        case .locationPicker(let data):
            LocationPickerCard(data: data)
        case .dailyTask(let data):
            DailyTaskCard(data: data)
        case .calendarSync:
            ActionCard(
                icon: "calendar.badge.plus", iconColor: Tokens.green,
                label: Lang.shared.isZh ? "日历同步" : "Calendar Sync",
                title: Lang.shared.isZh ? "同步到 Apple 日历" : "Sync to Apple Calendar",
                subtitle: ""
            ) {
                showCalendarSyncOptions = true
            }
        case .setLanguage:
            EmptyView()
        case .genericAction(let data):
            ActionCard(
                icon: iconForActionType(data.type),
                iconColor: colorForActionType(data.type),
                label: labelForActionType(data.type),
                title: data.pet_name ?? data.title ?? "",
                subtitle: data.saved_keys?.joined(separator: ", ") ?? ""
            ) {
                let dest = navigationForActionType(data.type)
                if dest == "settings" { navigateToSettings(petId: data.pet_id ?? data.pet_name) }
                else if dest == "daily_tasks" {
                    showTaskManager = true
                }
            }
        }
    }

    // MARK: - Chat

    private func handleSlashCommand(_ command: String) {
        showSlashMenu = false
        inputText = ""
        switch command {
        case "clear":
            withAnimation(.easeOut(duration: 0.25)) {
                chatStore.clear()
            }
            Haptics.light()
        default:
            break
        }
    }

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespaces)

        // Intercept slash commands
        if text.lowercased() == "/clear" {
            handleSlashCommand("clear")
            return
        }

        let photos = pendingPhotos
        guard !text.isEmpty || !photos.isEmpty, !isStreaming else { return }
        Haptics.light()

        let userMsg = ChatMessage(role: .user, content: text, imageData: photos.isEmpty ? nil : photos)
        let assistantMsg = ChatMessage(role: .assistant)
        chatStore.messages.append(userMsg)
        chatStore.messages.append(assistantMsg)
        chatStore.save()

        inputText = ""
        pendingPhotos = []
        isStreaming = true

        Task {
            let coord = location.lastLocation
            let loc = coord.map { (lat: $0.latitude, lng: $0.longitude) }
            let stream = ChatService.streamChat(
                message: text, sessionId: chatStore.sessionId, location: loc,
                images: photos, detectedLanguage: voiceDetectedLanguage
            )
            voiceDetectedLanguage = nil

            do {
                for try await event in stream {
                    guard let idx = chatStore.messages.indices.last else { break }
                    switch event {
                    case .token(let t):
                        chatStore.messages[idx].content += t
                    case .card(let c):
                        chatStore.messages[idx].cards.append(c)
                        if case .petCreated = c {
                            Task { await petStore.fetchFromAPI() }
                        }
                        if case .petUpdated(let data) = c {
                            Task { await petStore.fetchFromAPI() }
                            if data.saved_keys?.contains("avatar") == true {
                                petStore.avatarRevision += 1
                            }
                        }
                        if case .setLanguage(let data) = c {
                            Lang.shared.code = data.language
                        }
                        if case .genericAction(let data) = c {
                            if ["pet_deleted", "pet_updated"].contains(data.type) {
                                Task { await petStore.fetchFromAPI() }
                            }
                            if ["daily_task_created", "daily_task_updated", "daily_task_deleted"].contains(data.type) {
                                Task { await dailyTaskStore.fetchToday() }
                            }
                            if ["pet_deleted", "event_deleted", "reminder_deleted"].contains(data.type) {
                                let comps = Calendar.current.dateComponents([.year, .month], from: Date())
                                Task { await calendarStore.fetchMonth(year: comps.year!, month: comps.month!) }
                            }
                        }
                        if case .calendarSync = c {
                            showCalendarSyncOptions = true
                        }
                        if case .record(let r) = c, let comps = parseYearMonth(r.date) {
                            Task { await calendarStore.fetchMonth(year: comps.0, month: comps.1) }
                            // Also refresh old month if event was moved across months
                            if let oldDate = r.old_date, let oldComps = parseYearMonth(oldDate),
                               (oldComps.0, oldComps.1) != (comps.0, comps.1) {
                                Task { await calendarStore.fetchMonth(year: oldComps.0, month: oldComps.1) }
                            }
                        }
                    case .emergency(let e):
                        emergency = e
                    case .locationCard(let data):
                        let card = CardData.locationPicker(data)
                        chatStore.messages[idx].cards.append(card)
                    case .done(_, let sid):
                        chatStore.saveSession(sid)
                    }
                }
            } catch {
                if let idx = chatStore.messages.indices.last,
                   chatStore.messages[idx].content.isEmpty {
                    chatStore.messages[idx].content = L.errorMessage
                }
            }
            chatStore.save()
            isStreaming = false
        }
    }

    // MARK: - Card Navigation

    private func navigateToSettings(petId: String? = nil) {
        settingsDeepLinkPetId = petId
        withAnimation(.easeOut(duration: 0.3)) { showSettings = true }
    }

    private func navigationForActionType(_ type: String) -> String {
        switch type {
        case "pet_deleted", "pet_updated", "profile_summarized": return "settings"
        case "event_deleted", "reminder_deleted": return "calendar"
        case "daily_task_created", "daily_task_updated", "daily_task_deleted": return "daily_tasks"
        default: return ""
        }
    }

    // MARK: - Generic Action Card Helpers

    private func iconForActionType(_ type: String) -> String {
        switch type {
        case "pet_deleted": return "trash.fill"
        case "event_deleted": return "calendar.badge.minus"
        case "reminder_deleted": return "bell.slash.fill"
        case "profile_summarized": return "doc.text.fill"
        default: return "checkmark.circle.fill"
        }
    }

    private func colorForActionType(_ type: String) -> Color {
        switch type {
        case "pet_deleted", "event_deleted", "reminder_deleted": return Tokens.red
        case "profile_summarized": return Tokens.blue
        default: return Tokens.green
        }
    }

    private func labelForActionType(_ type: String) -> String {
        let zh = Lang.shared.isZh
        switch type {
        case "pet_deleted": return zh ? "已删除" : "Deleted"
        case "event_deleted": return zh ? "已删除" : "Deleted"
        case "reminder_deleted": return zh ? "已取消" : "Cancelled"
        case "profile_summarized": return zh ? "档案已更新" : "Profile Updated"
        default: return zh ? "已完成" : "Done"
        }
    }

    // MARK: - Confirm Actions

    private func handleConfirmAction(actionId: String) {
        Haptics.light()
        Task {
            struct ConfirmBody: Encodable { let action_id: String }
            struct ConfirmResponse: Decodable {
                let success: Bool
                let card: CardData?
                let message: String?
            }

            do {
                let resp: ConfirmResponse = try await APIClient.shared.request(
                    "POST", "/chat/confirm-action",
                    body: ConfirmBody(action_id: actionId)
                )

                // Update the confirm card status
                updateConfirmCardStatus(actionId: actionId, status: .confirmed)

                // If a result card came back, append it
                if let card = resp.card, let idx = chatStore.messages.indices.last {
                    chatStore.messages[idx].cards.append(card)

                    // Refresh relevant stores
                    if case .record(let r) = card, let comps = parseYearMonth(r.date) {
                        Task { await calendarStore.fetchMonth(year: comps.0, month: comps.1) }
                    }
                }

                Task { await petStore.fetchFromAPI() }
                // Also refresh calendar (delete/update events)
                let comps = Calendar.current.dateComponents([.year, .month], from: Date())
                Task { await calendarStore.fetchMonth(year: comps.year!, month: comps.month!) }
            } catch {
                updateConfirmCardStatus(actionId: actionId, status: .pending)
            }
            chatStore.save()
        }
    }

    private func handleCancelAction(actionId: String) {
        Haptics.light()
        updateConfirmCardStatus(actionId: actionId, status: .cancelled)
        chatStore.save()
    }

    private func updateConfirmCardStatus(actionId: String, status: ConfirmActionCardData.ConfirmStatus) {
        for msgIdx in chatStore.messages.indices {
            for cardIdx in chatStore.messages[msgIdx].cards.indices {
                if case .confirmAction(var data) = chatStore.messages[msgIdx].cards[cardIdx],
                   data.action_id == actionId {
                    data.status = status
                    chatStore.messages[msgIdx].cards[cardIdx] = .confirmAction(data)
                    return
                }
            }
        }
    }

    private func parseYearMonth(_ dateStr: String) -> (Int, Int)? {
        let parts = dateStr.split(separator: "-")
        guard parts.count >= 2, let y = Int(parts[0]), let m = Int(parts[1]) else { return nil }
        return (y, m)
    }

    private func startVoice() {
        guard !speech.isListening else { return }
        Task {
            let granted = await speech.requestPermission()
            if granted {
                speech.startListening()
                Haptics.medium()
            }
        }
    }

    private func releaseVoice() {
        guard speech.isListening else { return }
        Haptics.light()
        let text = speech.transcript.trimmingCharacters(in: .whitespaces)
        let lang = speech.detectedLanguage
        speech.stopListening()
        if !text.isEmpty {
            inputText = text
            voiceDetectedLanguage = lang.isEmpty ? nil : lang
            sendMessage()
        }
    }

    private func cancelVoice() {
        speech.cancel()
    }

    @ViewBuilder
    private func photoGrid(_ photos: [Data]) -> some View {
        let cols = photos.count == 1 ? 1 : (photos.count <= 4 ? 2 : 3)
        let size: CGFloat = photos.count == 1 ? 160 : (photos.count <= 4 ? 90 : 70)
        LazyVGrid(
            columns: Array(repeating: GridItem(.fixed(size), spacing: 4), count: cols),
            alignment: .trailing,
            spacing: 4
        ) {
            ForEach(Array(photos.enumerated()), id: \.offset) { _, data in
                if let img = UIImage(data: data) {
                    Image(uiImage: img)
                        .resizable()
                        .scaledToFill()
                        .frame(width: size, height: size)
                        .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
                        .onTapGesture { fullScreenImage = img }
                        .contextMenu {
                            Button {
                                UIPasteboard.general.image = img
                            } label: {
                                Label(Lang.shared.isZh ? "拷贝图片" : "Copy Image", systemImage: "doc.on.doc")
                            }
                            ShareLink(item: Image(uiImage: img), preview: SharePreview("Photo", image: Image(uiImage: img)))
                        }
                }
            }
        }
    }
}

// MARK: - Slash Command Menu

private struct SlashCommandMenu: View {
    let onSelect: (String) -> Void

    private struct SlashCommand {
        let name: String
        let icon: String
        let label: String
    }

    private var commands: [SlashCommand] {
        [
            SlashCommand(
                name: "clear",
                icon: "trash",
                label: Lang.shared.isZh ? "清空对话记录" : "Clear chat history"
            ),
        ]
    }

    var body: some View {
        VStack(spacing: 0) {
            ForEach(commands, id: \.name) { cmd in
                Button {
                    onSelect(cmd.name)
                } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Image(systemName: cmd.icon)
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.accent)
                            .frame(width: 24)
                        Text("/\(cmd.name)")
                            .font(Tokens.fontBody.weight(.medium))
                            .foregroundColor(Tokens.text)
                        Text(cmd.label)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                        Spacer()
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.sm + Tokens.spacing.xs)
                }
            }
        }
        .background(Tokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
        .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
        .padding(.horizontal, 12)
        .shadow(color: Tokens.dimOverlay.opacity(0.08), radius: 6, y: -2)
    }
}
