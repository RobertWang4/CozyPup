import SwiftUI

struct DailyTaskRow: View {
    let task: DailyTask
    let onTap: () -> Void

    private var progress: CGFloat {
        guard task.daily_target > 0 else { return 1 }
        return min(CGFloat(task.completed_count) / CGFloat(task.daily_target), 1)
    }

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: Tokens.spacing.sm) {
                // Left accent bar — fills up as progress increases
                ZStack(alignment: .bottom) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Tokens.border.opacity(0.4))
                        .frame(width: 3, height: 32)
                    RoundedRectangle(cornerRadius: 2)
                        .fill(task.isCompleted ? Tokens.green : Tokens.accent)
                        .frame(width: 3, height: 32 * progress)
                        .animation(.spring(response: 0.4, dampingFraction: 0.7), value: task.completed_count)
                }

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(task.title)
                            .font(Tokens.fontSubheadline.weight(.medium))
                            .foregroundColor(task.isCompleted ? Tokens.textTertiary : Tokens.text)

                        if let pet = task.pet {
                            Text(pet.name)
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundColor(Color(hex: pet.color_hex))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 2)
                                .background(Color(hex: pet.color_hex).opacity(0.12))
                                .cornerRadius(4)
                        }
                    }

                    // Progress track
                    HStack(spacing: 3) {
                        ForEach(0..<task.daily_target, id: \.self) { i in
                            RoundedRectangle(cornerRadius: 2)
                                .fill(i < task.completed_count
                                      ? (task.isCompleted ? Tokens.green : Tokens.accent)
                                      : Tokens.border.opacity(0.3))
                                .frame(height: 3)
                                .animation(.spring(response: 0.3, dampingFraction: 0.8).delay(Double(i) * 0.05), value: task.completed_count)
                        }
                    }
                    .frame(maxWidth: 120)
                }

                Spacer()

                // Right side: checkmark or tap hint
                ZStack {
                    if task.isCompleted {
                        Circle()
                            .fill(Tokens.green.opacity(0.12))
                            .frame(width: 24, height: 24)
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(Tokens.green)
                    } else {
                        Circle()
                            .strokeBorder(Tokens.accent.opacity(0.3), lineWidth: 1.5)
                            .frame(width: 24, height: 24)
                        Text("\(task.completed_count)")
                            .font(.system(size: 10, weight: .semibold, design: .rounded))
                            .foregroundColor(Tokens.accent)
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(TaskTapStyle())
        .disabled(task.isCompleted)
    }
}

// Subtle scale + highlight on press
private struct TaskTapStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(configuration.isPressed ? Tokens.accentSoft.opacity(0.5) : Color.clear)
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
    }
}
