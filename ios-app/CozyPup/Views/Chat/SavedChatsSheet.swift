import SwiftUI

struct SessionItem: Decodable, Identifiable {
    let id: String
    let title: String?
    let session_date: String
    let expires_at: String?
    let is_saved: Bool
    let message_count: Int
}

struct SavedChatsSheet: View {
    @EnvironmentObject var chatStore: ChatStore
    var onResume: (String, [ChatMessage]) -> Void
    var onDismiss: () -> Void

    @State private var saved: [SessionItem] = []
    @State private var recent: [SessionItem] = []
    @State private var isLoading = true
    @State private var selectedSession: SessionItem?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button { onDismiss() } label: {
                    Image(systemName: "xmark")
                        .font(Tokens.fontSubheadline)
                        .foregroundColor(Tokens.textSecondary)
                        .frame(width: 28, height: 28)
                        .background(Tokens.surface)
                        .clipShape(Circle())
                }
                Spacer()
                Text("历史对话")
                    .font(Tokens.fontHeadline)
                    .foregroundColor(Tokens.text)
                Spacer()
                // Balance the close button
                Color.clear.frame(width: 28, height: 28)
            }
            .padding(.horizontal, Tokens.spacing.md)
            .padding(.top, Tokens.spacing.md)
            .padding(.bottom, Tokens.spacing.sm)

            if isLoading {
                Spacer()
                ProgressView().tint(Tokens.accent)
                Spacer()
            } else if saved.isEmpty && recent.isEmpty {
                Spacer()
                VStack(spacing: Tokens.spacing.md) {
                    Image(systemName: "bookmark.slash")
                        .font(.largeTitle)
                        .foregroundColor(Tokens.textTertiary)
                    Text("还没有保存的对话")
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.textSecondary)
                }
                Spacer()
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: Tokens.spacing.lg) {
                        if !saved.isEmpty {
                            sectionView(
                                title: "已保存",
                                icon: "bookmark.fill",
                                items: saved,
                                showTitle: true
                            )
                        }
                        if !recent.isEmpty {
                            sectionView(
                                title: "最近对话",
                                icon: "clock.arrow.circlepath",
                                items: recent,
                                showTitle: false
                            )
                        }
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.sm)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .background(Tokens.bg.ignoresSafeArea())
        .sheet(item: $selectedSession) { item in
            ReadOnlyChatView(
                sessionId: item.id,
                title: item.title ?? item.session_date,
                onResume: { messages in
                    onResume(item.id, messages)
                }
            )
            .presentationDetents([.large])
        }
        .task { await loadSessions() }
    }

    private func sectionView(title: String, icon: String, items: [SessionItem], showTitle: Bool) -> some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            Label(title, systemImage: icon)
                .font(Tokens.fontCaption.weight(.semibold))
                .foregroundColor(Tokens.textSecondary)

            VStack(spacing: 0) {
                ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                    Button { selectedSession = item } label: {
                        HStack {
                            Text(showTitle ? (item.title ?? "对话") : item.session_date)
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                            Spacer()
                            Text(showTitle ? item.session_date : formatExpiry(item.expires_at ?? ""))
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                        .padding(.vertical, Tokens.spacing.sm + Tokens.spacing.xs)
                        .padding(.horizontal, Tokens.spacing.md)
                    }
                    if index < items.count - 1 {
                        Divider().padding(.leading, Tokens.spacing.md)
                    }
                }
            }
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
        }
    }

    private func loadSessions() async {
        struct Resp: Decodable {
            let saved: [SessionItem]
            let recent: [SessionItem]
        }
        do {
            let resp: Resp = try await APIClient.shared.request("GET", "/chat/sessions/saved")
            saved = resp.saved
            recent = resp.recent
        } catch {
            print("[SavedChats] load failed: \(error)")
        }
        isLoading = false
    }

    private func formatExpiry(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: iso) else { return "" }
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "HH:mm"
        return "\(timeFormatter.string(from: date))被替代"
    }
}

extension SessionItem: Hashable {
    static func == (lhs: SessionItem, rhs: SessionItem) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

#Preview {
    SavedChatsSheet(
        onResume: { _, _ in },
        onDismiss: {}
    )
    .environmentObject(ChatStore())
}
