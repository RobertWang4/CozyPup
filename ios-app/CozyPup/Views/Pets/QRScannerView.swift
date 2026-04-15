import SwiftUI
import AVFoundation
import PhotosUI
import CoreImage
import UIKit

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

/// Decode a QR code from a UIImage (used for "Pick from Photos" flow).
/// Returns the string payload or nil if no QR is found.
enum QRDecoder {
    static func decode(_ image: UIImage) -> String? {
        guard let ciImage = CIImage(image: image) else { return nil }
        let detector = CIDetector(
            ofType: CIDetectorTypeQRCode,
            context: nil,
            options: [CIDetectorAccuracy: CIDetectorAccuracyHigh]
        )
        let features = detector?.features(in: ciImage) ?? []
        for feature in features {
            if let qr = feature as? CIQRCodeFeature, let msg = qr.messageString {
                return msg
            }
        }
        return nil
    }
}

/// Reusable full-screen QR scanner sheet. Name kept for back-compat with
/// existing call sites — it now passes *any* QR payload through to the
/// caller, who is responsible for deciding what kind of QR it is
/// (pet share token, family invite URL, etc).
struct PetShareScannerSheet: View {
    var onToken: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var pickerItem: PhotosPickerItem?
    @State private var photoError: String?
    @ObservedObject private var lang = Lang.shared

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            QRScannerView { payload in
                onToken(payload)
                dismiss()
            }
            .ignoresSafeArea()

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

                VStack(spacing: 12) {
                    if let photoError {
                        Text(photoError)
                            .font(Tokens.fontCaption)
                            .foregroundColor(.white)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(Tokens.red.opacity(0.85))
                            .cornerRadius(8)
                    }

                    Text(lang.isZh ? "将二维码对准取景框" : "Point at a QR code")
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, Tokens.spacing.md)
                        .padding(.vertical, Tokens.spacing.sm)
                        .background(Color.black.opacity(0.5))
                        .cornerRadius(Tokens.radiusSmall)

                    // "From Photos" — for forwarded screenshots
                    PhotosPicker(
                        selection: $pickerItem,
                        matching: .images,
                        photoLibrary: .shared()
                    ) {
                        HStack(spacing: 6) {
                            Image(systemName: "photo.on.rectangle")
                                .font(.system(size: 14, weight: .semibold))
                            Text(lang.isZh ? "从相册选图" : "Pick from Photos")
                                .font(Tokens.fontSubheadline.weight(.semibold))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 12)
                        .background(Color.white.opacity(0.18))
                        .cornerRadius(100)
                        .overlay(
                            RoundedRectangle(cornerRadius: 100)
                                .stroke(Color.white.opacity(0.4), lineWidth: 1)
                        )
                    }
                }
                .padding(.bottom, Tokens.spacing.xl)
            }
        }
        .onChange(of: pickerItem) { _, newItem in
            guard let newItem else { return }
            Task { await handlePickedPhoto(newItem) }
        }
    }

    @MainActor
    private func handlePickedPhoto(_ item: PhotosPickerItem) async {
        photoError = nil
        defer { pickerItem = nil }
        do {
            guard let data = try await item.loadTransferable(type: Data.self),
                  let uiImage = UIImage(data: data) else {
                photoError = lang.isZh ? "无法读取图片" : "Couldn't load image"
                return
            }
            if let payload = QRDecoder.decode(uiImage) {
                onToken(payload)
                dismiss()
            } else {
                photoError = lang.isZh ? "没有找到二维码" : "No QR code found"
            }
        } catch {
            photoError = lang.isZh ? "读取失败" : "Failed to read"
        }
    }
}
