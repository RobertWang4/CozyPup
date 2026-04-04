import SwiftUI

struct RecordCard: View {
    let petName: String
    let date: String
    let category: String
    var title: String?
    var cost: Double?
    var onTap: (() -> Void)?

    var body: some View {
        HStack {
            Button(action: { onTap?() }) {
                HStack(spacing: 12) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Tokens.accent)
                        .frame(width: 4, height: Tokens.size.buttonSmall)

                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Circle().fill(Tokens.accent).frame(width: 6, height: 6)
                            Text(L.recordedToCalendar)
                                .font(Tokens.fontCaption.weight(.medium))
                                .foregroundColor(Tokens.textSecondary)
                        }
                        HStack(spacing: Tokens.spacing.xs) {
                            Image(systemName: "checkmark.circle")
                                .font(Tokens.fontSubheadline)
                                .foregroundColor(Tokens.green)
                            VStack(alignment: .leading, spacing: 1) {
                                HStack(spacing: Tokens.spacing.xs) {
                                    if let title, !title.isEmpty {
                                        Text("\(petName) · \(title)")
                                            .font(Tokens.fontSubheadline.weight(.medium))
                                            .foregroundColor(Tokens.text)
                                    } else {
                                        Text("\(petName) · \(category)")
                                            .font(Tokens.fontSubheadline.weight(.medium))
                                            .foregroundColor(Tokens.text)
                                    }
                                    if let cost, cost > 0 {
                                        Text("¥\(Int(cost))")
                                            .font(Tokens.fontCaption.weight(.semibold))
                                            .foregroundColor(Tokens.accent)
                                    }
                                }
                                Text(date)
                                    .font(Tokens.fontCaption)
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
            }
            .buttonStyle(.plain)
            Spacer()
        }
    }
}

#Preview {
    VStack(spacing: 12) {
        RecordCard(petName: "豆豆", date: "2026-04-01", category: "daily", title: "去公园玩")
        RecordCard(petName: "豆豆", date: "2026-04-01", category: "diet")
    }
    .padding()
    .background(Tokens.bg)
}
