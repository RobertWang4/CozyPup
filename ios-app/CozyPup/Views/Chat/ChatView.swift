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

    var body: some View {
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
                        EmptyStateView(
                            icon: "bubble.left.and.bubble.right",
                            title: "Ask Cozy Pup anything",
                            subtitle: "Health questions, record keeping, vet recommendations..."
                        )
                        .frame(minHeight: 400)
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
                .onChange(of: chatStore.messages.count) {
                    withAnimation { proxy.scrollTo("bottom") }
                }
            }

            Text("AI suggestions are for reference only. In emergencies, see a vet.")
                .font(.system(size: 11))
                .foregroundColor(Tokens.textSecondary)
                .padding(.vertical, 6)

            ChatInputBar(
                text: $inputText,
                isStreaming: isStreaming,
                isListening: speech.isListening,
                onSend: sendMessage,
                onMicToggle: toggleMic
            )
        }
        .background(Tokens.bg.ignoresSafeArea())
        .overlay {
            if showCalendar || showSettings {
                Color.black.opacity(0.3)
                    .ignoresSafeArea()
                    .onTapGesture {
                        withAnimation(.easeInOut(duration: 0.3)) {
                            showCalendar = false
                            showSettings = false
                        }
                    }
            }
        }
        .overlay(alignment: .leading) {
            if showCalendar {
                CalendarDrawer(isPresented: $showCalendar)
                    .frame(width: UIScreen.main.bounds.width * 0.85)
                    .frame(maxHeight: .infinity)
                    .background(Tokens.bg)
                    .clipShape(UnevenRoundedRectangle(bottomTrailingRadius: 20, topTrailingRadius: 20))
                    .shadow(color: .black.opacity(0.15), radius: 10, x: 2)
                    .ignoresSafeArea()
                    .transition(.move(edge: .leading))
            }
        }
        .overlay(alignment: .trailing) {
            if showSettings {
                SettingsDrawer(isPresented: $showSettings)
                    .frame(width: UIScreen.main.bounds.width * 0.85)
                    .frame(maxHeight: .infinity)
                    .background(Tokens.bg)
                    .clipShape(UnevenRoundedRectangle(topLeadingRadius: 20, bottomLeadingRadius: 20))
                    .shadow(color: .black.opacity(0.15), radius: 10, x: -2)
                    .ignoresSafeArea()
                    .transition(.move(edge: .trailing))
            }
        }
        .onChange(of: speech.transcript) {
            if speech.isListening { inputText = speech.transcript }
        }
        .onAppear {
            Task {
                await petStore.fetchFromAPI()
                await location.requestLocation()
            }
        }
    }

    private var header: some View {
        HStack {
            Button { Haptics.light(); withAnimation(.easeInOut(duration: 0.3)) { showCalendar = true } } label: {
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

            Button { Haptics.light(); withAnimation(.easeInOut(duration: 0.3)) { showSettings = true } } label: {
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

    @ViewBuilder
    private func cardView(_ card: CardData) -> some View {
        switch card {
        case .record(let data):
            RecordCard(petName: data.pet_name, date: data.date, category: data.category) {
                withAnimation(.easeInOut(duration: 0.3)) { showCalendar = true }
            }
        case .map(let data):
            MapCard(items: data.items)
        case .email(let data):
            EmailCard(subject: data.subject, emailBody: data.body)
        }
    }

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
                    case .emergency(let e):
                        emergency = e
                    case .done(_, let sid):
                        chatStore.saveSession(sid)
                    }
                }
            } catch {
                if let idx = chatStore.messages.indices.last,
                   chatStore.messages[idx].content.isEmpty {
                    chatStore.messages[idx].content = "Sorry, something went wrong. Please try again."
                }
            }
            chatStore.save()
            isStreaming = false
        }
    }

    private func toggleMic() {
        if speech.isListening {
            speech.stopListening()
        } else {
            Task {
                let granted = await speech.requestPermission()
                if granted { speech.startListening() }
            }
        }
    }
}
