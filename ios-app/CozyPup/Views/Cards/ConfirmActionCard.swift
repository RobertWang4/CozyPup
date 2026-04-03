import SwiftUI

struct ConfirmActionCard: View {
    let message: String
    let status: ConfirmActionCardData.ConfirmStatus
    let onConfirm: () -> Void
    let onCancel: () -> Void

    var body: some View {
        HStack {
            HStack(spacing: 12) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(statusAccent)
                    .frame(width: 4, height: status == .pending ? 60 : 36)

                VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                    // Header
                    HStack(spacing: 6) {
                        Circle().fill(statusAccent).frame(width: 6, height: 6)
                        Text(statusLabel)
                            .font(Tokens.fontCaption.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                    }

                    // Description
                    Text(message)
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.text)
                        .fixedSize(horizontal: false, vertical: true)

                    // Buttons or status
                    if status == .pending {
                        HStack(spacing: Tokens.spacing.sm) {
                            Button(action: onCancel) {
                                Text(L.cancel)
                                    .font(Tokens.fontSubheadline.weight(.medium))
                                    .foregroundColor(Tokens.textSecondary)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 10)
                                    .background(Tokens.bg)
                                    .cornerRadius(Tokens.radiusSmall)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                            .stroke(Tokens.border)
                                    )
                            }
                            .buttonStyle(.plain)

                            Button(action: onConfirm) {
                                Text(L.confirm)
                                    .font(Tokens.fontSubheadline.weight(.medium))
                                    .foregroundColor(Tokens.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 10)
                                    .background(Tokens.accent)
                                    .cornerRadius(Tokens.radiusSmall)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                Spacer()
            }
            .padding(Tokens.spacing.md)
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
            .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(statusBorder))

            Spacer()
        }
    }

    private var statusLabel: String {
        switch status {
        case .pending: return Lang.shared.isZh ? "确认操作" : "Confirm Action"
        case .confirmed: return L.actionConfirmed
        case .cancelled: return L.actionCancelled
        }
    }

    private var statusAccent: Color {
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

#Preview("Pending") {
    ConfirmActionCard(
        message: "确认删除豆豆的疫苗记录？此操作不可撤销。",
        status: .pending,
        onConfirm: {},
        onCancel: {}
    )
    .padding()
    .background(Tokens.bg)
}

#Preview("Confirmed") {
    ConfirmActionCard(
        message: "已删除豆豆的疫苗记录",
        status: .confirmed,
        onConfirm: {},
        onCancel: {}
    )
    .padding()
    .background(Tokens.bg)
}

#Preview("Cancelled") {
    ConfirmActionCard(
        message: "已取消删除操作",
        status: .cancelled,
        onConfirm: {},
        onCancel: {}
    )
    .padding()
    .background(Tokens.bg)
}
