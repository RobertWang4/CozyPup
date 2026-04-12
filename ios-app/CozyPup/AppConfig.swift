import Foundation

/// Single source of truth for hardcoded URLs, emails, and external IDs.
/// Placeholders marked `TBD` must be filled before the first App Store submission.
enum AppConfig {
    /// Support email used by Contact Support and Report a Problem.
    /// Replace before submission.
    static let supportEmail = "support@cozypup.app"  // TBD

    /// Privacy Policy — opened in SFSafariViewController.
    static let privacyPolicyURL = "https://cozypup.app/privacy"  // TBD

    /// Terms of Use — required by Apple for auto-renewable subscriptions.
    /// Opened in SFSafariViewController.
    static let termsOfUseURL = "https://cozypup.app/terms"  // TBD

    /// App Store share URL. When empty, the Share button is hidden.
    /// Fill at the time of first App Store submission.
    static let appStoreURL = ""  // TBD

    /// Bundle version + build, read from Info.plist.
    static var versionString: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "v\(version) (\(build))"
    }

    /// Whether Share CozyPup button should be shown.
    static var isShareEnabled: Bool { !appStoreURL.isEmpty }
}
