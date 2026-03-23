import SwiftUI
import FirebaseAuth
import GoogleSignIn
import FirebaseCore

struct UserInfo: Codable, Equatable {
    let name: String
    let email: String
    let provider: String
}

@MainActor
class AuthStore: ObservableObject {
    @Published var isAuthenticated = false
    @Published var user: UserInfo?
    @Published var hasAcknowledgedDisclaimer = false
    @Published var isLoading = false
    @Published var errorMessage: String?

    // Registration flow state
    @Published var pendingRegistration: PendingRegistration?

    struct PendingRegistration {
        let email: String
        let password: String
        let name: String?
    }

    private let authKey = "cozypup_auth"
    private let disclaimerKey = "cozypup_disclaimer"

    init() { load() }

    func load() {
        if let data = UserDefaults.standard.data(forKey: authKey),
           let saved = try? JSONDecoder().decode(UserInfo.self, from: data) {
            user = saved
            isAuthenticated = true
            Task { await validateSession() }
        }
        hasAcknowledgedDisclaimer = UserDefaults.standard.bool(forKey: disclaimerKey)
    }

    private func validateSession() async {
        struct UserResp: Decodable { let id: String }
        do {
            let _: UserResp = try await APIClient.shared.request("GET", "/auth/me")
        } catch {
            if let firebaseUser = Auth.auth().currentUser {
                await loginWithFirebaseUser(firebaseUser)
            } else {
                isAuthenticated = false
            }
        }
    }

    // MARK: - Google Sign-In

    func loginWithGoogle() {
        isLoading = true
        errorMessage = nil

        guard let clientID = FirebaseApp.app()?.options.clientID else {
            errorMessage = "Firebase not configured"
            isLoading = false
            return
        }

        let config = GIDConfiguration(clientID: clientID)
        GIDSignIn.sharedInstance.configuration = config

        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let rootVC = windowScene.windows.first?.rootViewController else {
            errorMessage = "Cannot find root view controller"
            isLoading = false
            return
        }

        Task {
            do {
                let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: rootVC)
                guard let idToken = result.user.idToken?.tokenString else {
                    errorMessage = "Failed to get Google ID token"
                    isLoading = false
                    return
                }
                let credential = GoogleAuthProvider.credential(
                    withIDToken: idToken,
                    accessToken: result.user.accessToken.tokenString
                )
                let authResult = try await Auth.auth().signIn(with: credential)
                await loginWithFirebaseUser(authResult.user)
            } catch {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }

    // MARK: - Email + Password

    func loginWithEmail(email: String, password: String) {
        isLoading = true
        errorMessage = nil

        Task {
            do {
                struct LoginBody: Encodable { let email: String; let password: String }
                struct AuthResp: Decodable { let access_token: String; let refresh_token: String; let user_id: String }

                let resp: AuthResp = try await APIClient.shared.authRequest(
                    "/auth/email/login",
                    body: LoginBody(email: email, password: password)
                )
                await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)
                await fetchAndSaveUser(provider: "email")
            } catch APIError.badStatus(401) {
                errorMessage = "邮箱或密码错误"
                isLoading = false
            } catch {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }

    func registerWithEmail(email: String, password: String, name: String?) {
        pendingRegistration = PendingRegistration(email: email, password: password, name: name)
    }

    func completeRegistration(phoneNumber: String) {
        guard let reg = pendingRegistration else { return }
        isLoading = true
        errorMessage = nil

        Task {
            do {
                struct RegisterBody: Encodable {
                    let email: String; let password: String
                    let name: String?; let phone_number: String
                }
                struct AuthResp: Decodable { let access_token: String; let refresh_token: String; let user_id: String }

                let resp: AuthResp = try await APIClient.shared.authRequest(
                    "/auth/email/register",
                    body: RegisterBody(
                        email: reg.email, password: reg.password,
                        name: reg.name, phone_number: phoneNumber
                    )
                )
                await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)
                pendingRegistration = nil
                await fetchAndSaveUser(provider: "email")
            } catch APIError.badStatus(409) {
                errorMessage = "该邮箱已注册"
                isLoading = false
            } catch {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }

    // MARK: - Firebase token → backend

    private func loginWithFirebaseUser(_ firebaseUser: FirebaseAuth.User) async {
        do {
            let idToken = try await firebaseUser.getIDToken()

            struct FirebaseBody: Encodable { let id_token: String }
            struct AuthResp: Decodable { let access_token: String; let refresh_token: String; let user_id: String }

            let resp: AuthResp = try await APIClient.shared.authRequest(
                "/auth/firebase", body: FirebaseBody(id_token: idToken)
            )
            await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)
            await fetchAndSaveUser(provider: firebaseUser.providerData.first?.providerID ?? "firebase")
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    private func fetchAndSaveUser(provider: String) async {
        struct UserResp: Decodable { let id: String; let email: String; let name: String?; let auth_provider: String }
        do {
            let me: UserResp = try await APIClient.shared.request("GET", "/auth/me")
            let userInfo = UserInfo(name: me.name ?? "User", email: me.email, provider: me.auth_provider)
            self.user = userInfo
            self.isAuthenticated = true
            if let data = try? JSONEncoder().encode(userInfo) {
                UserDefaults.standard.set(data, forKey: authKey)
            }
        } catch {
            errorMessage = "Failed to fetch user info"
        }
        isLoading = false
    }

    // MARK: - Apple Sign-In (placeholder)

    func loginWithApple() {
        errorMessage = "Apple Sign-In requires an Apple Developer account. Coming soon!"
    }

    // MARK: - Dev auth (simulator only)

    #if targetEnvironment(simulator)
    func loginDev() {
        isLoading = true
        Task {
            do {
                struct DevAuthBody: Encodable { let name: String; let email: String }
                struct AuthResp: Decodable { let access_token: String; let refresh_token: String; let user_id: String }

                let resp: AuthResp = try await APIClient.shared.authRequest(
                    "/auth/dev", body: DevAuthBody(name: "Dev User", email: "dev@cozypup.app")
                )
                await APIClient.shared.setTokens(access: resp.access_token, refresh: resp.refresh_token)
                await fetchAndSaveUser(provider: "dev")
            } catch {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }
    #endif

    // MARK: - Logout

    func logout() {
        try? Auth.auth().signOut()
        GIDSignIn.sharedInstance.signOut()
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
