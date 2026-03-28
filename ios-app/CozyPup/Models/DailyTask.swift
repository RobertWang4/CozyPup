import Foundation

struct DailyTaskPet: Codable, Equatable {
    let id: String
    let name: String
    let color_hex: String
}

struct DailyTask: Identifiable, Codable, Equatable {
    let id: String
    var title: String
    let type: String          // "routine" or "special"
    var daily_target: Int
    var completed_count: Int
    let pet: DailyTaskPet?
    var active: Bool
    let start_date: String?
    let end_date: String?

    var isCompleted: Bool { completed_count >= daily_target }
    var progressText: String { "\(completed_count)/\(daily_target)" }
}

struct TodayTasksResponse: Codable {
    let tasks: [DailyTask]
    let all_completed: Bool
}

struct TapResponse: Codable {
    let task_id: String
    let completed_count: Int
    let daily_target: Int
    let all_completed: Bool
}

struct DailyTaskCreateBody: Encodable {
    let title: String
    let type: String
    let daily_target: Int
    let pet_id: String?
    let start_date: String?
    let end_date: String?
}

struct DailyTaskUpdateBody: Encodable {
    let title: String?
    let daily_target: Int?
    let start_date: String?
    let end_date: String?
    let active: Bool?
}
