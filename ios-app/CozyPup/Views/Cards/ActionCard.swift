import SwiftUI

struct ActionCard: View {
    let icon: String
    let iconColor: Color
    let label: String
    let title: String
    let subtitle: String

    var body: some View {
        HStack {
            HStack(spacing: 12) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(iconColor)
                    .frame(width: 4, height: 36)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Circle().fill(iconColor).frame(width: 6, height: 6)
                        Text(label)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(Tokens.textSecondary)
                    }
                    HStack(spacing: 4) {
                        Image(systemName: icon)
                            .font(.system(size: 14))
                            .foregroundColor(iconColor)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(title)
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(Tokens.text)
                            Text(subtitle)
                                .font(.system(size: 12))
                                .foregroundColor(Tokens.textSecondary)
                        }
                    }
                }

                Spacer()
            }
            .padding(12)
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
            .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
            Spacer()
        }
    }
}
