import SwiftUI
import AVFoundation

/// Fast QR scanner using AVCaptureSession + AVCaptureMetadataOutput.
/// Hardware-level detection — significantly faster than DataScannerViewController.
struct QRScannerView: UIViewControllerRepresentable {
    let onFound: (String) -> Void

    func makeUIViewController(context: Context) -> QRScannerViewController {
        let vc = QRScannerViewController()
        vc.onFound = onFound
        return vc
    }

    func updateUIViewController(_ uiViewController: QRScannerViewController, context: Context) {}
}

final class QRScannerViewController: UIViewController {
    var onFound: ((String) -> Void)?

    private let session = AVCaptureSession()
    private var previewLayer: AVCaptureVideoPreviewLayer?
    private var hasFound = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        setupSession()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer?.frame = view.bounds
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        if !session.isRunning {
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.session.startRunning()
            }
        }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        if session.isRunning {
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                self?.session.stopRunning()
            }
        }
    }

    private func setupSession() {
        guard let device = AVCaptureDevice.default(for: .video) else { return }

        do {
            let input = try AVCaptureDeviceInput(device: device)
            if session.canAddInput(input) {
                session.addInput(input)
            }

            let output = AVCaptureMetadataOutput()
            if session.canAddOutput(output) {
                session.addOutput(output)
                output.setMetadataObjectsDelegate(self, queue: DispatchQueue.main)
                output.metadataObjectTypes = [.qr]
            }

            let preview = AVCaptureVideoPreviewLayer(session: session)
            preview.videoGravity = .resizeAspectFill
            preview.frame = view.bounds
            view.layer.addSublayer(preview)
            self.previewLayer = preview
        } catch {
            print("[QRScanner] Failed to setup: \(error)")
        }
    }
}

extension QRScannerViewController: AVCaptureMetadataOutputObjectsDelegate {
    func metadataOutput(_ output: AVCaptureMetadataOutput,
                        didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        guard !hasFound,
              let metadataObject = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              metadataObject.type == .qr,
              let payload = metadataObject.stringValue else { return }

        hasFound = true
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        onFound?(payload)
    }
}

/// Wrapper that presents scanner and extracts a cozypup://share?token=xxx token.
struct PetShareScannerSheet: View {
    var onToken: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

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

            // Viewfinder guide overlay
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

                // Viewfinder frame
                RoundedRectangle(cornerRadius: 20)
                    .stroke(Color.white.opacity(0.8), lineWidth: 3)
                    .frame(width: 260, height: 260)

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
