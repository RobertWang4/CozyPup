import SwiftUI

struct PetProfileEditor: View {
    let pet: Pet
    let petStore: PetStore
    @Binding var isPresented: Bool

    @State private var text: String = ""
    @State private var isSaving = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if text.isEmpty {
                    emptyState
                } else {
                    editor
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Tokens.bg.ignoresSafeArea())
            .navigationTitle(Lang.shared.isZh ? "\(pet.name) 的档案" : "\(pet.name)'s Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(L.cancel) { isPresented = false }
                        .foregroundColor(Tokens.accent)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        save()
                    } label: {
                        if isSaving {
                            ProgressView()
                        } else {
                            Text(L.save)
                                .foregroundColor(Tokens.accent)
                                .fontWeight(.semibold)
                        }
                    }
                    .disabled(isSaving)
                }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .presentationBackground(Tokens.bg)
        .onAppear {
            text = pet.profileMd ?? generateInitialProfile()
        }
    }

    private var emptyState: some View {
        VStack(spacing: Tokens.spacing.md) {
            Spacer()
            Image(systemName: "doc.text")
                .font(.system(size: 40))
                .foregroundColor(Tokens.textTertiary)
            Text(Lang.shared.isZh
                 ? "档案还是空的\nAI 会在聊天中自动填写\n你也可以手动编辑"
                 : "Profile is empty\nAI will fill it during chats\nYou can also edit manually")
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)
                .multilineTextAlignment(.center)
            Button {
                text = Lang.shared.isZh
                    ? "# \(pet.name)\n\n## 基本信息\n\n## 性格\n\n## 健康\n\n## 日常"
                    : "# \(pet.name)\n\n## Basics\n\n## Personality\n\n## Health\n\n## Routine"
            } label: {
                Text(Lang.shared.isZh ? "创建模板" : "Create Template")
                    .font(Tokens.fontSubheadline.weight(.medium))
                    .foregroundColor(Tokens.accent)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(Tokens.accentSoft)
                    .cornerRadius(Tokens.radiusSmall)
            }
            Spacer()
        }
        .padding()
    }

    private var editor: some View {
        TextEditor(text: $text)
            .font(Tokens.fontBody)
            .foregroundColor(Tokens.text)
            .scrollContentBackground(.hidden)
            .padding(Tokens.spacing.md)
    }

    private func generateInitialProfile() -> String {
        let isZh = Lang.shared.isZh
        var lines: [String] = []
        lines.append("# \(pet.name)")
        lines.append("")

        // Basics
        lines.append(isZh ? "## 基本信息" : "## Basics")
        let speciesStr: String = {
            switch pet.species {
            case .dog: return isZh ? "狗" : "Dog"
            case .cat: return isZh ? "猫" : "Cat"
            case .other: return isZh ? "其他" : "Other"
            }
        }()
        lines.append(isZh ? "- 类型：\(speciesStr)" : "- Species: \(speciesStr)")
        if !pet.breed.isEmpty {
            lines.append(isZh ? "- 品种：\(pet.breed)" : "- Breed: \(pet.breed)")
        }
        if let bday = pet.birthday, !bday.isEmpty {
            lines.append(isZh ? "- 生日：\(bday)" : "- Birthday: \(bday)")
        }
        if let w = pet.weight, w > 0 {
            lines.append(isZh ? "- 体重：\(String(format: "%.1f", w)) kg" : "- Weight: \(String(format: "%.1f", w)) kg")
        }

        lines.append("")
        lines.append(isZh ? "## 性格\n" : "## Personality\n")
        lines.append(isZh ? "## 健康\n" : "## Health\n")
        lines.append(isZh ? "## 日常" : "## Routine")

        return lines.joined(separator: "\n")
    }

    private func save() {
        isSaving = true
        Task {
            await petStore.saveProfileMd(pet.id, profileMd: text)
            isSaving = false
            isPresented = false
        }
    }
}
