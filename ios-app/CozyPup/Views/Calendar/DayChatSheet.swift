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
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView()
                        .tint(Tokens.accent)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if isEmpty {
                    VStack(spacing: Tokens.spacing.md) {
                        Image(systemName: "bubble.left.and.bubble.right")
                            .font(.largeTitle)
                            .foregroundColor(Tokens.textTertiary)
                        Text("当天没有对话记录")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.textSecondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        VStack(spacing: Tokens.spacing.sm) {
                            ForEach(messages) { msg in
                                ChatBubble(role: msg.role, content: msg.content)
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
                    .padding(Tokens.spacing.md)
                }
            }
            .background(Tokens.bg)
            .navigationTitle(formatDate(date))
            .navigationBarTitleDisplayMode(.inline)
        }
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
                ChatMessage(role: m.role, content: m.content, cards: m.cards ?? [])
            }
            isEmpty = messages.isEmpty
        } catch {
            print("[DayChatSheet] load failed: \(error)")
            isEmpty = true
        }
        isLoading = false
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
