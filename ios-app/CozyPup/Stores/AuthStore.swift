import SwiftUI
import GoogleSignIn
import AuthenticationServices

struct UserInfo: Codable, Equatable {
    let name: String
    let email: String
    let provider: String
    let avatarUrl: String?
}

@MainActor
class AuthStore: ObservableObject {
    @Published var isAuthenticated = false
    @Published var user: UserInfo?
    @Published var hasAcknowledgedDisclaimer = false
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var cachedAvatarImage: UIImage?

    private struct FullAuthResp: Decodable {
        let access_token: String; let refresh_token: String; let user_id: String
        let email: String?; let name: String?; let auth_provider: String?
        let avatar_url: String?
    }

    private let authKey = "cozypup_auth"
    private let disclaimerKey = "cozypup_disclaimer"

    init() { load() }

    func load() {
        if let data = UserDefaults.standard.data(forKey: authKey),
           let saved = try? JSONDecoder().decode(UserInfo.self, from: data) {
            user = saved
            isAuthenticated = true
            // Load cached avatar from disk immediately
            Task {
                await cacheAvatar(from: saved.avatarUrl)
                await validateSession()
            }
        }
        hasAcknowledgedDisclaimer = UserDefaults.standard.bool(forKey: disclaimerKey)
    }

    private func validateSession() async {
        struct UserResp: Decodable {
            let id: String
            let email: String
            let name: String?
            let avatar_url: String?
            let auth_provider: String
        }
        do {
            let me: UserResp = try await APIClient.shared.request("GET", "/auth/me")
            // Refresh cached user with latest avatar_url from server
            if let current = self.user {
                let updated = UserInfo(
                    name: me.name ?? current.name,
                    email: me.email,
                    provider: me.auth_provider,
                    avatarUrl: me.avatar_url ?? current.avatarUrl
                )
                self.user = updated
                if let data = try? JSONEncoder().encode(updated) {
                    UserDefaults.standard.set(data, forKey: authKey)
                }
                await cacheAvatar(from: updated.avatarUrl)
            }
        } catch {
            isAuthenticated = false
        }
    }

    // MARK: - Google Sign-In

    private static let googleClientID = "496617144117-73j9krtarupr8as09cka2tg06sn4cke8.apps.googleusercontent.com"

    func loginWithGoogle() {
        errorMessage = nil

        let config = GIDConfiguration(clientID: Self.googleClientID)
        GIDSignIn.sharedInstance.configuration = config

        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let rootVC = windowScene.windows.first?.rootViewController else {
            errorMessage = "Cannot find root view controller"
            return
        }

        Task {
            do {
                let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: rootVC)
                // Show loading only after Google sheet dismisses
                isLoading = true
                guard let idToken = result.user.idToken?.tokenString else {
                    errorMessage = "Failed to get Google ID token"
                    isLoading = false
                    return
                }

                struct AuthBody: Encodable { let id_token: String }

                let resp: FullAuthResp = try await APIClient.shared.authRequest(
                    "/auth/google", body: AuthBody(id_token: idToken)
                )
                await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)
                await saveUserFromResp(resp, fallbackProvider: "google")
            } catch {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }

    // MARK: - Apple Sign-In

    func handleAppleSignIn(result: Result<ASAuthorization, Error>) {
        isLoading = true
        errorMessage = nil

        switch result {
        case .success(let auth):
            guard let credential = auth.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let idToken = String(data: tokenData, encoding: .utf8) else {
                errorMessage = "Failed to get Apple ID token"
                isLoading = false
                return
            }

            Task {
                do {
                    struct AuthBody: Encodable { let id_token: String }

                    let resp: FullAuthResp = try await APIClient.shared.authRequest(
                        "/auth/apple", body: AuthBody(id_token: idToken)
                    )
                    await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)
                    await saveUserFromResp(resp, fallbackProvider: "apple")
                } catch {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }

        case .failure(let error):
            if (error as NSError).code != ASAuthorizationError.canceled.rawValue {
                errorMessage = error.localizedDescription
            }
            isLoading = false
        }
    }

    // MARK: - Dev auth (simulator only)

    #if targetEnvironment(simulator)
    func loginDev() {
        isLoading = true
        Task {
            do {
                struct DevAuthBody: Encodable { let name: String; let email: String }

                let resp: FullAuthResp = try await APIClient.shared.authRequest(
                    "/auth/dev", body: DevAuthBody(name: "Dev User", email: "dev@cozypup.app")
                )
                await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)
                await saveUserFromResp(resp, fallbackProvider: "dev")
            } catch {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }
    #endif

    // MARK: - Helpers

    /// Auth response includes user info — fallback to /auth/me if fields are missing (old backend)
    private func saveUserFromResp(_ resp: FullAuthResp, fallbackProvider: String) async {
        if let email = resp.email, !email.isEmpty {
            // New backend: user info included in auth response
            let userInfo = UserInfo(
                name: resp.name ?? "User",
                email: email,
                provider: resp.auth_provider ?? fallbackProvider,
                avatarUrl: resp.avatar_url
            )
            saveUser(userInfo)
        } else {
            // Old backend fallback: fetch from /auth/me
            await fetchUserFromMe(fallbackProvider: fallbackProvider)
        }
        isLoading = false
        // Register push in background — don't block login
        Task { await PushManager.shared.requestPermissionAndRegister() }
    }

    private func fetchUserFromMe(fallbackProvider: String) async {
        struct UserResp: Decodable {
            let id: String
            let email: String
            let name: String?
            let avatar_url: String?
            let auth_provider: String
        }
        do {
            let me: UserResp = try await APIClient.shared.request("GET", "/auth/me")
            saveUser(UserInfo(name: me.name ?? "User", email: me.email, provider: me.auth_provider, avatarUrl: me.avatar_url))
        } catch {
            print("fetchUserFromMe failed: \(error)")
            saveUser(UserInfo(name: "User", email: "", provider: fallbackProvider, avatarUrl: nil))
        }
    }

    private func saveUser(_ userInfo: UserInfo) {
        self.user = userInfo
        self.isAuthenticated = true
        if let data = try? JSONEncoder().encode(userInfo) {
            UserDefaults.standard.set(data, forKey: authKey)
        }
    }

    // MARK: - Logout

    func logout() {
        GIDSignIn.sharedInstance.signOut()
        isAuthenticated = false
        user = nil
        hasAcknowledgedDisclaimer = false
        UserDefaults.standard.removeObject(forKey: authKey)
        UserDefaults.standard.removeObject(forKey: disclaimerKey)
        // Clear all cached data from other stores
        UserDefaults.standard.removeObject(forKey: "cozypup_pets")
        UserDefaults.standard.removeObject(forKey: "cozypup_calendar")
        UserDefaults.standard.removeObject(forKey: "cozypup_chat_messages")
        UserDefaults.standard.removeObject(forKey: "cozypup_chat_session")
        clearAvatarCache()
        Task { await APIClient.shared.clearTokens() }
    }

    func acknowledgeDisclaimer() {
        hasAcknowledgedDisclaimer = true
        UserDefaults.standard.set(true, forKey: disclaimerKey)
    }

    // MARK: - User mutations

    /// Update the in-memory + cached UserInfo with a new name. Caller is
    /// responsible for the backend PATCH.
    func updateName(_ name: String) {
        guard let current = user else { return }
        let updated = UserInfo(name: name, email: current.email, provider: current.provider, avatarUrl: current.avatarUrl)
        self.user = updated
        if let data = try? JSONEncoder().encode(updated) {
            UserDefaults.standard.set(data, forKey: authKey)
        }
    }

    /// Update the in-memory + cached UserInfo with a new avatar URL.
    func updateAvatarURL(_ url: String) {
        guard let current = user else { return }
        let updated = UserInfo(name: current.name, email: current.email, provider: current.provider, avatarUrl: url)
        self.user = updated
        if let data = try? JSONEncoder().encode(updated) {
            UserDefaults.standard.set(data, forKey: authKey)
        }
        // Re-cache locally
        Task { await cacheAvatar(from: url) }
    }

    // MARK: - Avatar cache

    private static var avatarCachePath: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("user_avatar.jpg")
    }

    /// Download avatar from URL and cache to disk
    func cacheAvatar(from urlString: String?) async {
        guard let urlString, !urlString.isEmpty, let url = URL(string: urlString) else {
            cachedAvatarImage = nil
            return
        }
        // Check disk cache first
        if let data = try? Data(contentsOf: Self.avatarCachePath),
           let image = UIImage(data: data) {
            cachedAvatarImage = image
        }
        // Download fresh copy in background
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            if let image = UIImage(data: data) {
                try? data.write(to: Self.avatarCachePath)
                cachedAvatarImage = image
            }
        } catch {
            print("[AuthStore] avatar cache failed: \(error)")
        }
    }

    /// Set avatar from local UIImage (after PhotosPicker upload)
    func setCachedAvatar(_ image: UIImage) {
        cachedAvatarImage = image
        if let data = image.jpegData(compressionQuality: 0.8) {
            try? data.write(to: Self.avatarCachePath)
        }
    }

    private func clearAvatarCache() {
        cachedAvatarImage = nil
        try? FileManager.default.removeItem(at: Self.avatarCachePath)
    }
}
