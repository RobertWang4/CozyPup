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
            .background(Tokens.bg)
            .navigationTitle(Lang.shared.isZh ? "\(pet.name) 的档案" : "\(pet.name)'s Profile")
            .navigationBarTitleDisplayMode(.inline)
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
        .onAppear {
            text = pet.profileMd ?? ""
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

    private func save() {
        isSaving = true
        Task {
            await petStore.saveProfileMd(pet.id, profileMd: text)
            isSaving = false
            isPresented = false
        }
    }
}
