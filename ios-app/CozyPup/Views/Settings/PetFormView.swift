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
        VStack(spacing: Tokens.spacing.md) {
            // Avatar
            ZStack {
                Circle()
                    .fill(avatarColor.opacity(0.15))
                    .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
                Image(systemName: species == .cat ? "cat.fill" : "dog.fill")
                    .font(.system(size: 34))
                    .foregroundColor(avatarColor)
            }
            .padding(.bottom, Tokens.spacing.xs)

            VStack(alignment: .leading, spacing: 6) {
                Text(L.name).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                TextField(L.namePlaceholder, text: $name)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(L.species).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                HStack(spacing: 10) {
                    ForEach(Species.allCases, id: \.self) { s in
                        Button {
                            species = s
                            if s == .other { customSpeciesFocused = true }
                        } label: {
                            Text(speciesLabel(s))
                                .font(Tokens.fontSubheadline.weight(.medium))
                                .padding(.horizontal, Tokens.spacing.md)
                                .padding(.vertical, Tokens.spacing.sm)
                                .background(species == s ? Tokens.accent : Tokens.surface)
                                .foregroundColor(species == s ? Tokens.white : Tokens.text)
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
                        .font(Tokens.fontSubheadline)
                        .padding(10)
                        .background(Tokens.surface)
                        .cornerRadius(10)
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Tokens.border))
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(L.breed).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                TextField(L.breedPlaceholder, text: $breed)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(L.birthday).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
                    TextField("YYYY-MM-DD", text: $birthday)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Tokens.surface)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text(L.weightKg).font(Tokens.fontSubheadline.weight(.medium)).foregroundColor(Tokens.textSecondary)
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
                    .foregroundColor(Tokens.white)
                    .cornerRadius(14)
                    .font(Tokens.fontCallout.weight(.semibold))
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
