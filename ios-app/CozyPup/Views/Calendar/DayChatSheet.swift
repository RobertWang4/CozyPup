import SwiftUI

/// Shows read-only chat history for a specific date.
/// Used from the calendar day detail page's history button.
struct DayChatSheet: View {
    @EnvironmentObject var chatStore: ChatStore
    @Environment(\.dismiss) private var dismiss
    let date: String  // YYYY-MM-DD

    @State private var messages: [ChatMessage] = []
    @State private var isLoading = true
    @State private var isEmpty = false
    @State private var sessionId: String?

    var body: some View {
        VStack(spacing: 0) {
            // Drag handle + title
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            Text(formatDate(date))
                .font(Tokens.fontHeadline)
                .foregroundColor(Tokens.text)
                .padding(.vertical, Tokens.spacing.md)

            if isLoading {
                Spacer()
                ProgressView()
                    .tint(Tokens.accent)
                Spacer()
            } else if isEmpty {
                Spacer()
                VStack(spacing: Tokens.spacing.md) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.largeTitle)
                        .foregroundColor(Tokens.textTertiary)
                    Text("当天没有对话记录")
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.textSecondary)
                }
                Spacer()
            } else {
                ScrollView {
                    VStack(spacing: Tokens.spacing.sm) {
                        ForEach(messages) { msg in
                            VStack(spacing: Tokens.spacing.xs) {
                                if let urls = msg.imageUrls, !urls.isEmpty {
                                    HStack {
                                        if msg.role == .user { Spacer() }
                                        photoGridFromUrls(urls)
                                        if msg.role != .user { Spacer() }
                                    }
                                }
                                if !msg.content.isEmpty {
                                    ChatBubble(role: msg.role, content: msg.content)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.md)
                }

                Button {
                    Haptics.light()
                    Task {
                        await chatStore.switchToSession(id: sessionId ?? "", messages: messages)
                    }
                    dismiss()
                } label: {
                    Text("回到这天的对话")
                        .font(Tokens.fontBody.weight(.semibold))
                        .foregroundColor(Tokens.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Tokens.accent)
                        .cornerRadius(Tokens.radiusSmall)
                }
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.bottom, Tokens.spacing.md)
            }
        }
        .frame(maxWidth: .infinity)
        .background(Tokens.bg.ignoresSafeArea())
        .task { await loadMessages() }
    }

    private func loadMessages() async {
        // First find the session for this date from sessions list
        struct SessionItem: Decodable {
            let id: String
            let session_date: String
        }

        do {
            let sessions: [SessionItem] = try await APIClient.shared.request(
                "GET", "/chat/sessions"
            )
            guard let session = sessions.first(where: { $0.session_date == date }) else {
                isEmpty = true
                isLoading = false
                return
            }
            sessionId = session.id

            // Load messages for that session
            struct MessageItem: Decodable {
                let id: String
                let role: MessageRole
                let content: String
                let cards: [CardData]?
                let image_urls: [String]?
                let created_at: String
            }
            struct ResumeResp: Decodable {
                let session_id: String
                let messages: [MessageItem]
            }

            let resp: ResumeResp = try await APIClient.shared.request(
                "POST", "/chat/sessions/\(session.id)/resume"
            )
            messages = resp.messages.map { m in
                ChatMessage(role: m.role, content: m.content, cards: m.cards ?? [], imageUrls: m.image_urls)
            }
            isEmpty = messages.isEmpty
        } catch {
            print("[DayChatSheet] load failed: \(error)")
            isEmpty = true
        }
        isLoading = false
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
                        image.resizable().scaledToFill()
                    } placeholder: {
                        Tokens.placeholderBg
                    }
                    .frame(width: size, height: size)
                    .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
                }
            }
        }
    }

    private func formatDate(_ dateStr: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        guard let d = formatter.date(from: dateStr) else { return dateStr }
        formatter.dateFormat = "M月d日对话"
        return formatter.string(from: d)
    }
}

#Preview {
    DayChatSheet(date: "2026-04-10")
}
