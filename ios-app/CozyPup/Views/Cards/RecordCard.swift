import SwiftUI

struct RecordCard: View {
    let petName: String
    let date: String
    let category: String
    var onTap: (() -> Void)?

    var body: some View {
        HStack {
            Button(action: { onTap?() }) {
                HStack(spacing: 12) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Tokens.accent)
                        .frame(width: 4, height: 36)

                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Circle().fill(Tokens.accent).frame(width: 6, height: 6)
                            Text(L.recordedToCalendar)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(Tokens.textSecondary)
                        }
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle")
                                .font(.system(size: 14))
                                .foregroundColor(Tokens.green)
                            VStack(alignment: .leading, spacing: 1) {
                                Text("\(petName) · \(category)")
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(Tokens.text)
                                Text(date)
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
            }
            .buttonStyle(.plain)
            Spacer()
        }
    }
}
