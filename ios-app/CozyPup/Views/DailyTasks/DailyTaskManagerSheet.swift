import SwiftUI

struct DailyTaskManagerSheet: View {
    @EnvironmentObject var store: DailyTaskStore
    @EnvironmentObject var petStore: PetStore
    @Environment(\.dismiss) private var dismiss

    @State private var showAddForm = false

    // Add form state
    @State private var newTitle = ""
    @State private var newType = "routine"
    @State private var newTarget = 1
    @State private var newPetId: String?
    @State private var newStartDate = Date()
    @State private var newEndDate = Date().addingTimeInterval(7 * 86400)

    var body: some View {
        NavigationView {
            List {
                Section("常规待办") {
                    ForEach(store.tasks.filter { $0.type == "routine" }) { task in
                        taskRow(task)
                    }
                    if store.tasks.filter({ $0.type == "routine" }).isEmpty {
                        Text("暂无常规待办")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }

                Section("特殊待办") {
                    ForEach(store.tasks.filter { $0.type == "special" }) { task in
                        taskRow(task)
                    }
                    if store.tasks.filter({ $0.type == "special" }).isEmpty {
                        Text("暂无特殊待办")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("管理待办")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("关闭") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showAddForm = true
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showAddForm) {
                addTaskForm
            }
        }
    }

    private func taskRow(_ task: DailyTask) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                HStack(spacing: Tokens.spacing.xs) {
                    Text(task.title)
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.text)
                    if let pet = task.pet {
                        Text(pet.name)
                            .font(Tokens.fontCaption2)
                            .foregroundColor(Tokens.white)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color(hex: pet.color_hex))
                            .cornerRadius(4)
                    }
                }
                Text("每天 \(task.daily_target) 次")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textSecondary)
            }
            Spacer()
            Button(role: .destructive) {
                Task { await store.delete(task.id) }
            } label: {
                Image(systemName: "trash")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
            }
            .buttonStyle(.plain)
        }
    }

    private var addTaskForm: some View {
        NavigationView {
            Form {
                Section("基本信息") {
                    TextField("待办名称", text: $newTitle)
                    Picker("类型", selection: $newType) {
                        Text("常规（每天）").tag("routine")
                        Text("特殊（指定日期）").tag("special")
                    }
                    Stepper("每天 \(newTarget) 次", value: $newTarget, in: 1...10)
                }

                Section("关联宠物（可选）") {
                    Button("不关联") {
                        newPetId = nil
                    }
                    .foregroundColor(newPetId == nil ? Tokens.accent : Tokens.textSecondary)

                    ForEach(petStore.pets) { pet in
                        Button {
                            newPetId = pet.id
                        } label: {
                            HStack {
                                Text(pet.name)
                                    .foregroundColor(Tokens.text)
                                Spacer()
                                if newPetId == pet.id {
                                    Image(systemName: "checkmark")
                                        .foregroundColor(Tokens.accent)
                                }
                            }
                        }
                    }
                }

                if newType == "special" {
                    Section("日期范围") {
                        DatePicker("开始", selection: $newStartDate, displayedComponents: .date)
                        DatePicker("结束", selection: $newEndDate, displayedComponents: .date)
                    }
                }
            }
            .navigationTitle("添加待办")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("取消") { showAddForm = false }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("保存") {
                        let fmt = DateFormatter()
                        fmt.dateFormat = "yyyy-MM-dd"
                        Task {
                            let success = await store.create(
                                title: newTitle,
                                type: newType,
                                dailyTarget: newTarget,
                                petId: newPetId,
                                startDate: newType == "special" ? fmt.string(from: newStartDate) : nil,
                                endDate: newType == "special" ? fmt.string(from: newEndDate) : nil
                            )
                            if success {
                                showAddForm = false
                                newTitle = ""
                                newTarget = 1
                                newPetId = nil
                                newType = "routine"
                            }
                        }
                    }
                    .disabled(newTitle.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }
}
