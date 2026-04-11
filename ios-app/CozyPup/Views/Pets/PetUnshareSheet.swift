import SwiftUI

struct PetUnshareSheet: View {
    let petId: String
    let petName: String
    @State private var isSubmitting = false
    var onDone: (() -> Void)?

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            Text("Leave \(petName)?")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            HStack(spacing: Tokens.spacing.md) {
                Button {
                    Task { await unshare(keepCopy: true) }
                } label: {
                    VStack(spacing: Tokens.spacing.sm) {
                        Text("📋").font(.title)
                        Text("Keep a copy")
                            .font(Tokens.fontSubheadline.weight(.semibold))
                            .foregroundColor(Tokens.text)
                        Text("All data is copied. No longer synced.")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusSmall)
                    .overlay(
                        RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                            .stroke(Tokens.border, lineWidth: 1.5)
                    )
                }
                .buttonStyle(.plain)

                Button {
                    Task { await unshare(keepCopy: false) }
                } label: {
                    VStack(spacing: Tokens.spacing.sm) {
                        Text("👋").font(.title)
                        Text("Just leave")
                            .font(Tokens.fontSubheadline.weight(.semibold))
                            .foregroundColor(Tokens.text)
                        Text("Pet disappears. Data stays with owner.")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusSmall)
                    .overlay(
                        RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                            .stroke(Tokens.border, lineWidth: 1.5)
                    )
                }
                .buttonStyle(.plain)
            }

            if isSubmitting {
                ProgressView()
            }

            Spacer()
        }
        .padding(Tokens.spacing.md)
    }

    private func unshare(keepCopy: Bool) async {
        isSubmitting = true
        struct Body: Encodable { let keep_copy: Bool }
        struct Resp: Decodable { let status: String }
        do {
            let _: Resp = try await APIClient.shared.request(
                "POST", "/pets/\(petId)/unshare",
                body: Body(keep_copy: keepCopy)
            )
            onDone?()
        } catch {
            print("[Unshare] failed: \(error)")
        }
        isSubmitting = false
    }
}

#Preview {
    PetUnshareSheet(petId: "test", petName: "Weini")
}
