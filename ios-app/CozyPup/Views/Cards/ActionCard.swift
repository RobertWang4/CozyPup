import SwiftUI

struct ActionCard: View {
    let icon: String
    let iconColor: Color
    let label: String
    let title: String
    let subtitle: String
    var onTap: (() -> Void)?

    var body: some View {
        HStack {
            Button(action: { onTap?() }) {
                HStack(spacing: 12) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(iconColor)
                        .frame(width: 4, height: Tokens.size.buttonSmall)

                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Circle().fill(iconColor).frame(width: 6, height: 6)
                            Text(label)
                                .font(Tokens.fontCaption.weight(.medium))
                                .foregroundColor(Tokens.textSecondary)
                        }
                        HStack(spacing: Tokens.spacing.xs) {
                            Image(systemName: icon)
                                .font(Tokens.fontSubheadline)
                                .foregroundColor(iconColor)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(title)
                                    .font(Tokens.fontSubheadline.weight(.medium))
                                    .foregroundColor(Tokens.text)
                                Text(subtitle)
                                    .font(Tokens.fontCaption)
                                    .foregroundColor(Tokens.textSecondary)
                            }
                        }
                    }

                    Spacer()

                    if onTap != nil {
                        Image(systemName: "chevron.right")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
                .padding(12)
                .background(Tokens.surface)
                .cornerRadius(Tokens.radiusSmall)
                .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
            }
            .buttonStyle(.plain)
            Spacer()
        }
    }
}

#Preview("With Tap") {
    ActionCard(
        icon: "calendar.badge.plus",
        iconColor: Tokens.green,
        label: "已记录到日历",
        title: "豆豆 · 饮食",
        subtitle: "2026-04-01",
        onTap: {}
    )
    .padding()
    .background(Tokens.bg)
}

#Preview("No Tap") {
    ActionCard(
        icon: "checkmark.circle",
        iconColor: Tokens.blue,
        label: "疫苗提醒已设置",
        title: "豆豆 · 狂犬疫苗",
        subtitle: "2026-05-15 10:00"
    )
    .padding()
    .background(Tokens.bg)
}
