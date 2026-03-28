import Foundation

@MainActor
class DailyTaskStore: ObservableObject {
    @Published var tasks: [DailyTask] = []
    @Published var allCompleted: Bool = true

    private let cacheKey = "cozypup_daily_tasks"

    init() {
        loadLocal()
    }

    private func loadLocal() {
        guard let data = UserDefaults.standard.data(forKey: cacheKey),
              let saved = try? JSONDecoder().decode([DailyTask].self, from: data) else { return }
        tasks = saved
        allCompleted = saved.allSatisfy { $0.isCompleted }
    }

    private func saveLocal() {
        if let data = try? JSONEncoder().encode(tasks) {
            UserDefaults.standard.set(data, forKey: cacheKey)
        }
    }

    func fetchToday() async {
        do {
            let response: TodayTasksResponse = try await APIClient.shared.request(
                "GET", "/tasks/today"
            )
            tasks = response.tasks
            allCompleted = response.all_completed
            saveLocal()
        } catch {
            print("DailyTaskStore.fetchToday failed: \(error)")
        }
    }

    func tap(_ taskId: String) async {
        // Optimistic update
        if let idx = tasks.firstIndex(where: { $0.id == taskId }),
           tasks[idx].completed_count < tasks[idx].daily_target {
            tasks[idx].completed_count += 1
            allCompleted = tasks.allSatisfy { $0.isCompleted }
            saveLocal()
        }

        do {
            let response: TapResponse = try await APIClient.shared.request(
                "POST", "/tasks/\(taskId)/tap"
            )
            if let idx = tasks.firstIndex(where: { $0.id == taskId }) {
                tasks[idx].completed_count = response.completed_count
            }
            allCompleted = response.all_completed
            saveLocal()
        } catch {
            print("DailyTaskStore.tap failed: \(error)")
            await fetchToday()
        }
    }

    func create(
        title: String, type: String, dailyTarget: Int,
        petId: String? = nil, startDate: String? = nil, endDate: String? = nil
    ) async -> Bool {
        let body = DailyTaskCreateBody(
            title: title, type: type, daily_target: dailyTarget,
            pet_id: petId, start_date: startDate, end_date: endDate
        )
        do {
            let _: DailyTask = try await APIClient.shared.request(
                "POST", "/tasks", body: body
            )
            await fetchToday()
            return true
        } catch {
            print("DailyTaskStore.create failed: \(error)")
            return false
        }
    }

    func update(_ taskId: String, title: String? = nil, dailyTarget: Int? = nil, active: Bool? = nil) async -> Bool {
        let body = DailyTaskUpdateBody(
            title: title, daily_target: dailyTarget,
            start_date: nil, end_date: nil, active: active
        )
        do {
            let _: DailyTask = try await APIClient.shared.request(
                "PUT", "/tasks/\(taskId)", body: body
            )
            await fetchToday()
            return true
        } catch {
            print("DailyTaskStore.update failed: \(error)")
            return false
        }
    }

    func delete(_ taskId: String) async -> Bool {
        do {
            try await APIClient.shared.requestNoContent("DELETE", "/tasks/\(taskId)")
            tasks.removeAll { $0.id == taskId }
            allCompleted = tasks.allSatisfy { $0.isCompleted }
            saveLocal()
            return true
        } catch {
            print("DailyTaskStore.delete failed: \(error)")
            return false
        }
    }
}
