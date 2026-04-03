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

#Preview {
    MapCard(items: [
        MapItem(name: "朝阳公园", description: "宠物友好公园，有专门的狗狗活动区", distance: "1.2km"),
        MapItem(name: "望京宠物医院", description: "24小时营业，设备齐全", distance: "2.5km"),
        MapItem(name: "三里屯狗狗乐园", description: "室内外活动场地", distance: "3.8km"),
    ])
    .padding()
    .background(Tokens.bg)
}
