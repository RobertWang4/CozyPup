import SwiftUI

struct QuickActionCards: View {
    let onSelect: (String) -> Void
    @ObservedObject private var lang = Lang.shared

    private var actions: [(icon: String, label: String, message: String)] {
        lang.isZh ? [
            ("🐶", "添加宠物", "我想添加一只宠物"),
            ("💊", "健康咨询", "我家宠物最近有点不舒服"),
            ("📅", "设个提醒", "帮我设一个提醒"),
            ("📍", "附近医院", "帮我找附近的宠物医院"),
        ] : [
            ("🐶", "Add Pet", "I want to add a pet"),
            ("💊", "Health", "My pet hasn't been feeling well"),
            ("📅", "Reminder", "Set a reminder for me"),
            ("📍", "Vet Near Me", "Find a nearby vet clinic"),
        ]
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Tokens.spacing.sm) {
                ForEach(actions, id: \.label) { action in
                    Button {
                        Haptics.light()
                        onSelect(action.message)
                    } label: {
                        HStack(spacing: Tokens.spacing.xs) {
                            Text(action.icon)
                                .font(Tokens.fontSubheadline)
                            Text(action.label)
                                .font(Tokens.fontSubheadline)
                                .foregroundColor(Tokens.text)
                        }
                        .padding(.horizontal, Tokens.spacing.md)
                        .padding(.vertical, Tokens.spacing.sm)
                        .background(Tokens.surface)
                        .cornerRadius(Tokens.radiusSmall)
                    }
                }
            }
            .padding(.horizontal, Tokens.spacing.md)
        }
    }
}

#Preview {
    QuickActionCards { msg in print(msg) }
        .background(Tokens.bg)
}
