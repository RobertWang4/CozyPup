import SwiftUI

struct DailyTaskCard: View {
    let data: DailyTaskCardData
    @EnvironmentObject var dailyTaskStore: DailyTaskStore

    private var isCreated: Bool { data.type == "daily_task_created" }
    private var isDeleted: Bool { data.type == "daily_task_deleted" }

    private var icon: String {
        if isDeleted { return "trash" }
        if isCreated { return "checkmark.circle" }
        return "pencil"
    }

    private var label: String {
        if isDeleted { return L.taskDeleted }
        if isCreated { return L.taskCreated }
        return L.taskUpdated
    }

    private var iconColor: Color {
        if isDeleted { return Tokens.red }
        if isCreated { return Tokens.green }
        return Tokens.blue
    }

    private var subtitle: String {
        var parts: [String] = []
        if let t = data.task_type {
            parts.append(t == "routine" ? L.taskTypeRoutine : L.taskTypeSpecial)
        }
        if let target = data.daily_target, target > 1 {
            parts.append(L.taskDailyTarget(target))
        }
        if let start = data.start_date, let end = data.end_date {
            parts.append("\(start) ~ \(end)")
        }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        ActionCard(
            icon: icon,
            iconColor: iconColor,
            label: label,
            title: data.title,
            subtitle: subtitle
        )
        .task {
            await dailyTaskStore.fetchToday()
        }
    }
}
