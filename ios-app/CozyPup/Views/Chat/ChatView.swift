import SwiftUI

struct ChatView: View {
    @EnvironmentObject var chatStore: ChatStore
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @StateObject private var speech = SpeechService()
    @StateObject private var location = LocationService()

    @State private var inputText = ""
    @State private var isStreaming = false
    @State private var emergency: EmergencyData?
    @State private var showCalendar = false
    @State private var showSettings = false
    @State private var calendarDrag: CGFloat = 0
    @State private var settingsDrag: CGFloat = 0

    private var drawerWidth: CGFloat { UIScreen.main.bounds.width * 0.85 }

    // Calendar: -drawerWidth (hidden) to 0 (open)
    private var calendarX: CGFloat {
        let base: CGFloat = showCalendar ? 0 : -drawerWidth
        return min(0, max(-drawerWidth, base + calendarDrag))
    }

    // Settings: 0 (open) to drawerWidth (hidden)
    private var settingsX: CGFloat {
        let base: CGFloat = showSettings ? 0 : drawerWidth
        return max(0, min(drawerWidth, base + settingsDrag))
    }

    // 0 = all closed, 1 = fully open
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
                        LazyVStack(spacing: 10) {
                            ForEach(chatStore.messages) { msg in
                                VStack(spacing: 8) {
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
                    .scrollDismissesKeyboard(.interactively)
                    .onTapGesture {
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    }
                    .onChange(of: chatStore.messages.count) {
                        withAnimation { proxy.scrollTo("bottom") }
                    }
                }

                Text(L.aiDisclaimer)
                    .font(.system(size: 11))
                    .foregroundColor(Tokens.textSecondary)
                    .padding(.vertical, 6)

                ChatInputBar(
                    text: $inputText,
                    isStreaming: isStreaming,
                    isListening: speech.isListening,
                    onSend: sendMessage,
                    onMicDown: startVoice,
                    onMicUp: releaseVoice,
                    onMicCancel: cancelVoice
                )
            }
            .background(Tokens.bg.ignoresSafeArea())

            // Voice overlay
            if speech.isListening {
                VoiceInputOverlay(
                    transcript: speech.transcript,
                    audioLevel: speech.audioLevel,
                    isCancelling: false
                )
                .transition(.opacity)
            }
        }
        // 1. Edge swipe areas (always rendered, below dimming overlay)
        .overlay {
            HStack(spacing: 0) {
                Color.clear.frame(width: 28)
                    .contentShape(Rectangle())
                    .gesture(edgeOpenGesture(isCalendar: true))
                Spacer()
                Color.clear.frame(width: 28)
                    .contentShape(Rectangle())
                    .gesture(edgeOpenGesture(isCalendar: false))
            }
            .ignoresSafeArea()
        }
        // 2. Dimming overlay (covers edge areas when drawer is open)
        .overlay {
            Color.black.opacity(Double(drawerProgress) * 0.3)
                .ignoresSafeArea()
                .allowsHitTesting(showCalendar || showSettings)
                .onTapGesture { closeDrawers() }
                .gesture(overlayCloseDrag)
        }
        // 3. Calendar drawer
        .overlay(alignment: .leading) {
            CalendarDrawer(isPresented: $showCalendar)
                .frame(width: drawerWidth)
                .frame(maxHeight: .infinity)
                .background(Tokens.bg)
                .clipShape(UnevenRoundedRectangle(bottomTrailingRadius: 20, topTrailingRadius: 20))
                .shadow(color: .black.opacity(drawerProgress > 0.01 ? 0.15 : 0), radius: 10, x: 2)
                .offset(x: calendarX)
                .ignoresSafeArea()
        }
        // 4. Settings drawer
        .overlay(alignment: .trailing) {
            SettingsDrawer(isPresented: $showSettings)
                .frame(width: drawerWidth)
                .frame(maxHeight: .infinity)
                .background(Tokens.bg)
                .clipShape(UnevenRoundedRectangle(topLeadingRadius: 20, bottomLeadingRadius: 20))
                .shadow(color: .black.opacity(drawerProgress > 0.01 ? 0.15 : 0), radius: 10, x: -2)
                .offset(x: settingsX)
                .ignoresSafeArea()
        }
        .onChange(of: showCalendar) { _, val in
            if !val { calendarDrag = 0 }
        }
        .onChange(of: showSettings) { _, val in
            if !val { settingsDrag = 0 }
        }
        .onAppear {
            Task {
                await petStore.fetchFromAPI()
                await location.requestLocation()
            }
        }
    }

    // MARK: - Drawer Gestures

    /// Edge swipe to open a drawer
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

    /// Drag on the dimming overlay to close open drawer
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
            Button {
                Haptics.light()
                dismissKeyboard()
                withAnimation(.easeOut(duration: 0.3)) { showCalendar = true }
            } label: {
                Image(systemName: "calendar")
                    .font(.system(size: 18))
                    .foregroundColor(Tokens.text)
                    .frame(width: 40, height: 40)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusIcon)
                    .overlay(RoundedRectangle(cornerRadius: Tokens.radiusIcon).stroke(Tokens.border))
                    .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
            }

            Spacer()

            HStack(spacing: 8) {
                Image("logo")
                    .resizable()
                    .frame(width: 28, height: 28)
                    .cornerRadius(8)
                Text("Cozy Pup")
                    .font(.system(.title3, design: .serif))
                    .fontWeight(.medium)
                    .foregroundColor(Tokens.accent)
            }

            Spacer()

            Button {
                Haptics.light()
                dismissKeyboard()
                withAnimation(.easeOut(duration: 0.3)) { showSettings = true }
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 18))
                    .foregroundColor(Tokens.text)
                    .frame(width: 40, height: 40)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusIcon)
                    .overlay(RoundedRectangle(cornerRadius: Tokens.radiusIcon).stroke(Tokens.border))
                    .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 12)
    }

    // MARK: - Cards

    @ViewBuilder
    private func cardView(_ card: CardData) -> some View {
        switch card {
        case .record(let data):
            RecordCard(petName: data.pet_name, date: data.date, category: data.category) {
                withAnimation(.easeOut(duration: 0.3)) { showCalendar = true }
            }
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
            )
        case .reminder(let data):
            ActionCard(
                icon: "bell.fill", iconColor: Tokens.accent,
                label: L.reminderSet,
                title: "\(data.pet_name) · \(data.title)",
                subtitle: data.trigger_at
            )
        }
    }

    // MARK: - Chat

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty, !isStreaming else { return }
        Haptics.light()

        let userMsg = ChatMessage(role: .user, content: text)
        let assistantMsg = ChatMessage(role: .assistant)
        chatStore.messages.append(userMsg)
        chatStore.messages.append(assistantMsg)
        chatStore.save()

        inputText = ""
        isStreaming = true

        Task {
            let coord = location.lastLocation
            let loc = coord.map { (lat: $0.latitude, lng: $0.longitude) }
            let stream = ChatService.streamChat(
                message: text, sessionId: chatStore.sessionId, location: loc
            )

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
                        if case .record(let r) = c, let comps = parseYearMonth(r.date) {
                            Task { await calendarStore.fetchMonth(year: comps.0, month: comps.1) }
                        }
                    case .emergency(let e):
                        emergency = e
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
        speech.stopListening()
        if !text.isEmpty {
            inputText = text
            sendMessage()
        }
    }

    private func cancelVoice() {
        speech.cancel()
    }
}
