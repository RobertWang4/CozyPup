import SwiftUI

struct EmergencyBanner: View {
    var onFind: () -> Void
    var onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(Tokens.white)
                .padding(6)
                .background(Tokens.red)
                .cornerRadius(8)

            VStack(alignment: .leading, spacing: 2) {
                Text("Possible emergency detected")
                    .font(Tokens.fontSubheadline.weight(.semibold))
                    .foregroundColor(Tokens.text)
                Text("Find a nearby 24h pet ER?")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textSecondary)
            }

            Spacer()

            Button("Find") { onFind() }
                .font(Tokens.fontSubheadline.weight(.semibold))
                .foregroundColor(Tokens.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Tokens.red)
                .cornerRadius(10)

            Button { onDismiss() } label: {
                Image(systemName: "xmark")
                    .font(Tokens.fontCaption.weight(.semibold))
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .padding(12)
        .background(Tokens.redSoft)
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Tokens.redSoft))
        .padding(.horizontal, 12)
    }
}

#Preview {
    EmergencyBanner(onFind: {}, onDismiss: {})
        .background(Tokens.bg)
}
