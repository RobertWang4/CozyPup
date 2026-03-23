import SwiftUI

struct ConfirmActionCard: View {
    let message: String
    let status: ConfirmActionCardData.ConfirmStatus
    let onConfirm: () -> Void
    let onCancel: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: statusIcon)
                        .font(Tokens.fontSubheadline)
                        .foregroundColor(statusColor)
                    Text(message)
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.text)
                }

                if status == .pending {
                    HStack(spacing: Tokens.spacing.sm) {
                        Button(action: onCancel) {
                            Text(L.cancel)
                                .font(Tokens.fontCaption.weight(.medium))
                                .foregroundColor(Tokens.textSecondary)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(Tokens.surface)
                                .cornerRadius(Tokens.radiusSmall)
                                .overlay(
                                    RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                        .stroke(Tokens.border)
                                )
                        }
                        .buttonStyle(.plain)

                        Button(action: onConfirm) {
                            Text(L.confirm)
                                .font(Tokens.fontCaption.weight(.medium))
                                .foregroundColor(Tokens.white)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(Tokens.accent)
                                .cornerRadius(Tokens.radiusSmall)
                        }
                        .buttonStyle(.plain)
                    }
                } else if status == .confirmed {
                    Text(L.actionConfirmed)
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.green)
                } else {
                    Text(L.actionCancelled)
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }
            .padding(12)
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
            .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(statusBorder))
            Spacer()
        }
    }

    private var statusIcon: String {
        switch status {
        case .pending: return "questionmark.circle"
        case .confirmed: return "checkmark.circle.fill"
        case .cancelled: return "xmark.circle"
        }
    }

    private var statusColor: Color {
        switch status {
        case .pending: return Tokens.orange
        case .confirmed: return Tokens.green
        case .cancelled: return Tokens.textTertiary
        }
    }

    private var statusBorder: Color {
        switch status {
        case .pending: return Tokens.orange.opacity(0.3)
        case .confirmed: return Tokens.green.opacity(0.3)
        case .cancelled: return Tokens.border
        }
    }
}
