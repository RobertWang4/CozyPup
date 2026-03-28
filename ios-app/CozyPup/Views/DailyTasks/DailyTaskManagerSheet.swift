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
    @State private var isSaving = false
    @State private var deleteTarget: DailyTask?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button("关闭") { dismiss() }
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
                Spacer()
                Text("管理待办")
                    .font(Tokens.fontSubheadline.weight(.semibold))
                    .foregroundColor(Tokens.text)
                Spacer()
                Button {
                    withAnimation(.easeOut(duration: 0.2)) { showAddForm = true }
                } label: {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 22))
                        .foregroundColor(Tokens.accent)
                }
            }
            .padding(.horizontal, Tokens.spacing.lg)
            .padding(.vertical, 14)

            Divider().foregroundColor(Tokens.divider)

            // Task list
            ScrollView {
                VStack(spacing: Tokens.spacing.md) {
                    if !store.tasks.filter({ $0.type == "routine" }).isEmpty {
                        taskSection("常规", tasks: store.tasks.filter { $0.type == "routine" })
                    }
                    if !store.tasks.filter({ $0.type == "special" }).isEmpty {
                        taskSection("特殊", tasks: store.tasks.filter { $0.type == "special" })
                    }
                    if store.tasks.isEmpty {
                        VStack(spacing: Tokens.spacing.sm) {
                            Image(systemName: "leaf")
                                .font(.system(size: 24))
                                .foregroundColor(Tokens.green.opacity(0.5))
                            Text("暂无待办")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                        .padding(.top, 40)
                    }
                }
                .padding(Tokens.spacing.lg)
            }
        }
        .background(Tokens.bg)
        .sheet(isPresented: $showAddForm) {
            addFormSheet
        }
        .alert("确认删除", isPresented: Binding(
            get: { deleteTarget != nil },
            set: { if !$0 { deleteTarget = nil } }
        )) {
            Button("取消", role: .cancel) { deleteTarget = nil }
            Button("删除", role: .destructive) {
                if let task = deleteTarget {
                    // Optimistic: remove from list immediately
                    withAnimation(.easeOut(duration: 0.2)) {
                        store.tasks.removeAll { $0.id == task.id }
                    }
                    Task { await store.delete(task.id) }
                    deleteTarget = nil
                }
            }
        } message: {
            if let task = deleteTarget {
                Text("确定要删除「\(task.title)」吗？")
            }
        }
        .preferredColorScheme(.light)
    }

    // MARK: - Task Section

    private func taskSection(_ title: String, tasks: [DailyTask]) -> some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            Text(title)
                .font(Tokens.fontCaption.weight(.semibold))
                .foregroundColor(Tokens.textTertiary)
                .textCase(.uppercase)
                .tracking(0.8)

            VStack(spacing: 0) {
                ForEach(tasks) { task in
                    if task.id != tasks.first?.id {
                        Divider().padding(.leading, Tokens.spacing.md)
                    }
                    HStack(spacing: Tokens.spacing.sm) {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(task.title)
                                    .font(Tokens.fontBody)
                                    .foregroundColor(Tokens.text)
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
                            Text("每天 \(task.daily_target) 次")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        Spacer()
                        Button {
                            deleteTarget = task
                        } label: {
                            Image(systemName: "minus.circle")
                                .font(.system(size: 18))
                                .foregroundColor(Tokens.red.opacity(0.6))
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.sm + 2)
                }
            }
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
        }
    }

    // MARK: - Add Form (lightweight, no NavigationView/Form)

    private var addFormSheet: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button("取消") {
                    showAddForm = false
                    resetForm()
                }
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)
                Spacer()
                Text("添加待办")
                    .font(Tokens.fontSubheadline.weight(.semibold))
                    .foregroundColor(Tokens.text)
                Spacer()
                Button {
                    guard !newTitle.trimmingCharacters(in: .whitespaces).isEmpty else { return }
                    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    isSaving = true
                    Task {
                        let success = await store.create(
                            title: newTitle,
                            type: newType,
                            dailyTarget: newTarget,
                            petId: newPetId
                        )
                        isSaving = false
                        if success {
                            showAddForm = false
                            resetForm()
                        }
                    }
                } label: {
                    if isSaving {
                        ProgressView()
                            .scaleEffect(0.8)
                    } else {
                        Text("保存")
                            .font(Tokens.fontSubheadline.weight(.semibold))
                            .foregroundColor(
                                newTitle.trimmingCharacters(in: .whitespaces).isEmpty
                                ? Tokens.textTertiary : Tokens.accent
                            )
                    }
                }
                .disabled(newTitle.trimmingCharacters(in: .whitespaces).isEmpty || isSaving)
            }
            .padding(.horizontal, Tokens.spacing.lg)
            .padding(.vertical, 14)

            Divider().foregroundColor(Tokens.divider)

            ScrollView {
                VStack(spacing: Tokens.spacing.md) {
                    // Name field
                    VStack(alignment: .leading, spacing: 6) {
                        Text("名称")
                            .font(Tokens.fontCaption.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                        TextField("例如：遛狗、喂药", text: $newTitle)
                            .font(Tokens.fontBody)
                            .padding(Tokens.spacing.sm + 2)
                            .background(Tokens.surface)
                            .cornerRadius(Tokens.radiusSmall)
                            .overlay(
                                RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                    .strokeBorder(Tokens.border.opacity(0.5), lineWidth: 0.5)
                            )
                    }

                    // Type picker
                    VStack(alignment: .leading, spacing: 6) {
                        Text("类型")
                            .font(Tokens.fontCaption.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                        HStack(spacing: Tokens.spacing.sm) {
                            typeChip("常规", value: "routine")
                            typeChip("特殊", value: "special")
                        }
                    }

                    // Target stepper
                    VStack(alignment: .leading, spacing: 6) {
                        Text("每天次数")
                            .font(Tokens.fontCaption.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                        HStack {
                            Text("\(newTarget) 次")
                                .font(Tokens.fontBody.weight(.medium))
                                .foregroundColor(Tokens.text)
                            Spacer()
                            HStack(spacing: 0) {
                                Button {
                                    if newTarget > 1 { newTarget -= 1 }
                                } label: {
                                    Image(systemName: "minus")
                                        .font(.system(size: 13, weight: .medium))
                                        .frame(width: 36, height: 32)
                                }
                                Divider().frame(height: 16)
                                Button {
                                    if newTarget < 10 { newTarget += 1 }
                                } label: {
                                    Image(systemName: "plus")
                                        .font(.system(size: 13, weight: .medium))
                                        .frame(width: 36, height: 32)
                                }
                            }
                            .foregroundColor(Tokens.text)
                            .background(Tokens.surface)
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .strokeBorder(Tokens.border.opacity(0.5), lineWidth: 0.5)
                            )
                        }
                        .padding(Tokens.spacing.sm + 2)
                        .background(Tokens.surface)
                        .cornerRadius(Tokens.radiusSmall)
                        .overlay(
                            RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                .strokeBorder(Tokens.border.opacity(0.5), lineWidth: 0.5)
                        )
                    }

                    // Pet picker
                    if !petStore.pets.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("关联宠物")
                                .font(Tokens.fontCaption.weight(.medium))
                                .foregroundColor(Tokens.textSecondary)
                            HStack(spacing: Tokens.spacing.sm) {
                                petChip(nil, name: "不关联")
                                ForEach(petStore.pets) { pet in
                                    petChip(pet.id, name: pet.name, colorHex: pet.colorHex)
                                }
                            }
                        }
                    }
                }
                .padding(Tokens.spacing.lg)
            }
        }
        .background(Tokens.bg)
        .preferredColorScheme(.light)
    }

    // MARK: - Chips

    private func typeChip(_ label: String, value: String) -> some View {
        Button {
            newType = value
        } label: {
            Text(label)
                .font(Tokens.fontSubheadline.weight(.medium))
                .foregroundColor(newType == value ? Tokens.white : Tokens.text)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(newType == value ? Tokens.accent : Tokens.surface)
                .cornerRadius(Tokens.radiusSmall)
                .overlay(
                    RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                        .strokeBorder(newType == value ? Color.clear : Tokens.border.opacity(0.5), lineWidth: 0.5)
                )
        }
        .buttonStyle(.plain)
    }

    private func petChip(_ id: String?, name: String, colorHex: String? = nil) -> some View {
        Button {
            newPetId = id
        } label: {
            Text(name)
                .font(Tokens.fontSubheadline.weight(.medium))
                .foregroundColor(newPetId == id
                    ? (colorHex != nil ? Color(hex: colorHex!) : Tokens.accent)
                    : Tokens.textSecondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .background(
                    newPetId == id
                    ? (colorHex != nil ? Color(hex: colorHex!).opacity(0.12) : Tokens.accentSoft)
                    : Tokens.surface
                )
                .cornerRadius(Tokens.radiusSmall)
                .overlay(
                    RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                        .strokeBorder(
                            newPetId == id
                            ? (colorHex != nil ? Color(hex: colorHex!).opacity(0.3) : Tokens.accent.opacity(0.3))
                            : Tokens.border.opacity(0.5),
                            lineWidth: 0.5
                        )
                )
        }
        .buttonStyle(.plain)
    }

    private func resetForm() {
        newTitle = ""
        newTarget = 1
        newPetId = nil
        newType = "routine"
    }
}
