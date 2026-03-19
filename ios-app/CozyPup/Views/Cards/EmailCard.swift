import SwiftUI

struct EmailCard: View {
    let subject: String
    let emailBody: String
    @State private var copied = false

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "envelope")
                        .font(.system(size: 12))
                        .foregroundColor(Tokens.blue)
                    Text("Email Draft")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Tokens.textSecondary)
                }

                Text(subject)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Tokens.text)

                Text(emailBody)
                    .font(.system(size: 13))
                    .foregroundColor(Tokens.textSecondary)

                HStack(spacing: 8) {
                    Button {
                        UIPasteboard.general.string = "\(subject)\n\n\(emailBody)"
                        copied = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copied = false }
                    } label: {
                        Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Tokens.textSecondary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                    }

                    ShareLink(item: "\(subject)\n\n\(emailBody)") {
                        Label("Share", systemImage: "square.and.arrow.up")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Tokens.textSecondary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                    }
                }
            }
            .padding(12)
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
            .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
            Spacer()
        }
    }
}
