import SwiftUI

struct DailyTaskPopover: View {
    @EnvironmentObject var store: DailyTaskStore
    @Binding var isPresented: Bool

    private var completedCount: Int {
        store.tasks.filter { $0.isCompleted }.count
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header with overall progress
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Today")
                        .font(Tokens.fontCaption2.weight(.medium))
                        .foregroundColor(Tokens.textTertiary)
                        .textCase(.uppercase)
                        .tracking(1.2)
                    Text("\(completedCount)/\(store.tasks.count)")
                        .font(.system(size: 20, weight: .semibold, design: .serif))
                        .foregroundColor(store.allCompleted ? Tokens.green : Tokens.text)
                }
                Spacer()
                Button {
                    NotificationCenter.default.post(name: .openSavedChats, object: nil)
                } label: {
                    Image(systemName: "clock.arrow.circlepath")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.accent)
                }
                .buttonStyle(.plain)
                .padding(.trailing, Tokens.spacing.xs)
                Button {
                    withAnimation(.easeOut(duration: 0.2)) { isPresented = false }
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(Tokens.textTertiary)
                        .frame(width: 22, height: 22)
                        .background(Tokens.bg)
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, Tokens.spacing.md)
            .padding(.top, 14)
            .padding(.bottom, 10)

            // Task list
            if store.tasks.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "leaf")
                        .font(.system(size: 12))
                        .foregroundColor(Tokens.green)
                    Text("No tasks yet")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
                .padding(.vertical, Tokens.spacing.md)
                .frame(maxWidth: .infinity)
            } else {
                VStack(spacing: 0) {
                    ForEach(store.tasks) { task in
                        DailyTaskRow(task: task, onTap: {
                            Task { await store.tap(task.id) }
                        }, onUntap: {
                            Task { await store.untap(task.id) }
                        })
                    }
                }
            }
        }
        .padding(.bottom, 6)
        .background(
            RoundedRectangle(cornerRadius: Tokens.radius)
                .fill(Tokens.surface)
                .shadow(color: Tokens.text.opacity(0.06), radius: 16, y: 6)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Tokens.radius)
                .strokeBorder(Tokens.border.opacity(0.3), lineWidth: 0.5)
        )
    }
}
