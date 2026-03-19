import SwiftUI

struct PetFormView: View {
    var editingPet: Pet?
    var onSave: (String, Species, String, String?, Double?) -> Void
    var onCancel: (() -> Void)?

    @State private var name = ""
    @State private var species: Species = .dog
    @State private var breed = ""
    @State private var birthday = ""
    @State private var weight = ""

    var body: some View {
        VStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Name").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                TextField("e.g. Buddy", text: $name)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Species").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                HStack(spacing: 10) {
                    ForEach(Species.allCases, id: \.self) { s in
                        Button {
                            species = s
                        } label: {
                            Text(s.rawValue.capitalized)
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
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Breed").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                TextField("e.g. Golden Retriever", text: $breed)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Birthday").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                    TextField("YYYY-MM-DD", text: $birthday)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Tokens.surface)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Weight (kg)").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
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
                Text(editingPet != nil ? "Save Changes" : "Add Pet")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(name.isEmpty ? Tokens.border : Tokens.accent)
                    .foregroundColor(.white)
                    .cornerRadius(14)
                    .font(.system(size: 16, weight: .semibold))
            }
            .disabled(name.isEmpty)

            if let onCancel {
                Button("Cancel") { onCancel() }
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
