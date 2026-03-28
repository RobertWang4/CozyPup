import SwiftUI

struct DailyTaskIndicator: View {
    @EnvironmentObject var store: DailyTaskStore
    @Binding var showPopover: Bool

    var body: some View {
        Button {
            withAnimation(.easeOut(duration: 0.2)) { showPopover.toggle() }
        } label: {
            ZStack {
                Circle()
                    .fill(store.allCompleted ? Tokens.green.opacity(0.15) : Tokens.surface)
                    .frame(width: Tokens.size.buttonSmall, height: Tokens.size.buttonSmall)
                Image(systemName: store.allCompleted ? "checkmark.circle.fill" : "checkmark.circle")
                    .font(.system(size: 18))
                    .foregroundColor(store.allCompleted ? Tokens.green : Tokens.textSecondary)
            }
        }
        .buttonStyle(.plain)
    }
}
