import SwiftUI
import GoogleSignIn

class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ app: UIApplication,
                     open url: URL,
                     options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        return GIDSignIn.sharedInstance.handle(url)
    }
}

@main
struct CozyPupApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var auth = AuthStore()
    @StateObject private var petStore = PetStore()
    @StateObject private var calendarStore = CalendarStore()
    @StateObject private var chatStore = ChatStore()
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
            .environmentObject(Lang.shared)
        }
    }
}
