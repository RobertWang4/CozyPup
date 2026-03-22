import SwiftUI

struct PetFormView: View {
    var editingPet: Pet?
    var onSave: (String, Species, String, String?, Double?) -> Void
    var onCancel: (() -> Void)?

    @State private var name = ""
    @State private var species: Species = .dog
    @State private var customSpecies = ""
    @State private var breed = ""
    @State private var birthday = ""
    @State private var weight = ""
    @FocusState private var customSpeciesFocused: Bool

    private func speciesLabel(_ s: Species) -> String {
        if s == .other && !customSpecies.isEmpty { return customSpecies }
        switch s {
        case .dog: return L.dog
        case .cat: return L.cat
        case .other: return L.other
        }
    }

    private var avatarColor: Color {
        if let pet = editingPet { return pet.color }
        return petColors[0]
    }

    var body: some View {
        VStack(spacing: 16) {
            // Avatar
            ZStack {
                Circle()
                    .fill(avatarColor.opacity(0.15))
                    .frame(width: 80, height: 80)
                Image(systemName: species == .cat ? "cat.fill" : "dog.fill")
                    .font(.system(size: 34))
                    .foregroundColor(avatarColor)
            }
            .padding(.bottom, 4)

            VStack(alignment: .leading, spacing: 6) {
                Text(L.name).font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                TextField(L.namePlaceholder, text: $name)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(L.species).font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                HStack(spacing: 10) {
                    ForEach(Species.allCases, id: \.self) { s in
                        Button {
                            species = s
                            if s == .other { customSpeciesFocused = true }
                        } label: {
                            Text(speciesLabel(s))
                                .font(.system(size: 14, weight: .medium))
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(species == s ? Tokens.accent : Tokens.surface)
                                .foregroundColor(species == s ? .white : Tokens.text)
                                .cornerRadius(20)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 20)
                                        .stroke(species == s ? Color.clear : Tokens.border)
                                )
                        }
                    }
                }
                if species == .other {
                    TextField(Lang.shared.isZh ? "输入宠物类型，如：兔子、仓鼠" : "e.g. Rabbit, Hamster", text: $customSpecies)
                        .focused($customSpeciesFocused)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .padding(10)
                        .background(Tokens.surface)
                        .cornerRadius(10)
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Tokens.border))
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(L.breed).font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                TextField(L.breedPlaceholder, text: $breed)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L.birthday).font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                    TextField("YYYY-MM-DD", text: $birthday)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Tokens.surface)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text(L.weightKg).font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                    TextField("0.0", text: $weight)
                        .keyboardType(.decimalPad)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Tokens.surface)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
            }

            Button {
                Haptics.light()
                let bday = birthday.isEmpty ? nil : birthday
                let w = Double(weight)
                onSave(name, species, breed, bday, w)
            } label: {
                Text(editingPet != nil ? L.saveChanges : L.addPet)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(name.isEmpty ? Tokens.border : Tokens.accent)
                    .foregroundColor(.white)
                    .cornerRadius(14)
                    .font(.system(size: 16, weight: .semibold))
            }
            .disabled(name.isEmpty)

            if let onCancel {
                Button(L.cancel) { onCancel() }
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .onAppear {
            if let pet = editingPet {
                name = pet.name
                species = pet.species
                breed = pet.breed
                birthday = pet.birthday ?? ""
                weight = pet.weight.map { String($0) } ?? ""
            }
        }
    }
}
