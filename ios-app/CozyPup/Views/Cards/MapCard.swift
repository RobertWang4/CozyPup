import SwiftUI

struct MapCard: View {
    let items: [MapItem]

    private let icons = ["tree", "fence", "figure.walk"]

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "mappin.and.ellipse")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.accent)
                    Text("Nearby Pet-Friendly Places")
                        .font(Tokens.fontCaption.weight(.semibold))
                        .foregroundColor(Tokens.textSecondary)
                }

                ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                    HStack(spacing: 12) {
                        Image(systemName: icons[i % icons.count])
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.green)
                            .frame(width: Tokens.size.iconSmall, height: Tokens.size.iconSmall)
                            .background(Tokens.accentSoft)
                            .cornerRadius(Tokens.spacing.sm)

                        VStack(alignment: .leading, spacing: 1) {
                            Text(item.name)
                                .font(Tokens.fontSubheadline.weight(.medium))
                                .foregroundColor(Tokens.text)
                            Text(item.description)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }

                        Spacer()

                        Text(item.distance)
                            .font(Tokens.fontCaption)
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
