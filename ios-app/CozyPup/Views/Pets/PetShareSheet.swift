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

            VStack(spacing: Tokens.spacing.lg) {
                // Drag handle
                RoundedRectangle(cornerRadius: 2)
                    .fill(Tokens.border)
                    .frame(width: 36, height: 4)
                    .padding(.top, Tokens.spacing.sm)

                Text("Share this pet")
                    .font(Tokens.fontTitle.weight(.medium))
                    .foregroundColor(Tokens.text)

                Text("Let someone scan to co-own")
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)

                // Card with pet info + QR
                VStack(spacing: Tokens.spacing.md) {
                    // Pet header
                    HStack(spacing: Tokens.spacing.sm) {
                        petAvatar
                            .frame(width: 48, height: 48)
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
                            .font(.system(size: 20))
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.top, Tokens.spacing.md)

                    Divider()
                        .background(Tokens.border)
                        .padding(.horizontal, Tokens.spacing.md)

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
                                    .padding(Tokens.spacing.sm)
                                    .background(Color.white)
                                    .cornerRadius(Tokens.radiusSmall)
                            }
                        }
                    }

                    // Expires label
                    if let expiresAt {
                        HStack(spacing: 4) {
                            Image(systemName: "clock")
                                .font(.system(size: 11))
                            Text("Expires \(expiresAt, style: .relative)")
                                .font(Tokens.fontCaption2)
                        }
                        .foregroundColor(Tokens.textTertiary)
                        .padding(.bottom, Tokens.spacing.md)
                    }
                }
                .frame(maxWidth: .infinity)
                .background(Tokens.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: Tokens.radius)
                        .stroke(Tokens.border, lineWidth: 1)
                )
                .cornerRadius(Tokens.radius)
                .padding(.horizontal, Tokens.spacing.md)

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
                    .font(.system(size: 22))
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
