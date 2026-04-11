import SwiftUI
import GoogleSignIn
import UserNotifications

class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ app: UIApplication,
                     open url: URL,
                     options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        return GIDSignIn.sharedInstance.handle(url)
    }

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    // MARK: - Push notification token

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        Task {
            await PushManager.shared.registerToken(token)
        }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("[Push] Failed to register: \(error.localizedDescription)")
    }

    // MARK: - Show notification when app is in foreground

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }

    // MARK: - Handle notification tap

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let userInfo = response.notification.request.content.userInfo
        if let eventId = userInfo["event_id"] as? String {
            NotificationCenter.default.post(
                name: .openCalendarEvent,
                object: nil,
                userInfo: ["eventId": eventId]
            )
        }
        completionHandler()
    }
}

@main
struct CozyPupApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var auth = AuthStore()
    @StateObject private var petStore = PetStore()
    @StateObject private var calendarStore = CalendarStore()
    @StateObject private var chatStore = ChatStore()
    @StateObject private var dailyTaskStore = DailyTaskStore()
    @StateObject private var subscriptionStore = SubscriptionStore()
    var body: some Scene {
        WindowGroup {
            Group {
                if !auth.isAuthenticated {
                    LoginView()
                } else if !auth.hasAcknowledgedDisclaimer {
                    DisclaimerView()
                } else {
                    ChatView()
                }
            }
            .animation(.easeInOut(duration: 0.3), value: auth.isAuthenticated)
            .animation(.easeInOut(duration: 0.3), value: auth.hasAcknowledgedDisclaimer)
            .environmentObject(auth)
            .environmentObject(petStore)
            .environmentObject(calendarStore)
            .environmentObject(chatStore)
            .environmentObject(dailyTaskStore)
            .environmentObject(subscriptionStore)
            .environmentObject(Lang.shared)
            .onOpenURL { url in
                guard url.scheme == "cozypup",
                      url.host == "calendar",
                      url.pathComponents.count >= 3,
                      url.pathComponents[1] == "event" else { return }
                let eventId = url.pathComponents[2]
                NotificationCenter.default.post(
                    name: .openCalendarEvent,
                    object: nil,
                    userInfo: ["eventId": eventId]
                )
            }
            .task {
                if auth.isAuthenticated {
                    await subscriptionStore.loadStatus()
                    await subscriptionStore.loadProducts()
                }
            }
        }
    }
}

extension Notification.Name {
    static let openCalendarEvent = Notification.Name("openCalendarEvent")
}
