import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var petStore: PetStore

    var body: some View {
        ScrollView {
            VStack(spacing: Tokens.spacing.lg) {
                VStack(spacing: Tokens.spacing.sm) {
                    Text("Welcome to Cozy Pup!")
                        .font(Tokens.fontTitle)
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
                .padding(.horizontal, Tokens.spacing.lg)
            }
        }
        .background(Tokens.bg.ignoresSafeArea())
    }
}
