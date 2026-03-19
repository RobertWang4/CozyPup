import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var petStore: PetStore

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                VStack(spacing: 8) {
                    Text("Welcome to Cozy Pup!")
                        .font(.system(.title, design: .serif))
                        .fontWeight(.semibold)
                        .foregroundColor(Tokens.text)
                    Text("Let's set up your first pet")
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.textSecondary)
                }
                .padding(.top, 60)

                PetFormView { name, species, breed, birthday, weight in
                    Task {
                        await petStore.add(name: name, species: species, breed: breed,
                                           birthday: birthday, weight: weight)
                    }
                }
                .padding(.horizontal, 24)
            }
        }
        .background(Tokens.bg.ignoresSafeArea())
    }
}
