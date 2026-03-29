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
    @State private var newEndDate = Date().addingTimeInterval(7 * 24 * 3600)
    @State private var isSaving = false
    @State private var deleteTarget: DailyTask?

    private let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private let displayDateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "M月d日"
        return f
    }()

    var body: some View {
        NavigationStack {
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
                                .font(.system(size: 28))
                                .foregroundColor(Tokens.green.opacity(0.4))
                            Text("暂无待办")
                                .font(Tokens.fontSubheadline)
                                .foregroundColor(Tokens.textTertiary)
                            Text("点击右上角 + 添加")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary.opacity(0.7))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 60)
                    }
                }
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.top, Tokens.spacing.sm)
                .padding(.bottom, Tokens.spacing.xl)
            }
            .background(Tokens.bg)
            .navigationTitle("管理待办")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("关闭") { dismiss() }
                        .font(Tokens.fontSubheadline)
                        .foregroundColor(Tokens.textSecondary)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        withAnimation(.easeOut(duration: 0.2)) { showAddForm = true }
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 15, weight: .medium))
                            .foregroundColor(Tokens.accent)
                    }
                }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
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
                .padding(.leading, Tokens.spacing.xs)

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
                            HStack(spacing: Tokens.spacing.xs) {
                                Text("每天 \(task.daily_target) 次")
                                    .font(Tokens.fontCaption)
                                    .foregroundColor(Tokens.textSecondary)
                                if task.type == "special",
                                   let start = task.start_date, let end = task.end_date {
                                    Text("·")
                                        .foregroundColor(Tokens.textTertiary)
                                    Text("\(start) → \(end)")
                                        .font(Tokens.fontCaption)
                                        .foregroundColor(Tokens.textTertiary)
                                }
                            }
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
            .cornerRadius(Tokens.radius)
        }
    }

    // MARK: - Add Form

    private var addFormSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Tokens.spacing.lg) {
                    // Card 1: Name + Type
                    formCard {
                        cardField(label: "名称") {
                            TextField("例如：遛狗、喂药", text: $newTitle)
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                        }

                        cardDivider

                        cardField(label: "类型") {
                            HStack(spacing: Tokens.spacing.sm) {
                                typeChip("常规", value: "routine")
                                typeChip("特殊", value: "special")
                                Spacer()
                            }
                        }
                    }

                    // Card 2: Daily target
                    formCard {
                        cardField(label: "每天次数") {
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
                                            .foregroundColor(Tokens.text)
                                            .frame(width: 36, height: 32)
                                    }
                                    Rectangle()
                                        .fill(Tokens.divider)
                                        .frame(width: 0.5, height: 16)
                                    Button {
                                        if newTarget < 10 { newTarget += 1 }
                                    } label: {
                                        Image(systemName: "plus")
                                            .font(.system(size: 13, weight: .medium))
                                            .foregroundColor(Tokens.text)
                                            .frame(width: 36, height: 32)
                                    }
                                }
                                .background(Tokens.bg)
                                .cornerRadius(8)
                            }
                        }
                    }

                    // Card 3: Date range (special only)
                    if newType == "special" {
                        formCard {
                            cardField(label: "开始日期") {
                                DatePicker(
                                    "",
                                    selection: $newStartDate,
                                    displayedComponents: .date
                                )
                                .datePickerStyle(.compact)
                                .labelsHidden()
                                .tint(Tokens.accent)
                            }

                            cardDivider

                            cardField(label: "结束日期") {
                                DatePicker(
                                    "",
                                    selection: $newEndDate,
                                    in: newStartDate...,
                                    displayedComponents: .date
                                )
                                .datePickerStyle(.compact)
                                .labelsHidden()
                                .tint(Tokens.accent)
                            }
                        }
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }

                    // Card 4: Pet picker
                    if !petStore.pets.isEmpty {
                        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                            Text("关联宠物")
                                .font(Tokens.fontCaption.weight(.medium))
                                .foregroundColor(Tokens.textTertiary)
                                .padding(.leading, Tokens.spacing.xs)

                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: Tokens.spacing.sm) {
                                    petChip(nil, name: "不关联")
                                    ForEach(petStore.pets) { pet in
                                        petChip(pet.id, name: pet.name, colorHex: pet.colorHex)
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.top, Tokens.spacing.sm)
                .padding(.bottom, Tokens.spacing.xl)
            }
            .background(Tokens.bg)
            .navigationTitle("添加待办")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        showAddForm = false
                        resetForm()
                    }
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        guard !newTitle.trimmingCharacters(in: .whitespaces).isEmpty else { return }
                        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                        isSaving = true
                        Task {
                            let startStr = newType == "special" ? dateFormatter.string(from: newStartDate) : nil
                            let endStr = newType == "special" ? dateFormatter.string(from: newEndDate) : nil
                            let success = await store.create(
                                title: newTitle,
                                type: newType,
                                dailyTarget: newTarget,
                                petId: newPetId,
                                startDate: startStr,
                                endDate: endStr
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
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .preferredColorScheme(.light)
    }

    // MARK: - Form Card Components

    @ViewBuilder
    private func formCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        VStack(spacing: 0) {
            content()
        }
        .background(Tokens.surface)
        .cornerRadius(Tokens.radius)
    }

    private var cardDivider: some View {
        Rectangle()
            .fill(Tokens.divider)
            .frame(height: 0.5)
            .padding(.leading, Tokens.spacing.md)
    }

    @ViewBuilder
    private func cardField<Content: View>(label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
            Text(label)
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textTertiary)
            content()
        }
        .padding(.horizontal, Tokens.spacing.md)
        .padding(.vertical, Tokens.spacing.sm + 2)
    }

    // MARK: - Chips

    private func typeChip(_ label: String, value: String) -> some View {
        Button {
            withAnimation(.easeInOut(duration: 0.15)) {
                newType = value
            }
        } label: {
            Text(label)
                .font(Tokens.fontSubheadline.weight(.medium))
                .foregroundColor(newType == value ? Tokens.accent : Tokens.textSecondary)
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(newType == value ? Tokens.accentSoft : Tokens.bg)
                .cornerRadius(Tokens.radiusSmall)
        }
        .buttonStyle(.plain)
    }

    private func petChip(_ id: String?, name: String, colorHex: String? = nil) -> some View {
        Button {
            withAnimation(.easeInOut(duration: 0.15)) {
                newPetId = id
            }
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
        }
        .buttonStyle(.plain)
    }

    private func resetForm() {
        newTitle = ""
        newTarget = 1
        newPetId = nil
        newType = "routine"
        newStartDate = Date()
        newEndDate = Date().addingTimeInterval(7 * 24 * 3600)
    }
}
