import SwiftUI
import CoreImage.CIFilterBuiltins

struct PetShareSheet: View {
    let petId: String
    let petName: String
    @State private var token: String?
    @State private var expiresAt: Date?
    @State private var isLoading = true

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            Text("Share \(petName)")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            Text("Let someone scan to co-own this pet")
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)

            if isLoading {
                ProgressView()
                    .frame(width: 200, height: 200)
            } else if let token {
                let url = "cozypup://share?token=\(token)"
                if let image = generateQRCode(from: url) {
                    Image(uiImage: image)
                        .interpolation(.none)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 200, height: 200)
                        .cornerRadius(Tokens.radiusSmall)
                }

                if let expiresAt {
                    Text("Expires \(expiresAt, style: .relative)")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }

            Spacer()
        }
        .padding(Tokens.spacing.md)
        .task { await generateToken() }
    }

    private func generateToken() async {
        struct Resp: Decodable {
            let token: String
            let expires_at: String
        }
        do {
            let resp: Resp = try await APIClient.shared.request(
                "POST", "/pets/\(petId)/share-token"
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

#Preview {
    PetShareSheet(petId: "test-id", petName: "Weini")
}
