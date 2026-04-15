import Foundation

/// Single source of truth for hardcoded URLs, emails, and external IDs.
/// Placeholders marked `TBD` must be filled before the first App Store submission.
enum AppConfig {
    /// Support email used by Contact Support and Report a Problem.
    /// Temporary: personal Gmail until `support@cozypup.app` is set up
    /// via Cloudflare Email Routing once the domain is registered.
    static let supportEmail = "cozypup2026@gmail.com"

    /// Base URL for legal pages served by the FastAPI backend at /legal/*.
    /// Will switch to `https://cozypup.app/legal/*` once the domain is live.
    private static let legalBase = "https://backend-601329501885.northamerica-northeast1.run.app/legal"

    /// Privacy Policy — opened in SFSafariViewController.
    static let privacyPolicyURL = "\(legalBase)/privacy"

    /// Terms of Use — required by Apple for auto-renewable subscriptions.
    /// Opened in SFSafariViewController.
    static let termsOfUseURL = "\(legalBase)/terms"

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
