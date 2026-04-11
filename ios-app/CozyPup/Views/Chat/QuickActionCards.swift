import SwiftUI

struct QuickActionCards: View {
    let onSelect: (String) -> Void

    private let actions: [(icon: String, label: String, message: String)] = [
        ("🐶", "添加宠物", "我想添加一只宠物"),
        ("💊", "健康咨询", "我家宠物最近有点不舒服"),
        ("📅", "设个提醒", "帮我设一个提醒"),
        ("📍", "附近医院", "帮我找附近的宠物医院"),
    ]

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: Tokens.spacing.sm) {
            ForEach(actions, id: \.label) { action in
                Button {
                    Haptics.light()
                    onSelect(action.message)
                } label: {
                    VStack(spacing: Tokens.spacing.xs) {
                        Text(action.icon)
                            .font(.title2)
                        Text(action.label)
                            .font(Tokens.fontSubheadline.weight(.medium))
                            .foregroundColor(Tokens.text)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusSmall)
                }
            }
        }
        .padding(.horizontal, Tokens.spacing.md)
    }
}

#Preview {
    QuickActionCards { msg in print(msg) }
        .background(Tokens.bg)
}
