import SwiftUI

struct DailyTaskPopover: View {
    @EnvironmentObject var store: DailyTaskStore
    @Binding var isPresented: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Compact header
            HStack {
                Text("今日待办")
                    .font(Tokens.fontCaption.weight(.semibold))
                    .foregroundColor(Tokens.textSecondary)
                Spacer()
                Button {
                    withAnimation(.easeOut(duration: 0.2)) { isPresented = false }
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(Tokens.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, Tokens.spacing.md)
            .padding(.top, Tokens.spacing.sm + 2)
            .padding(.bottom, Tokens.spacing.xs)

            // Task list — no scroll, sized to content
            if store.tasks.isEmpty {
                Text("暂无待办")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
                    .padding(.vertical, Tokens.spacing.sm)
                    .frame(maxWidth: .infinity)
            } else {
                VStack(spacing: 0) {
                    ForEach(store.tasks) { task in
                        if task.id != store.tasks.first?.id {
                            Divider()
                                .padding(.horizontal, Tokens.spacing.md)
                        }
                        DailyTaskRow(task: task) {
                            Task { await store.tap(task.id) }
                        }
                    }
                }
            }
        }
        .padding(.bottom, Tokens.spacing.xs)
        .background(Tokens.surface)
        .cornerRadius(Tokens.radiusSmall)
        .overlay(
            RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                .stroke(Tokens.border.opacity(0.5), lineWidth: 0.5)
        )
        .shadow(color: Tokens.dimOverlay.opacity(0.06), radius: 8, y: 3)
    }
}
