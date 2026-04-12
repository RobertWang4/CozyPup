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
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if saved.isEmpty && recent.isEmpty {
                    VStack(spacing: Tokens.spacing.md) {
                        Image(systemName: "bookmark.slash")
                            .font(.largeTitle)
                            .foregroundColor(Tokens.textTertiary)
                        Text("还没有保存的对话")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.textSecondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List {
                        if !saved.isEmpty {
                            Section {
                                ForEach(saved) { item in
                                    Button { selectedSession = item } label: {
                                        HStack {
                                            Text(item.title ?? "对话")
                                                .font(Tokens.fontBody)
                                                .foregroundColor(Tokens.text)
                                            Spacer()
                                            Text(item.session_date)
                                                .font(Tokens.fontCaption)
                                                .foregroundColor(Tokens.textSecondary)
                                        }
                                    }
                                }
                            } header: {
                                Label("已保存", systemImage: "bookmark.fill")
                            }
                        }

                        if !recent.isEmpty {
                            Section {
                                ForEach(recent) { item in
                                    Button { selectedSession = item } label: {
                                        HStack {
                                            Text(item.session_date)
                                                .font(Tokens.fontBody)
                                                .foregroundColor(Tokens.text)
                                            Spacer()
                                            if let exp = item.expires_at {
                                                Text(formatExpiry(exp))
                                                    .font(Tokens.fontCaption)
                                                    .foregroundColor(Tokens.textTertiary)
                                            }
                                        }
                                    }
                                }
                            } header: {
                                Label("最近对话", systemImage: "clock.arrow.circlepath")
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                    .scrollContentBackground(.hidden)
                }
            }
            .background(Tokens.bg)
            .navigationTitle("历史对话")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { onDismiss() } label: {
                        Image(systemName: "xmark")
                            .foregroundColor(Tokens.textSecondary)
                    }
                }
            }
            .navigationDestination(item: $selectedSession) { item in
                ReadOnlyChatView(
                    sessionId: item.id,
                    title: item.title ?? item.session_date,
                    onResume: { messages in
                        onResume(item.id, messages)
                    }
                )
            }
        }
        .task { await loadSessions() }
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
