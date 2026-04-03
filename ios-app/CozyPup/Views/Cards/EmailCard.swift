import SwiftUI

struct EmailCard: View {
    let subject: String
    let emailBody: String
    @State private var copied = false

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "envelope")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.blue)
                    Text("Email Draft")
                        .font(Tokens.fontCaption.weight(.semibold))
                        .foregroundColor(Tokens.textSecondary)
                }

                Text(subject)
                    .font(Tokens.fontSubheadline.weight(.semibold))
                    .foregroundColor(Tokens.text)

                Text(emailBody)
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)

                HStack(spacing: Tokens.spacing.sm) {
                    Button {
                        UIPasteboard.general.string = "\(subject)\n\n\(emailBody)"
                        copied = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copied = false }
                    } label: {
                        Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                            .font(Tokens.fontCaption.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .overlay(RoundedRectangle(cornerRadius: Tokens.spacing.sm).stroke(Tokens.border))
                    }

                    ShareLink(item: "\(subject)\n\n\(emailBody)") {
                        Label("Share", systemImage: "square.and.arrow.up")
                            .font(Tokens.fontCaption.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .overlay(RoundedRectangle(cornerRadius: Tokens.spacing.sm).stroke(Tokens.border))
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

#Preview {
    EmailCard(
        subject: "豆豆体检报告 - 2026年4月",
        emailBody: "尊敬的宠物医生：\n\n我家金毛豆豆最近食欲不振，精神萎靡，希望预约一次全面体检。\n\n谢谢！"
    )
    .padding()
    .background(Tokens.bg)
}
