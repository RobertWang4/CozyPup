import Foundation
import UserNotifications
import UIKit

actor PushManager {
    static let shared = PushManager()

    private init() {}

    /// Request notification permission and register for remote notifications.
    /// Call after successful login.
    func requestPermissionAndRegister() async {
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound, .badge])
            guard granted else {
                print("[Push] Permission denied by user")
                return
            }
            await MainActor.run {
                UIApplication.shared.registerForRemoteNotifications()
            }
        } catch {
            print("[Push] Permission request failed: \(error.localizedDescription)")
        }
    }

    /// Send the device token to the backend.
    func registerToken(_ token: String) async {
        struct DeviceBody: Encodable {
            let token: String
            let platform: String
        }
        struct DeviceResp: Decodable {
            let id: String
        }
        do {
            let _: DeviceResp = try await APIClient.shared.request(
                "POST", "/devices",
                body: DeviceBody(token: token, platform: "ios")
            )
            print("[Push] Token registered with backend")
        } catch {
            print("[Push] Failed to register token: \(error.localizedDescription)")
        }
    }

    /// Unregister the device token on logout.
    func unregisterToken() async {
        // Clear badge
        await MainActor.run {
            UIApplication.shared.applicationIconBadgeNumber = 0
        }
    }
}
