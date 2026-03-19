import SwiftUI

struct UserInfo: Codable, Equatable {
    let name: String
    let email: String
}

@MainActor
class AuthStore: ObservableObject {
    @Published var isAuthenticated = false
    @Published var user: UserInfo?
    @Published var hasAcknowledgedDisclaimer = false

    private let authKey = "cozypup_auth"
    private let disclaimerKey = "cozypup_disclaimer"

    init() { load() }

    func load() {
        if let data = UserDefaults.standard.data(forKey: authKey),
           let saved = try? JSONDecoder().decode(UserInfo.self, from: data) {
            user = saved
            isAuthenticated = true
        }
        hasAcknowledgedDisclaimer = UserDefaults.standard.bool(forKey: disclaimerKey)
    }

    func login(provider: String) {
        let mockUsers: [String: UserInfo] = [
            "apple": UserInfo(name: "Apple User", email: "user@icloud.com"),
            "google": UserInfo(name: "Google User", email: "user@gmail.com"),
        ]
        user = mockUsers[provider]
        isAuthenticated = true
        if let data = try? JSONEncoder().encode(user) {
            UserDefaults.standard.set(data, forKey: authKey)
        }
    }

    func logout() {
        isAuthenticated = false
        user = nil
        hasAcknowledgedDisclaimer = false
        UserDefaults.standard.removeObject(forKey: authKey)
        UserDefaults.standard.removeObject(forKey: disclaimerKey)
    }

    func acknowledgeDisclaimer() {
        hasAcknowledgedDisclaimer = true
        UserDefaults.standard.set(true, forKey: disclaimerKey)
    }
}
