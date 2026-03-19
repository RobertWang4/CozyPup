import SwiftUI

struct MapCard: View {
    let items: [MapItem]

    private let icons = ["tree", "fence", "figure.walk"]

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "mappin.and.ellipse")
                        .font(.system(size: 12))
                        .foregroundColor(Tokens.accent)
                    Text("Nearby Pet-Friendly Places")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Tokens.textSecondary)
                }

                ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                    HStack(spacing: 12) {
                        Image(systemName: icons[i % icons.count])
                            .font(.system(size: 14))
                            .foregroundColor(Tokens.green)
                            .frame(width: 28, height: 28)
                            .background(Tokens.accentSoft)
                            .cornerRadius(8)

                        VStack(alignment: .leading, spacing: 1) {
                            Text(item.name)
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(Tokens.text)
                            Text(item.description)
                                .font(.system(size: 12))
                                .foregroundColor(Tokens.textSecondary)
                        }

                        Spacer()

                        Text(item.distance)
                            .font(.system(size: 12))
                            .foregroundColor(Tokens.textTertiary)
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
