import SwiftUI

@main
struct CozyPupApp: App {
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
                } else if petStore.pets.isEmpty {
                    OnboardingView()
                } else {
                    ChatView()
                }
            }
            .environmentObject(auth)
            .environmentObject(petStore)
            .environmentObject(calendarStore)
            .environmentObject(chatStore)
        }
    }
}
