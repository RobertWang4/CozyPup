import SwiftUI
import CoreImage.CIFilterBuiltins

struct PetShareSheet: View {
    let pet: Pet
    @State private var token: String?
    @State private var expiresAt: Date?
    @State private var isLoading = true

    var body: some View {
        ZStack {
            Tokens.bg.ignoresSafeArea()

            VStack {
                // Drag handle
                RoundedRectangle(cornerRadius: 2)
                    .fill(Tokens.border)
                    .frame(width: 36, height: 4)
                    .padding(.top, Tokens.spacing.sm)

                Spacer()

                // The card
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

                    // Footer: scan hint
                    VStack(spacing: 4) {
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
                    }
                    .padding(.bottom, Tokens.spacing.lg)
                }
                .background(Tokens.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: 24)
                        .stroke(Tokens.border, lineWidth: 1)
                )
                .cornerRadius(24)
                .shadow(color: Tokens.text.opacity(0.08), radius: 24, x: 0, y: 12)
                .padding(.horizontal, Tokens.spacing.lg)

                Spacer()
            }
        }
        .task { await generateToken() }
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
