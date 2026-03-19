import SwiftUI

struct EmptyStateView: View {
    let icon: String
    let title: String
    var subtitle: String?

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 48))
                .foregroundColor(Tokens.textTertiary)
            Text(title)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(Tokens.textSecondary)
            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 14))
                    .foregroundColor(Tokens.textTertiary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}
