import SwiftUI

struct DailyTaskRow: View {
    let task: DailyTask
    let onTap: () -> Void

    private var progress: CGFloat {
        guard task.daily_target > 0 else { return 1 }
        return CGFloat(task.completed_count) / CGFloat(task.daily_target)
    }

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: Tokens.spacing.sm) {
                // Title + pet tag
                VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                    HStack(spacing: Tokens.spacing.xs) {
                        Text(task.title)
                            .font(Tokens.fontSubheadline.weight(.medium))
                            .foregroundColor(task.isCompleted ? Tokens.textTertiary : Tokens.text)

                        if let pet = task.pet {
                            Text(pet.name)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(Tokens.white)
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1)
                                .background(Color(hex: pet.color_hex).opacity(task.isCompleted ? 0.5 : 1))
                                .cornerRadius(4)
                        }
                    }

                    // Progress bar
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule()
                                .fill(Tokens.border)
                                .frame(height: 4)
                            Capsule()
                                .fill(task.isCompleted ? Tokens.green : Tokens.accent)
                                .frame(width: geo.size.width * progress, height: 4)
                                .animation(.easeOut(duration: 0.3), value: task.completed_count)
                        }
                    }
                    .frame(height: 4)
                }

                // Completion indicator
                if task.isCompleted {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(Tokens.green)
                } else {
                    Circle()
                        .strokeBorder(Tokens.border, lineWidth: 1.5)
                        .frame(width: 16, height: 16)
                }
            }
            .padding(.horizontal, Tokens.spacing.md)
            .padding(.vertical, Tokens.spacing.sm + 2)
        }
        .buttonStyle(.plain)
        .disabled(task.isCompleted)
    }
}
