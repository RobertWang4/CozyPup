import SwiftUI
import VisionKit

/// QR code scanner using iOS 17 DataScannerViewController.
/// Calls `onFound` with the scanned payload then dismisses.
struct QRScannerView: UIViewControllerRepresentable {
    let onFound: (String) -> Void

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let scanner = DataScannerViewController(
            recognizedDataTypes: [.barcode(symbologies: [.qr])],
            qualityLevel: .balanced,
            recognizesMultipleItems: false,
            isGuidanceEnabled: true,
            isHighlightingEnabled: true
        )
        scanner.delegate = context.coordinator
        try? scanner.startScanning()
        return scanner
    }

    func updateUIViewController(_ uiViewController: DataScannerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onFound: onFound) }

    class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let onFound: (String) -> Void
        var found = false

        init(onFound: @escaping (String) -> Void) {
            self.onFound = onFound
        }

        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            guard !found else { return }
            for item in addedItems {
                if case .barcode(let barcode) = item, let payload = barcode.payloadStringValue {
                    found = true
                    onFound(payload)
                    break
                }
            }
        }
    }
}

/// Wrapper that presents scanner and extracts a cozypup://share?token=xxx token.
struct PetShareScannerSheet: View {
    var onToken: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var isUnavailable = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if DataScannerViewController.isSupported && DataScannerViewController.isAvailable {
                QRScannerView { payload in
                    // payload: cozypup://share?token=xxx
                    if let url = URL(string: payload),
                       url.scheme == "cozypup",
                       url.host == "share",
                       let token = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                           .queryItems?.first(where: { $0.name == "token" })?.value {
                        onToken(token)
                        dismiss()
                    }
                }
                .ignoresSafeArea()
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "camera.fill")
                        .font(.system(size: 40))
                        .foregroundColor(.white)
                    Text("Scanner not available on this device")
                        .foregroundColor(.white)
                }
            }

            // Top bar with close button
            VStack {
                HStack {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 36, height: 36)
                            .background(Color.black.opacity(0.5))
                            .clipShape(Circle())
                    }
                    .padding(.leading, Tokens.spacing.md)
                    .padding(.top, Tokens.spacing.md)
                    Spacer()
                }

                Spacer()

                Text("Point at a CozyPup QR code")
                    .font(Tokens.fontSubheadline.weight(.medium))
                    .foregroundColor(.white)
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.sm)
                    .background(Color.black.opacity(0.5))
                    .cornerRadius(Tokens.radiusSmall)
                    .padding(.bottom, Tokens.spacing.xl)
            }
        }
    }
}
