import SwiftUI

/// Main app screen. Shown by `CozyPupApp` once the user is authed,
/// has acknowledged the disclaimer, and has at least one pet.
///
/// Hosts SSE chat streaming (via `ChatService`), renders inline SSE cards,
/// and overlays the left Calendar drawer, right Settings drawer, voice
/// input overlay, daily-task popover, and paywall sheets. Binds to
/// ChatStore / CalendarStore / PetStore / DailyTaskStore / SubscriptionStore.
struct ChatView: View {
    @EnvironmentObject var chatStore: ChatStore
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @EnvironmentObject var dailyTaskStore: DailyTaskStore
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    // Owned by this view (not shared app-wide), so @StateObject — lifetime tied to ChatView.
    @StateObject private var speech = SpeechService()
    @StateObject private var location = LocationService()

    @State private var inputText = ""
    @State private var isStreaming = false
    @State private var emergency: EmergencyData?
    @State private var showSoftPaywall = false
    @State private var showUpgradeModal = false
    @State private var showCalendar = false
    @State private var calendarJumpDate: String?
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
    @State private var showSavedChats = false
    @State private var showSaveConfirm = false
    @State private var savedTitle: String?
    @State private var previewEvent: CalendarEvent?
    @Namespace private var previewNS

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
                                VStack(spacing: Tokens.spacing.md) {
                                    // Welcome message (first time only)
                                    if !chatStore.hasSeenWelcome {
                                        HStack(alignment: .top, spacing: Tokens.spacing.sm) {
                                            Image("logo")
                                                .resizable()
                                                .frame(width: 28, height: 28)
                                                .cornerRadius(14)
                                            Text(Lang.shared.isZh
                                                ? "你好！我是 CozyPup，你的宠物专属管家 🐾\n\n我可以帮你：记录健康状况、设置疫苗提醒、查找附近宠物医院、解答养宠问题。\n\n先告诉我你家毛孩子叫什么吧～"
                                                : "Hi! I'm CozyPup, your pet's personal butler 🐾\n\nI can help you: track health, set vaccine reminders, find nearby vets, and answer pet care questions.\n\nTell me your pet's name to get started!")
                                                .font(Tokens.fontBody)
                                                .foregroundColor(Tokens.text)
                                                .padding(Tokens.spacing.md)
                                                .background(Tokens.bubbleAi)
                                                .cornerRadius(Tokens.radius)
                                        }
                                        .padding(.horizontal, Tokens.spacing.md)
                                        .padding(.top, Tokens.spacing.xl)
                                    }

                                    Spacer()
                                }
                                .frame(minHeight: 400)
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
                                        } else if let urls = msg.imageUrls, !urls.isEmpty {
                                            HStack {
                                                if msg.role == .user { Spacer() }
                                                photoGridFromUrls(urls)
                                                if msg.role != .user { Spacer() }
                                            }
                                        }
                                        if !msg.content.isEmpty {
                                            ChatBubble(role: msg.role, content: msg.content)
                                        }
                                        cardListView(msg.cards)
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

                // Quick action chips (only when no messages yet)
                if chatStore.messages.isEmpty {
                    QuickActionCards { message in
                        inputText = message
                        sendMessage()
                        chatStore.hasSeenWelcome = true
                    }
                    .padding(.bottom, Tokens.spacing.xs)
                }

                // Slash command menu
                if showSlashMenu {
                    SlashCommandMenu(onSelect: { command in
                        handleSlashCommand(command)
                    })
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                // Expired users keep the normal input bar. When they send,
                // the backend's /chat gate returns an upgrade_prompt stream
                // which renders as an inline card in the chat history.
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
                .onTapGesture {
                    // Safety valve: tap anywhere to stop and send (in case DragGesture.onEnded was swallowed)
                    releaseVoice()
                }
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
            CalendarDrawer(isPresented: $showCalendar, jumpToDate: calendarJumpDate, onPreviewEvent: { evt in
                withAnimation(.spring(response: 0.42, dampingFraction: 0.82)) {
                    previewEvent = evt
                }
            })
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
        // Safety net: SwiftUI occasionally swallows DragGesture.onEnded when another
        // gesture wins the arbitration, leaving the drawer half-open. If the drag
        // value stops changing for 0.5s while non-zero, force it back to 0.
        // Safety net: if drawer drag gets stuck (onEnded not called), snap back
        .onChange(of: settingsDrag) { _, val in
            guard val != 0, showSettings else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                if settingsDrag == val { // still the same value after 0.5s — stuck
                    withAnimation(.spring(response: 0.3)) { settingsDrag = 0 }
                }
            }
        }
        .onChange(of: calendarDrag) { _, val in
            guard val != 0, showCalendar else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                if calendarDrag == val {
                    withAnimation(.spring(response: 0.3)) { calendarDrag = 0 }
                }
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
        // Expired users are no longer hard-blocked from the app —
        // they can still browse pets / calendar / reminders. The backend
        // intercepts POST /chat and returns an upgrade_prompt card inline,
        // so the paywall is reached from the card tap, not from a cliff.
        .sheet(isPresented: $showSoftPaywall) {
            PaywallSheet(isHard: false) { showSoftPaywall = false }
                .presentationDetents([.medium])
                .environmentObject(subscriptionStore)
        }
        .fullScreenCover(isPresented: $showUpgradeModal) {
            UpgradeModal { showUpgradeModal = false }
                .environmentObject(subscriptionStore)
        }
        .alert(Lang.shared.isZh ? "保存当前对话？" : "Save current chat?", isPresented: $showSaveConfirm) {
            Button(Lang.shared.isZh ? "取消" : "Cancel", role: .cancel) {}
            Button(Lang.shared.isZh ? "保存" : "Save") {
                Task {
                    if let title = await chatStore.saveCurrentSession() {
                        savedTitle = title
                    }
                }
            }
        }
        .alert(Lang.shared.isZh ? "已保存" : "Saved", isPresented: .init(
            get: { savedTitle != nil },
            set: { if !$0 { savedTitle = nil } }
        )) {
            Button(Lang.shared.isZh ? "好的" : "OK") { savedTitle = nil }
        } message: {
            Text(savedTitle ?? "")
        }
        .sheet(isPresented: $showSavedChats) {
            SavedChatsSheet(
                onResume: { sessionId, messages in
                    showSavedChats = false
                    Task {
                        await chatStore.switchToSession(id: sessionId, messages: messages)
                    }
                },
                onDismiss: { showSavedChats = false }
            )
            .presentationDetents([.medium, .large])
            .environmentObject(chatStore)
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.willResignActiveNotification)) { _ in
            // App interrupted (swipe up, notification, phone call) — cancel voice to prevent stuck state
            if speech.isListening {
                cancelVoice()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .openSavedChats)) { _ in
            showSavedChats = true
        }
        .overlay {
            if let evt = previewEvent {
                EventPreviewOverlay(
                    event: evt,
                    namespace: previewNS,
                    matchedId: "event-\(evt.id)",
                    onDismiss: {
                        withAnimation(.spring(response: 0.38, dampingFraction: 0.85)) {
                            previewEvent = nil
                        }
                    },
                    onDelete: { calendarStore.remove(evt.id) },
                    onSave: { draft in
                        calendarStore.update(
                            evt.id,
                            title: draft.title,
                            category: draft.category,
                            eventDate: draft.eventDate,
                            eventTime: draft.eventTime,
                            cost: draft.cost,
                            reminderAt: draft.reminderAt,
                            notes: draft.notes,
                            type: draft.type
                        )
                    },
                    onPhotoUpload: { data in
                        await calendarStore.uploadEventPhoto(eventId: evt.id, imageData: data)
                    },
                    onPhotoDelete: { url in
                        Task { await calendarStore.deleteEventPhoto(eventId: evt.id, photoUrl: url) }
                    },
                    onLocationUpdate: { name, address, lat, lng, placeId in
                        Task { await calendarStore.updateLocation(eventId: evt.id, name: name, address: address, lat: lat, lng: lng, placeId: placeId) }
                    },
                    onLocationRemove: {
                        Task { await calendarStore.removeLocation(eventId: evt.id) }
                    }
                )
                .transition(.asymmetric(
                    insertion: .scale(scale: 0.85).combined(with: .opacity),
                    removal: .scale(scale: 0.9).combined(with: .opacity)
                ))
                .zIndex(999)
            }
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
                // Only allow horizontal drag when it's clearly horizontal (not a vertical scroll)
                let horizontal = abs(value.translation.width)
                let vertical = abs(value.translation.height)
                guard horizontal > vertical * 0.8 else { return }
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
                let horizontal = abs(value.translation.width)
                let vertical = abs(value.translation.height)
                guard horizontal > vertical * 0.8 else { return }
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
            calendarJumpDate = nil
        }
    }

    private func dismissKeyboard() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: Tokens.spacing.sm) {
            // Left: calendar + task check
            Button {
                withAnimation(.easeInOut(duration: 0.35)) { showCalendar = true }
            } label: {
                Image(systemName: "calendar")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
            }
            .buttonStyle(.plain)

            if !dailyTaskStore.tasks.isEmpty {
                Button { showDailyTasks.toggle() } label: {
                    Image(systemName: dailyTaskStore.allCompleted ? "checkmark.circle.fill" : "checkmark.circle")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(dailyTaskStore.allCompleted ? Tokens.green : Tokens.textSecondary)
                        .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                }
                .buttonStyle(.plain)
            }

            Spacer()

            // Right: settings icon
            Button {
                withAnimation(.easeInOut(duration: 0.35)) { showSettings = true }
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
            }
            .buttonStyle(.plain)
        }
        .overlay {
            Image("logo")
                .resizable()
                .frame(width: 48, height: 48)
                .cornerRadius(10)
        }
        .padding(.horizontal, Tokens.spacing.lg)
        .padding(.vertical, Tokens.spacing.xs)
    }

    // MARK: - Cards

    /// Groups consecutive placeDetail cards into a paged TabView; renders all other cards individually.
    @ViewBuilder
    private func cardListView(_ cards: [CardData]) -> some View {
        let groups = groupCards(cards)
        ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
            if group.count > 1, case .placeDetail = group[0] {
                // Multiple placeDetail cards → paged TabView
                let details: [PlaceDetailCardData] = group.compactMap { if case .placeDetail(let d) = $0 { return d } else { return nil } }
                TabView {
                    ForEach(Array(details.enumerated()), id: \.offset) { _, data in
                        PlaceDetailCard(data: data)
                            .padding(.bottom, Tokens.spacing.lg)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .automatic))
                .frame(height: 400)
            } else {
                ForEach(Array(group.enumerated()), id: \.offset) { _, card in
                    cardView(card)
                }
            }
        }
    }

    /// Groups consecutive placeDetail cards together; other cards are 1-element groups.
    private func groupCards(_ cards: [CardData]) -> [[CardData]] {
        var groups: [[CardData]] = []
        for card in cards {
            if case .placeDetail = card, let last = groups.last, case .placeDetail = last.first {
                groups[groups.count - 1].append(card)
            } else {
                groups.append([card])
            }
        }
        return groups
    }

    @ViewBuilder
    private func cardView(_ card: CardData) -> some View {
        switch card {
        case .record(let data):
            RecordCard(
                petName: data.pet_name,
                date: data.date,
                category: data.category,
                title: data.title,
                cost: data.cost,
                hasReminder: data.reminder_at != nil,
                photosCount: data.photos_count ?? 0,
                eventTime: data.event_time,
                rawText: data.raw_text,
                onTap: {
                    calendarJumpDate = data.date
                    withAnimation(.easeInOut(duration: 0.35)) {
                        showCalendar = true
                    }
                }
            )
        case .placeCard(let data):
            PlaceCard(data: data)
        case .placeDetail(let data):
            PlaceDetailCard(data: data)
        case .directions(let data):
            DirectionsCard(data: data)
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
            let subtitle: String = {
                if let fields = data.saved_fields, !fields.isEmpty {
                    return fields.map { "\($0.label): \($0.value)" }.joined(separator: Lang.shared.isZh ? "、" : ", ")
                }
                return data.saved_keys?.joined(separator: ", ") ?? ""
            }()
            ActionCard(
                icon: "checkmark.circle.fill", iconColor: Tokens.green,
                label: Lang.shared.isZh ? "已更新" : "Updated",
                title: data.pet_name,
                subtitle: subtitle
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
                .onAppear { Task { await dailyTaskStore.fetchToday() } }
        case .calendarSync:
            ActionCard(
                icon: "calendar.badge.plus", iconColor: Tokens.green,
                label: Lang.shared.isZh ? "日历同步" : "Calendar Sync",
                title: Lang.shared.isZh ? "同步到 Apple 日历" : "Sync to Apple Calendar",
                subtitle: ""
            ) {
                showCalendarSyncOptions = true
            }
        case .references(let data):
            ReferencesCard(data: data)
        case .setLanguage:
            EmptyView()
        case .upgradePrompt:
            ActionCard(
                icon: "crown.fill",
                iconColor: Tokens.accent,
                label: Lang.shared.isZh ? "升级订阅" : "Upgrade",
                title: Lang.shared.isZh ? "继续与 CozyPup AI 对话" : "Keep chatting with CozyPup AI",
                subtitle: Lang.shared.isZh
                    ? "试用已结束 · 宠物档案、日历和提醒依然免费"
                    : "Trial ended · Profiles, calendar, reminders still free"
            ) {
                showUpgradeModal = true
            }
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
        case "savechat":
            showSaveConfirm = true
        case "loadchat":
            showSavedChats = true
        default:
            break
        }
    }

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespaces)

        // Intercept slash commands
        let lower = text.lowercased()
        if lower == "/clear" || lower == "/savechat" || lower == "/loadchat" {
            handleSlashCommand(String(lower.dropFirst()))
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
            // Consume the one-shot new-session flag so the backend starts a
            // fresh session row for the first message after /clear.
            let newSession = chatStore.pendingNewSession
            chatStore.pendingNewSession = false
            let stream = ChatService.streamChat(
                message: text, sessionId: chatStore.sessionId, location: loc,
                images: photos, detectedLanguage: voiceDetectedLanguage,
                newSession: newSession
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

            // Track message count and check soft paywall
            chatStore.incrementMessageCount()
            if case .trial(let daysLeft) = subscriptionStore.status,
               daysLeft < 7,
               chatStore.totalMessageCount >= 10,
               chatStore.softPaywallShownCount < 2 {
                if chatStore.lastSoftPaywallDate == nil ||
                   !Calendar.current.isDateInToday(chatStore.lastSoftPaywallDate!) {
                    showSoftPaywall = true
                    chatStore.softPaywallShownCount += 1
                    chatStore.lastSoftPaywallDate = Date()
                }
            }

            // Always refresh daily tasks after any chat response —
            // LLM may have created/deleted tasks, or claimed it did without calling tools
            await dailyTaskStore.fetchToday()
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

                // If a result card came back, add it as a new message
                if let card = resp.card {
                    let msg = ChatMessage(
                        id: UUID().uuidString,
                        role: .assistant,
                        content: "",
                        cards: [card]
                    )
                    chatStore.messages.append(msg)

                    // Refresh relevant stores
                    if case .record(let r) = card, let comps = parseYearMonth(r.date) {
                        Task { await calendarStore.fetchMonth(year: comps.0, month: comps.1) }
                    }
                    if case .petUpdated = card {
                        Task { await petStore.fetchFromAPI() }
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

    private func photoURL(_ path: String) -> URL? {
        if path.hasPrefix("http") { return URL(string: path) }
        return APIClient.shared.avatarURL(path)
    }

    @ViewBuilder
    private func photoGridFromUrls(_ urls: [String]) -> some View {
        let cols = urls.count == 1 ? 1 : (urls.count <= 4 ? 2 : 3)
        let size: CGFloat = urls.count == 1 ? 160 : (urls.count <= 4 ? 90 : 70)
        LazyVGrid(
            columns: Array(repeating: GridItem(.fixed(size), spacing: 4), count: cols),
            alignment: .trailing,
            spacing: 4
        ) {
            ForEach(Array(urls.enumerated()), id: \.offset) { _, urlStr in
                if let url = photoURL(urlStr) {
                    CachedAsyncImage(url: url) { image in
                        image
                            .resizable()
                            .scaledToFill()
                    } placeholder: {
                        Tokens.placeholderBg
                    }
                    .frame(width: size, height: size)
                    .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
                }
            }
        }
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
                name: "savechat",
                icon: "bookmark.fill",
                label: Lang.shared.isZh ? "保存对话" : "Save chat"
            ),
            SlashCommand(
                name: "loadchat",
                icon: "clock.arrow.circlepath",
                label: Lang.shared.isZh ? "加载对话" : "Load chat"
            ),
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
