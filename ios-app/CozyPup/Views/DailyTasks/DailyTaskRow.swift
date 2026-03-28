import SwiftUI

struct DailyTaskRow: View {
    let task: DailyTask
    let onTap: () -> Void

    var body: some View {
        HStack(spacing: Tokens.spacing.sm) {
            Button(action: onTap) {
                ZStack {
                    Circle()
                        .stroke(task.isCompleted ? Tokens.green : Tokens.border, lineWidth: 2)
                        .frame(width: 24, height: 24)
                    if task.isCompleted {
                        Image(systemName: "checkmark")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(Tokens.green)
                    }
                }
            }
            .buttonStyle(.plain)
            .disabled(task.isCompleted)

            Text(task.title)
                .font(Tokens.fontBody)
                .foregroundColor(task.isCompleted ? Tokens.textTertiary : Tokens.text)
                .strikethrough(task.isCompleted, color: Tokens.textTertiary)

            Spacer()

            if let pet = task.pet {
                Text(pet.name)
                    .font(Tokens.fontCaption2)
                    .foregroundColor(Tokens.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color(hex: pet.color_hex))
                    .cornerRadius(6)
            }

            if task.daily_target > 1 {
                Text(task.progressText)
                    .font(Tokens.fontCaption.weight(.medium))
                    .foregroundColor(task.isCompleted ? Tokens.green : Tokens.textSecondary)
            }
        }
        .padding(.vertical, Tokens.spacing.xs)
    }
}
