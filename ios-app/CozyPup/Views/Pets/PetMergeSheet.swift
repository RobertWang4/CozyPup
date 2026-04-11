import SwiftUI

struct PetMergeSheet: View {
    let shareToken: String
    @EnvironmentObject var petStore: PetStore
    @State private var selectedPetId: String?
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    var onDone: (() -> Void)?

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            Text("Merge with your pet?")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if petStore.pets.isEmpty {
                Text("You don't have any pets yet. The shared pet will be added to your list.")
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding()
            } else {
                ScrollView {
                    VStack(spacing: Tokens.spacing.sm) {
                        ForEach(petStore.pets, id: \.id) { pet in
                            Button {
                                selectedPetId = selectedPetId == pet.id ? nil : pet.id
                            } label: {
                                HStack(spacing: Tokens.spacing.sm) {
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(Color(hex: pet.colorHex))
                                        .frame(width: 40, height: 40)

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(pet.name)
                                            .font(Tokens.fontBody.weight(.semibold))
                                            .foregroundColor(Tokens.text)
                                        Text(pet.breed)
                                            .font(Tokens.fontCaption)
                                            .foregroundColor(Tokens.textSecondary)
                                    }

                                    Spacer()

                                    Circle()
                                        .strokeBorder(
                                            selectedPetId == pet.id ? Tokens.accent : Tokens.border,
                                            lineWidth: 1.5
                                        )
                                        .background(
                                            Circle().fill(
                                                selectedPetId == pet.id ? Tokens.accent : Color.clear
                                            )
                                        )
                                        .overlay(
                                            selectedPetId == pet.id
                                                ? Image(systemName: "checkmark")
                                                    .font(.system(size: 10, weight: .bold))
                                                    .foregroundColor(Tokens.white)
                                                : nil
                                        )
                                        .frame(width: 22, height: 22)
                                }
                                .padding(Tokens.spacing.sm)
                                .background(
                                    selectedPetId == pet.id ? Tokens.accentSoft : Tokens.surface
                                )
                                .cornerRadius(Tokens.radiusSmall)
                                .overlay(
                                    RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                        .stroke(
                                            selectedPetId == pet.id ? Tokens.accent : Tokens.border,
                                            lineWidth: 1.5
                                        )
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
            }

            Button {
                Task { await acceptShare() }
            } label: {
                if isSubmitting {
                    ProgressView().tint(Tokens.white)
                } else {
                    Text(selectedPetId != nil ? "Confirm Merge" : "Add Without Merging")
                }
            }
            .font(Tokens.fontBody.weight(.semibold))
            .foregroundColor(Tokens.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Tokens.accent)
            .cornerRadius(Tokens.radiusSmall)
            .disabled(isSubmitting)

            if selectedPetId != nil {
                Button {
                    selectedPetId = nil
                } label: {
                    Text("Skip — add without merging")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }

            Spacer()
        }
        .padding(Tokens.spacing.md)
    }

    private func acceptShare() async {
        isSubmitting = true
        defer { isSubmitting = false }

        struct Body: Encodable {
            let token: String
            let merge_pet_id: String?
        }
        struct Resp: Decodable {
            let status: String
            let pet_id: String
        }

        do {
            let _: Resp = try await APIClient.shared.request(
                "POST", "/pets/accept-share",
                body: Body(token: shareToken, merge_pet_id: selectedPetId)
            )
            await petStore.fetchFromAPI()
            onDone?()
        } catch {
            errorMessage = "Failed to accept share: \(error.localizedDescription)"
        }
    }
}

#Preview {
    PetMergeSheet(shareToken: "test-token")
        .environmentObject(PetStore())
}
