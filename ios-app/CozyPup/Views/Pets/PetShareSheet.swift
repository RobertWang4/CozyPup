import SwiftUI
import CoreImage.CIFilterBuiltins

struct PetShareSheet: View {
    let pet: Pet
    var onDismiss: () -> Void

    @State private var token: String?
    @State private var expiresAt: Date?
    @State private var isLoading = true
    @State private var cardVisible = false
    @State private var showShareActivity = false
    @State private var shareItems: [Any] = []

    var body: some View {
        ZStack {
            // Transparent backdrop — tap to dismiss
            Color.clear
                .contentShape(Rectangle())
                .ignoresSafeArea()
                .onTapGesture { dismiss() }

            // Floating card (not attached to any edge)
            VStack(spacing: 0) {
                // Pet header
                HStack(spacing: Tokens.spacing.sm) {
                    petAvatar
                        .frame(width: 52, height: 52)
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 2) {
                        Text(pet.name)
                            .font(Tokens.fontTitle.weight(.semibold))
                            .foregroundColor(Tokens.text)
                        if !pet.breed.isEmpty {
                            Text(pet.breed)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                    }

                    Spacer()

                    Image(systemName: "pawprint.fill")
                        .foregroundColor(Tokens.accent)
                        .font(.system(size: 22))
                }
                .padding(.horizontal, Tokens.spacing.lg)
                .padding(.top, Tokens.spacing.lg)
                .padding(.bottom, Tokens.spacing.md)

                Rectangle()
                    .fill(Tokens.border)
                    .frame(height: 1)
                    .padding(.horizontal, Tokens.spacing.lg)

                // QR code
                ZStack {
                    if isLoading {
                        ProgressView()
                            .frame(width: 220, height: 220)
                    } else if let token {
                        let url = "cozypup://share?token=\(token)"
                        if let image = generateQRCode(from: url) {
                            Image(uiImage: image)
                                .interpolation(.none)
                                .resizable()
                                .scaledToFit()
                                .frame(width: 220, height: 220)
                        }
                    }
                }
                .padding(.vertical, Tokens.spacing.lg)

                // Footer
                VStack(spacing: Tokens.spacing.sm) {
                    Text("Let someone scan to co-own")
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.text)
                    if let expiresAt {
                        HStack(spacing: 4) {
                            Image(systemName: "clock")
                                .font(.system(size: 10))
                            Text("Expires \(expiresAt, style: .relative)")
                                .font(Tokens.fontCaption2)
                        }
                        .foregroundColor(Tokens.textTertiary)
                    }

                    // Share button — send QR to someone remotely
                    Button {
                        prepareShareItems()
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "square.and.arrow.up")
                                .font(.system(size: 14, weight: .semibold))
                            Text("Send to a friend")
                                .font(Tokens.fontSubheadline.weight(.semibold))
                        }
                        .foregroundColor(Tokens.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Tokens.accent)
                        .cornerRadius(Tokens.radiusSmall)
                    }
                    .disabled(token == nil)
                    .padding(.horizontal, Tokens.spacing.lg)
                    .padding(.top, Tokens.spacing.xs)
                }
                .padding(.bottom, Tokens.spacing.lg)
            }
            .background(Tokens.surface)
            .cornerRadius(28)
            .shadow(color: Color.black.opacity(0.25), radius: 30, x: 0, y: 16)
            .padding(.horizontal, Tokens.spacing.xl)
            .scaleEffect(cardVisible ? 1 : 0.92)
            .opacity(cardVisible ? 1 : 0)
        }
        .background(BackgroundClearView())
        .onAppear {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.82)) {
                cardVisible = true
            }
            Task { await generateToken() }
        }
        .sheet(isPresented: $showShareActivity) {
            ActivityView(items: shareItems)
                .presentationDetents([.medium, .large])
        }
    }

    private func prepareShareItems() {
        guard let token else { return }
        let url = "cozypup://share?token=\(token)"
        var items: [Any] = [
            "Co-own \(pet.name) with me on CozyPup 🐾\n\nTap the link to join (or scan the QR):\n\(url)"
        ]
        if let image = generateQRCode(from: url) {
            items.append(image)
        }
        shareItems = items
        showShareActivity = true
    }

    private func dismiss() {
        withAnimation(.easeInOut(duration: 0.2)) {
            cardVisible = false
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            onDismiss()
        }
    }

    @ViewBuilder
    private var petAvatar: some View {
        if !pet.avatarUrl.isEmpty, let url = APIClient.shared.avatarURL(pet.avatarUrl) {
            CachedAsyncImage(url: url) { image in
                image.resizable().scaledToFill()
            } placeholder: {
                Circle().fill(pet.color.opacity(0.2))
            }
        } else {
            ZStack {
                Circle().fill(pet.color.opacity(0.2))
                Image(systemName: pet.species == .cat ? "cat.fill" : "dog.fill")
                    .font(.system(size: 24))
                    .foregroundColor(pet.color)
            }
        }
    }

    private func generateToken() async {
        struct Resp: Decodable {
            let token: String
            let expires_at: String
        }
        do {
            let resp: Resp = try await APIClient.shared.request(
                "POST", "/pets/\(pet.id)/share-token"
            )
            token = resp.token
            let formatter = ISO8601DateFormatter()
            expiresAt = formatter.date(from: resp.expires_at)
            isLoading = false
        } catch {
            print("[PetShare] Failed to generate token: \(error)")
            isLoading = false
        }
    }

    private func generateQRCode(from string: String) -> UIImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"

        guard let output = filter.outputImage else { return nil }
        let scaled = output.transformed(by: CGAffineTransform(scaleX: 10, y: 10))
        let context = CIContext()
        guard let cgImage = context.createCGImage(scaled, from: scaled.extent) else { return nil }
        return UIImage(cgImage: cgImage)
    }
}

/// Makes the underlying UIWindow background transparent so fullScreenCover looks like a floating modal.
private struct BackgroundClearView: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        DispatchQueue.main.async {
            view.superview?.superview?.backgroundColor = .clear
        }
        return view
    }
    func updateUIView(_ uiView: UIView, context: Context) {}
}

/// Wraps UIActivityViewController so we can open iOS's native share sheet from SwiftUI.
private struct ActivityView: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
