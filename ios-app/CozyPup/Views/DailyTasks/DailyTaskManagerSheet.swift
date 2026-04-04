import SwiftUI

struct DailyTaskManagerSheet: View {
    @EnvironmentObject var store: DailyTaskStore
    @EnvironmentObject var petStore: PetStore
    @Environment(\.dismiss) private var dismiss

    @State private var showAddForm = false

    // Add form state
    @State private var newTitle = ""
    @State private var newTarget = 1
    @State private var newPetId: String?
    @State private var hasDateRange = false
    @State private var newStartDate = Date()
    @State private var newEndDate = Date().addingTimeInterval(7 * 24 * 3600)
    @State private var isSaving = false
    @State private var deleteTarget: DailyTask?

    private let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 0) {
                    if store.tasks.isEmpty {
                        emptyState
                    } else {
                        taskList
                    }
                }
                .padding(.top, Tokens.spacing.sm)
                .padding(.bottom, Tokens.spacing.xl)
            }
            .background(Tokens.bg)
            .navigationTitle(Lang.shared.isZh ? "管理待办" : "Tasks")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(Lang.shared.isZh ? "关闭" : "Close") { dismiss() }
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
        .sheet(isPresented: $showAddForm) { addFormSheet }
        .alert(Lang.shared.isZh ? "确认删除" : "Confirm Delete", isPresented: Binding(
            get: { deleteTarget != nil },
            set: { if !$0 { deleteTarget = nil } }
        )) {
            Button(Lang.shared.isZh ? "取消" : "Cancel", role: .cancel) { deleteTarget = nil }
            Button(Lang.shared.isZh ? "删除" : "Delete", role: .destructive) {
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
                Text(Lang.shared.isZh
                     ? "确定要删除「\(task.title)」吗？"
                     : "Delete \"\(task.title)\"?")
            }
        }
        .preferredColorScheme(.light)
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: Tokens.spacing.md) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 36, weight: .thin))
                .foregroundColor(Tokens.textTertiary.opacity(0.5))
            Text(Lang.shared.isZh ? "暂无待办" : "No tasks yet")
                .font(Tokens.fontBody)
                .foregroundColor(Tokens.textTertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 80)
    }

    // MARK: - Task List

    private var taskList: some View {
        VStack(spacing: 0) {
            ForEach(store.tasks) { task in
                if task.id != store.tasks.first?.id {
                    Rectangle()
                        .fill(Tokens.divider)
                        .frame(height: 0.5)
                        .padding(.leading, Tokens.spacing.lg + Tokens.spacing.md)
                }
                taskRow(task)
            }
        }
        .background(Tokens.surface)
        .cornerRadius(Tokens.radius)
        .padding(.horizontal, Tokens.spacing.md)
    }

    private func taskRow(_ task: DailyTask) -> some View {
        HStack(spacing: Tokens.spacing.sm) {
            // Left accent bar
            RoundedRectangle(cornerRadius: 1.5)
                .fill(task.pet != nil ? Color(hex: task.pet!.color_hex) : Tokens.accent)
                .frame(width: 3, height: 32)

            VStack(alignment: .leading, spacing: 3) {
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
                            .background(Color(hex: pet.color_hex).opacity(0.1))
                            .cornerRadius(4)
                    }
                }
                HStack(spacing: 4) {
                    Text(Lang.shared.isZh
                         ? "每天 \(task.daily_target) 次"
                         : "\(task.daily_target)x / day")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                    if let end = task.end_date {
                        Text("·")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                        Text(Lang.shared.isZh
                             ? "至 \(formatDateShort(end))"
                             : "until \(formatDateShort(end))")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
            }

            Spacer()

            Button { deleteTarget = task } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Tokens.textTertiary)
                    .frame(width: 28, height: 28)
                    .background(Tokens.bg.opacity(0.8))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, Tokens.spacing.md)
        .padding(.vertical, Tokens.spacing.sm + 2)
    }

    // MARK: - Add Form

    private var addFormSheet: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Single continuous card
                VStack(spacing: 0) {
                    // Title field
                    VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
                        Text(Lang.shared.isZh ? "名称" : "Title")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                        TextField(Lang.shared.isZh ? "例如：遛狗、喂药" : "e.g. Walk dog, Give meds", text: $newTitle)
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.md)

                    sectionDivider

                    // Frequency
                    HStack {
                        Text(Lang.shared.isZh ? "每天" : "Daily")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                        Spacer()
                        HStack(spacing: 0) {
                            Button {
                                if newTarget > 1 { withAnimation(.snappy(duration: 0.15)) { newTarget -= 1 } }
                            } label: {
                                Image(systemName: "minus")
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundColor(newTarget > 1 ? Tokens.text : Tokens.textTertiary)
                                    .frame(width: 32, height: 28)
                            }
                            Text("\(newTarget)")
                                .font(Tokens.fontBody.weight(.semibold).monospacedDigit())
                                .foregroundColor(Tokens.accent)
                                .frame(width: 24)
                            Button {
                                if newTarget < 10 { withAnimation(.snappy(duration: 0.15)) { newTarget += 1 } }
                            } label: {
                                Image(systemName: "plus")
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundColor(newTarget < 10 ? Tokens.text : Tokens.textTertiary)
                                    .frame(width: 32, height: 28)
                            }
                        }
                        .background(Tokens.bg)
                        .cornerRadius(Tokens.radiusSmall)
                        Text(Lang.shared.isZh ? "次" : "times")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.textSecondary)
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.sm + 4)

                    sectionDivider

                    // Date range toggle
                    HStack {
                        Image(systemName: hasDateRange ? "calendar.circle.fill" : "calendar.circle")
                            .font(.system(size: 18))
                            .foregroundColor(hasDateRange ? Tokens.accent : Tokens.textTertiary)
                        Text(Lang.shared.isZh ? "设定期限" : "Set dates")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                        Spacer()
                        Toggle("", isOn: $hasDateRange.animation(.easeInOut(duration: 0.25)))
                            .labelsHidden()
                            .tint(Tokens.accent)
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.sm + 2)

                    // Date pickers (collapsed by default)
                    if hasDateRange {
                        sectionDivider

                        HStack {
                            Text(Lang.shared.isZh ? "从" : "From")
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.textSecondary)
                            Spacer()
                            DatePicker("", selection: $newStartDate, displayedComponents: .date)
                                .datePickerStyle(.compact)
                                .labelsHidden()
                                .tint(Tokens.accent)
                                .environment(\.locale, Locale(identifier: Lang.shared.isZh ? "zh_CN" : "en_US"))
                        }
                        .padding(.horizontal, Tokens.spacing.md)
                        .padding(.vertical, Tokens.spacing.sm)

                        sectionDivider

                        HStack {
                            Text(Lang.shared.isZh ? "到" : "Until")
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.textSecondary)
                            Spacer()
                            DatePicker("", selection: $newEndDate, in: newStartDate..., displayedComponents: .date)
                                .datePickerStyle(.compact)
                                .labelsHidden()
                                .tint(Tokens.accent)
                                .environment(\.locale, Locale(identifier: Lang.shared.isZh ? "zh_CN" : "en_US"))
                        }
                        .padding(.horizontal, Tokens.spacing.md)
                        .padding(.vertical, Tokens.spacing.sm)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }

                    // Pet picker (inline, not separate section)
                    if !petStore.pets.isEmpty {
                        sectionDivider

                        HStack {
                            Image(systemName: "pawprint")
                                .font(.system(size: 14))
                                .foregroundColor(Tokens.textTertiary)
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 6) {
                                    petChip(nil, name: Lang.shared.isZh ? "全部" : "All")
                                    ForEach(petStore.pets) { pet in
                                        petChip(pet.id, name: pet.name, colorHex: pet.colorHex)
                                    }
                                }
                            }
                        }
                        .padding(.horizontal, Tokens.spacing.md)
                        .padding(.vertical, Tokens.spacing.sm + 2)
                    }
                }
                .background(Tokens.surface)
                .cornerRadius(Tokens.radius)
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.top, Tokens.spacing.sm)

                Spacer()
            }
            .background(Tokens.bg)
            .navigationTitle(Lang.shared.isZh ? "添加待办" : "New Task")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(Lang.shared.isZh ? "取消" : "Cancel") {
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
                            let startStr = hasDateRange ? dateFormatter.string(from: newStartDate) : nil
                            let endStr = hasDateRange ? dateFormatter.string(from: newEndDate) : nil
                            let type = hasDateRange ? "special" : "routine"
                            let success = await store.create(
                                title: newTitle,
                                type: type,
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
                            ProgressView().scaleEffect(0.8)
                        } else {
                            Text(Lang.shared.isZh ? "保存" : "Save")
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

    // MARK: - Helpers

    private var sectionDivider: some View {
        Rectangle()
            .fill(Tokens.divider)
            .frame(height: 0.5)
            .padding(.leading, Tokens.spacing.md)
    }

    private func petChip(_ id: String?, name: String, colorHex: String? = nil) -> some View {
        let selected = newPetId == id
        let chipColor = colorHex != nil ? Color(hex: colorHex!) : Tokens.accent
        return Button {
            withAnimation(.easeInOut(duration: 0.15)) { newPetId = id }
        } label: {
            Text(name)
                .font(Tokens.fontCaption.weight(.medium))
                .foregroundColor(selected ? chipColor : Tokens.textSecondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(selected ? chipColor.opacity(0.1) : Tokens.bg)
                .cornerRadius(Tokens.radiusSmall)
                .overlay(
                    RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                        .strokeBorder(selected ? chipColor.opacity(0.3) : Color.clear, lineWidth: 0.5)
                )
        }
        .buttonStyle(.plain)
    }

    private func formatDateShort(_ dateStr: String) -> String {
        guard let date = DateFormatter.iso.date(from: dateStr) else { return dateStr }
        let f = DateFormatter()
        f.locale = Locale(identifier: Lang.shared.isZh ? "zh_CN" : "en_US")
        f.dateFormat = Lang.shared.isZh ? "M月d日" : "MMM d"
        return f.string(from: date)
    }

    private func resetForm() {
        newTitle = ""
        newTarget = 1
        newPetId = nil
        hasDateRange = false
        newStartDate = Date()
        newEndDate = Date().addingTimeInterval(7 * 24 * 3600)
    }
}

private extension DateFormatter {
    static let iso: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
}
