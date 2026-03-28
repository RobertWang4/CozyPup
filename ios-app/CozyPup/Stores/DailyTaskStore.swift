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

    private func recalcAllCompleted() {
        allCompleted = tasks.isEmpty || tasks.allSatisfy { $0.isCompleted }
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
            recalcAllCompleted()
            saveLocal()
        }

        // Fire-and-forget — trust optimistic update
        do {
            let _: TapResponse = try await APIClient.shared.request(
                "POST", "/tasks/\(taskId)/tap"
            )
        } catch {
            print("DailyTaskStore.tap failed: \(error)")
            await fetchToday() // revert on failure
        }
    }

    func untap(_ taskId: String) async {
        // Optimistic update
        if let idx = tasks.firstIndex(where: { $0.id == taskId }),
           tasks[idx].completed_count > 0 {
            tasks[idx].completed_count -= 1
            recalcAllCompleted()
            saveLocal()
        }

        // Fire-and-forget — trust optimistic update
        do {
            let _: TapResponse = try await APIClient.shared.request(
                "POST", "/tasks/\(taskId)/untap"
            )
        } catch {
            print("DailyTaskStore.untap failed: \(error)")
            await fetchToday() // revert on failure
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
            let created: DailyTask = try await APIClient.shared.request(
                "POST", "/tasks", body: body
            )
            // Directly add to list — no second fetch needed
            tasks.append(created)
            recalcAllCompleted()
            saveLocal()
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
            let updated: DailyTask = try await APIClient.shared.request(
                "PUT", "/tasks/\(taskId)", body: body
            )
            if let idx = tasks.firstIndex(where: { $0.id == taskId }) {
                tasks[idx] = updated
            }
            recalcAllCompleted()
            saveLocal()
            return true
        } catch {
            print("DailyTaskStore.update failed: \(error)")
            return false
        }
    }

    func delete(_ taskId: String) async -> Bool {
        // Optimistic — already removed from UI before calling
        do {
            try await APIClient.shared.requestNoContent("DELETE", "/tasks/\(taskId)")
            // Ensure removed (may already be removed optimistically by caller)
            tasks.removeAll { $0.id == taskId }
            recalcAllCompleted()
            saveLocal()
            return true
        } catch {
            print("DailyTaskStore.delete failed: \(error)")
            await fetchToday() // revert on failure
            return false
        }
    }
}
