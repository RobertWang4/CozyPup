import Foundation

@MainActor
class ChatStore: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var sessionId: String?

    private let messagesKey = "cozypup_chat_messages"
    private let sessionKey = "cozypup_chat_session"
    private let welcomeKey = "cozypup_has_seen_welcome"
    private let messageCountKey = "cozypup_total_message_count"
    private let softPaywallCountKey = "cozypup_soft_paywall_count"
    private let softPaywallDateKey = "cozypup_soft_paywall_date"

    var hasSeenWelcome: Bool {
        get { UserDefaults.standard.bool(forKey: welcomeKey) }
        set { UserDefaults.standard.set(newValue, forKey: welcomeKey) }
    }

    var totalMessageCount: Int {
        get { UserDefaults.standard.integer(forKey: messageCountKey) }
        set { UserDefaults.standard.set(newValue, forKey: messageCountKey) }
    }

    var softPaywallShownCount: Int {
        get { UserDefaults.standard.integer(forKey: softPaywallCountKey) }
        set { UserDefaults.standard.set(newValue, forKey: softPaywallCountKey) }
    }

    var lastSoftPaywallDate: Date? {
        get { UserDefaults.standard.object(forKey: softPaywallDateKey) as? Date }
        set { UserDefaults.standard.set(newValue, forKey: softPaywallDateKey) }
    }

    func incrementMessageCount() {
        totalMessageCount += 1
    }

    init() { load() }

    func load() {
        if let data = UserDefaults.standard.data(forKey: messagesKey),
           let saved = try? JSONDecoder().decode([ChatMessage].self, from: data) {
            messages = saved
        }
        if let data = UserDefaults.standard.data(forKey: sessionKey),
           let session = try? JSONDecoder().decode(SessionData.self, from: data) {
            let today = Self.todayStr()
            if session.date == today {
                sessionId = session.id
            } else {
                clear()
            }
        }
    }

    func save() {
        if let data = try? JSONEncoder().encode(messages) {
            UserDefaults.standard.set(data, forKey: messagesKey)
        }
    }

    func saveSession(_ id: String) {
        sessionId = id
        let session = SessionData(id: id, date: Self.todayStr())
        if let data = try? JSONEncoder().encode(session) {
            UserDefaults.standard.set(data, forKey: sessionKey)
        }
    }

    func clear() {
        messages = []
        sessionId = nil
        UserDefaults.standard.removeObject(forKey: messagesKey)
        UserDefaults.standard.removeObject(forKey: sessionKey)
    }

    private static func todayStr() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Date())
    }

    private struct SessionData: Codable {
        let id: String
        let date: String
    }
}
