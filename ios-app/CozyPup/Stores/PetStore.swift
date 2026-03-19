import SwiftUI

@MainActor
class PetStore: ObservableObject {
    @Published var pets: [Pet] = []

    private let key = "cozypup_pets"

    init() { load() }

    func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let saved = try? JSONDecoder().decode([Pet].self, from: data) else { return }
        pets = saved
    }

    private func save() {
        if let data = try? JSONEncoder().encode(pets) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    func add(name: String, species: Species, breed: String, birthday: String?, weight: Double?) {
        let pet = Pet(name: name, species: species, breed: breed,
                      birthday: birthday, weight: weight, colorIndex: pets.count)
        pets.append(pet)
        save()
    }

    func update(_ id: String, name: String, species: Species, breed: String, birthday: String?, weight: Double?) {
        guard let idx = pets.firstIndex(where: { $0.id == id }) else { return }
        pets[idx].name = name
        pets[idx].species = species
        pets[idx].breed = breed
        pets[idx].birthday = birthday
        pets[idx].weight = weight
        save()
    }

    func remove(_ id: String) {
        pets.removeAll { $0.id == id }
        save()
    }

    func getById(_ id: String) -> Pet? {
        pets.first { $0.id == id }
    }
}
