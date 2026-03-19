import SwiftUI

struct EmergencyBanner: View {
    var onFind: () -> Void
    var onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.white)
                .padding(6)
                .background(Tokens.red)
                .cornerRadius(8)

            VStack(alignment: .leading, spacing: 2) {
                Text("Possible emergency detected")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Tokens.text)
                Text("Find a nearby 24h pet ER?")
                    .font(.system(size: 12))
                    .foregroundColor(Tokens.textSecondary)
            }

            Spacer()

            Button("Find") { onFind() }
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Tokens.red)
                .cornerRadius(10)

            Button { onDismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .padding(12)
        .background(Tokens.redSoft)
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "F5C4B5")))
        .padding(.horizontal, 12)
    }
}
