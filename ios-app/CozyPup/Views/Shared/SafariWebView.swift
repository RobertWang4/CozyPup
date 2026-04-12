import SwiftUI
import SafariServices

/// Presents a URL in an in-app Safari view controller.
struct SafariWebView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let config = SFSafariViewController.Configuration()
        config.barCollapsingEnabled = true
        let vc = SFSafariViewController(url: url, configuration: config)
        vc.preferredBarTintColor = UIColor(Tokens.bg)
        vc.preferredControlTintColor = UIColor(Tokens.accent)
        return vc
    }

    func updateUIViewController(_ uiViewController: SFSafariViewController, context: Context) {}
}

#Preview {
    SafariWebView(url: URL(string: "https://apple.com")!)
}
