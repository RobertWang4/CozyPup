import SwiftUI

struct DailyTaskPopover: View {
    @EnvironmentObject var store: DailyTaskStore
    @Binding var isPresented: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("今日待办")
                    .font(Tokens.fontSubheadline.weight(.semibold))
                    .foregroundColor(Tokens.text)
                Spacer()
                Button {
                    withAnimation(.easeOut(duration: 0.2)) { isPresented = false }
                } label: {
                    Image(systemName: "xmark")
                        .font(Tokens.fontCaption.weight(.medium))
                        .foregroundColor(Tokens.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, Tokens.spacing.md)
            .padding(.top, Tokens.spacing.md)
            .padding(.bottom, Tokens.spacing.sm)

            Divider().foregroundColor(Tokens.divider)

            if store.tasks.isEmpty {
                Text("暂无待办")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
                    .frame(maxWidth: .infinity)
                    .padding(Tokens.spacing.md)
            } else {
                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(store.tasks) { task in
                            DailyTaskRow(task: task) {
                                Task { await store.tap(task.id) }
                            }
                            .padding(.horizontal, Tokens.spacing.md)

                            if task.id != store.tasks.last?.id {
                                Divider()
                                    .foregroundColor(Tokens.divider)
                                    .padding(.horizontal, Tokens.spacing.md)
                            }
                        }
                    }
                    .padding(.vertical, Tokens.spacing.sm)
                }
            }
        }
        .background(Tokens.surface)
        .cornerRadius(Tokens.radius)
        .overlay(
            RoundedRectangle(cornerRadius: Tokens.radius)
                .stroke(Tokens.border, lineWidth: 1)
        )
        .shadow(color: Tokens.dimOverlay.opacity(0.08), radius: 12, y: 4)
    }
}
