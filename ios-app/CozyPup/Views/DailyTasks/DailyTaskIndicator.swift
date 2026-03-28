import SwiftUI

struct DailyTaskIndicator: View {
    @EnvironmentObject var store: DailyTaskStore
    @Binding var showPopover: Bool

    private var completedCount: Int {
        store.tasks.filter { $0.isCompleted }.count
    }

    private var total: Int { store.tasks.count }

    var body: some View {
        Button {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                showPopover.toggle()
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: store.allCompleted ? "checkmark" : "list.bullet")
                    .font(.system(size: 11, weight: .semibold))
                Text("\(completedCount)/\(total)")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
            }
            .foregroundColor(store.allCompleted ? Tokens.green : Tokens.textSecondary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                Capsule()
                    .fill(store.allCompleted ? Tokens.green.opacity(0.1) : Tokens.surface)
            )
            .overlay(
                Capsule()
                    .strokeBorder(store.allCompleted ? Tokens.green.opacity(0.2) : Tokens.border.opacity(0.5), lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
    }
}
