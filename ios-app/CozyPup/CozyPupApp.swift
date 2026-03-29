import SwiftUI
import GoogleSignIn

class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ app: UIApplication,
                     open url: URL,
                     options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        return GIDSignIn.sharedInstance.handle(url)
    }

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        return true
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
        }
    }
}

extension Notification.Name {
    static let openCalendarEvent = Notification.Name("openCalendarEvent")
}
