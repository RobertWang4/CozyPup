import SwiftUI

struct DailyTaskRow: View {
    let task: DailyTask
    let onTap: () -> Void
    var onUntap: (() -> Void)?

    @State private var dragOffset: CGFloat = 0

    private var progress: CGFloat {
        guard task.daily_target > 0 else { return 1 }
        return min(CGFloat(task.completed_count) / CGFloat(task.daily_target), 1)
    }

    var body: some View {
        HStack(spacing: Tokens.spacing.sm) {
            // Left accent bar
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

            // Checkmark or count
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
        .offset(x: dragOffset)
        .contentShape(Rectangle())
        .onTapGesture {
            if !task.isCompleted { onTap() }
        }
        .gesture(
            task.completed_count > 0
            ? DragGesture(minimumDistance: 15)
                .onChanged { value in
                    if value.translation.width < 0 {
                        dragOffset = value.translation.width * 0.4 // resistance
                    }
                }
                .onEnded { value in
                    if value.translation.width < -40 {
                        // Trigger undo
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                            dragOffset = -60
                        }
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                            onUntap?()
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                                dragOffset = 0
                            }
                        }
                    } else {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                            dragOffset = 0
                        }
                    }
                }
            : nil
        )
    }
}

#Preview("In Progress") {
    DailyTaskRow(
        task: DailyTask(
            id: "1", title: "遛狗", type: "routine",
            daily_target: 3, completed_count: 1,
            pet: DailyTaskPet(id: "p1", name: "豆豆", color_hex: "E8835C"),
            active: true, start_date: nil, end_date: nil
        ),
        onTap: {}
    )
    .background(Tokens.bg)
}

#Preview("Completed") {
    DailyTaskRow(
        task: DailyTask(
            id: "2", title: "喂药", type: "special",
            daily_target: 2, completed_count: 2,
            pet: DailyTaskPet(id: "p1", name: "豆豆", color_hex: "6BA3BE"),
            active: true, start_date: nil, end_date: nil
        ),
        onTap: {}
    )
    .background(Tokens.bg)
}

#Preview("Not Started") {
    DailyTaskRow(
        task: DailyTask(
            id: "3", title: "刷牙", type: "routine",
            daily_target: 1, completed_count: 0,
            pet: nil, active: true, start_date: nil, end_date: nil
        ),
        onTap: {}
    )
    .background(Tokens.bg)
}
