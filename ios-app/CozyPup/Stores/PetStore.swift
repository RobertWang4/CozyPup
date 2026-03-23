import SwiftUI

@MainActor
class PetStore: ObservableObject {
    @Published var pets: [Pet] = []
    @Published var avatarRevision: Int = 0  // incremented on avatar upload to bust cache

    private let key = "cozypup_pets"

    init() { loadLocal() }

    // MARK: - Local cache

    private func loadLocal() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let saved = try? JSONDecoder().decode([Pet].self, from: data) else { return }
        pets = saved
    }

    private func saveLocal() {
        if let data = try? JSONEncoder().encode(pets) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    // MARK: - API

    func fetchFromAPI() async {
        do {
            let fetched: [Pet] = try await APIClient.shared.request("GET", "/pets")
            pets = fetched
            saveLocal()
        } catch {
            print("PetStore.fetchFromAPI failed: \(error)")
        }
    }

    func add(name: String, species: Species, breed: String, birthday: String?, weight: Double?) async {
        struct CreateBody: Encodable {
            let name: String
            let species: String
            let breed: String
            let birthday: String?
            let weight: Double?
        }

        let body = CreateBody(name: name, species: species.rawValue, breed: breed,
                              birthday: birthday, weight: weight)
        do {
            let pet: Pet = try await APIClient.shared.request("POST", "/pets", body: body)
            pets.append(pet)
            saveLocal()
        } catch {
            print("PetStore.add failed: \(error)")
            // Fallback to local
            let pet = Pet(name: name, species: species, breed: breed,
                          birthday: birthday, weight: weight, colorIndex: pets.count)
            pets.append(pet)
            saveLocal()
        }
    }

    func update(_ id: String, name: String, species: Species, breed: String, birthday: String?, weight: Double?) async {
        struct UpdateBody: Encodable {
            let name: String
            let species: String
            let breed: String
            let birthday: String?
            let weight: Double?
        }

        let body = UpdateBody(name: name, species: species.rawValue, breed: breed,
                              birthday: birthday, weight: weight)
        do {
            let updated: Pet = try await APIClient.shared.request("PUT", "/pets/\(id)", body: body)
            if let idx = pets.firstIndex(where: { $0.id == id }) {
                pets[idx] = updated
                saveLocal()
            }
        } catch {
            print("PetStore.update failed: \(error)")
            // Fallback to local
            if let idx = pets.firstIndex(where: { $0.id == id }) {
                pets[idx].name = name
                pets[idx].species = species
                pets[idx].breed = breed
                pets[idx].birthday = birthday
                pets[idx].weight = weight
                saveLocal()
            }
        }
    }

    func remove(_ id: String) async {
        do {
            try await APIClient.shared.requestNoContent("DELETE", "/pets/\(id)")
        } catch {
            print("PetStore.remove failed: \(error)")
        }
        pets.removeAll { $0.id == id }
        saveLocal()
    }

    func uploadAvatar(_ petId: String, imageData: Data) async {
        do {
            let data = try await APIClient.shared.uploadMultipart(
                "/pets/\(petId)/avatar",
                fileData: imageData,
                fileName: "avatar.jpg",
                mimeType: "image/jpeg"
            )
            let updated = try JSONDecoder().decode(Pet.self, from: data)
            if let idx = pets.firstIndex(where: { $0.id == petId }) {
                pets[idx] = updated
                saveLocal()
            }
            avatarRevision += 1
        } catch {
            print("PetStore.uploadAvatar failed: \(error)")
        }
    }

    func getById(_ id: String) -> Pet? {
        pets.first { $0.id == id }
    }
}
