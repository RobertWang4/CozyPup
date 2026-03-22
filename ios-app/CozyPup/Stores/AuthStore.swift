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
    @Published var isLoading = false

    private let authKey = "cozypup_auth"
    private let disclaimerKey = "cozypup_disclaimer"

    init() { load() }

    func load() {
        if let data = UserDefaults.standard.data(forKey: authKey),
           let saved = try? JSONDecoder().decode(UserInfo.self, from: data) {
            user = saved
            isAuthenticated = true
            // Validate token on launch — re-auth if expired
            Task { await validateSession() }
        }
        hasAcknowledgedDisclaimer = UserDefaults.standard.bool(forKey: disclaimerKey)
    }

    /// Check that the stored token still works; if not, silently re-authenticate.
    private func validateSession() async {
        struct UserResp: Decodable { let id: String }

        do {
            let _: UserResp = try await APIClient.shared.request("GET", "/auth/me")
            // Token is valid — nothing to do
        } catch {
            // Token expired or missing — try silent re-login with stored user info
            guard let user else {
                isAuthenticated = false
                return
            }
            await silentReauth(user: user)
        }
    }

    /// Re-authenticate using dev auth with existing user info.
    private func silentReauth(user info: UserInfo) async {
        struct DevAuthBody: Encodable { let name: String; let email: String }
        struct AuthResp: Decodable { let access_token: String; let refresh_token: String }

        do {
            let resp: AuthResp = try await APIClient.shared.authRequest(
                "/auth/dev", body: DevAuthBody(name: info.name, email: info.email)
            )
            await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)
        } catch {
            // Re-auth failed — force user to login screen
            isAuthenticated = false
            self.user = nil
            UserDefaults.standard.removeObject(forKey: authKey)
            Task { await APIClient.shared.clearTokens() }
        }
    }

    func login(provider: String) {
        isLoading = true
        Task {
            do {
                // Use dev auth endpoint
                struct DevAuthBody: Encodable {
                    let name: String
                    let email: String
                }

                struct AuthResp: Decodable {
                    let access_token: String
                    let refresh_token: String
                    let user_id: String
                }

                let body = DevAuthBody(
                    name: provider == "apple" ? "Apple User" : "Google User",
                    email: provider == "apple" ? "user@icloud.com" : "user@gmail.com"
                )

                let resp: AuthResp = try await APIClient.shared.authRequest("/auth/dev", body: body)
                await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)

                // Fetch user info
                struct UserResp: Decodable {
                    let id: String
                    let email: String
                    let name: String?
                    let auth_provider: String
                }

                let me: UserResp = try await APIClient.shared.request("GET", "/auth/me")
                let userInfo = UserInfo(name: me.name ?? "User", email: me.email)

                self.user = userInfo
                self.isAuthenticated = true
                if let data = try? JSONEncoder().encode(userInfo) {
                    UserDefaults.standard.set(data, forKey: authKey)
                }
            } catch {
                print("Login failed: \(error)")
            }
            self.isLoading = false
        }
    }

    func logout() {
        isAuthenticated = false
        user = nil
        hasAcknowledgedDisclaimer = false
        UserDefaults.standard.removeObject(forKey: authKey)
        UserDefaults.standard.removeObject(forKey: disclaimerKey)
        Task { await APIClient.shared.clearTokens() }
    }

    func acknowledgeDisclaimer() {
        hasAcknowledgedDisclaimer = true
        UserDefaults.standard.set(true, forKey: disclaimerKey)
    }
}
