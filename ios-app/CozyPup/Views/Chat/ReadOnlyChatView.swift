import SwiftUI

struct ReadOnlyChatView: View {
    let sessionId: String
    let title: String
    let onResume: ([ChatMessage]) -> Void

    @State private var messages: [ChatMessage] = []
    @State private var isLoading = true
    @State private var loadError = false

    var body: some View {
        VStack(spacing: 0) {
            if isLoading {
                Spacer()
                ProgressView()
                    .tint(Tokens.accent)
                Spacer()
            } else if loadError {
                Spacer()
                VStack(spacing: Tokens.spacing.sm) {
                    Image(systemName: "exclamationmark.circle")
                        .font(.system(size: 32))
                        .foregroundColor(Tokens.textTertiary)
                    Text("加载失败，请重试")
                        .font(Tokens.fontSubheadline)
                        .foregroundColor(Tokens.textSecondary)
                }
                Spacer()
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
                    onResume(messages)
                } label: {
                    Text("继续对话")
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
        .frame(maxWidth: .infinity)
        .background(Tokens.bg.ignoresSafeArea())
        .task { await loadMessages() }
    }

    private func loadMessages() async {
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

        do {
            let resp: ResumeResp = try await APIClient.shared.request(
                "POST", "/chat/sessions/\(sessionId)/resume"
            )
            messages = resp.messages.map { m in
                ChatMessage(
                    role: m.role,
                    content: m.content,
                    cards: m.cards ?? []
                )
            }
        } catch {
            print("[ReadOnlyChat] load failed: \(error)")
            loadError = true
        }
        isLoading = false
    }
}

// MARK: - Previews

#Preview("Loaded") {
    NavigationStack {
        ReadOnlyChatView(
            sessionId: "preview-session",
            title: "4月8日对话",
            onResume: { _ in }
        )
    }
}

#Preview("Loading") {
    NavigationStack {
        ReadOnlyChatView(
            sessionId: "preview-loading",
            title: "加载中...",
            onResume: { _ in }
        )
    }
}
