import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthStore

    var body: some View {
        VStack(spacing: 40) {
            Spacer()
            VStack(spacing: 12) {
                Image("logo")
                    .resizable()
                    .frame(width: Tokens.size.avatarLarge, height: Tokens.size.avatarLarge)
                    .cornerRadius(20)
                Text("Cozy Pup")
                    .font(Tokens.fontLargeTitle)
                    .fontWeight(.semibold)
                    .foregroundColor(Tokens.accent)
                Text("Your pet's personal butler")
                    .font(Tokens.fontBody)
                    .foregroundColor(Tokens.textSecondary)
            }

            VStack(spacing: 14) {
                Button {
                    Haptics.light()
                    auth.login(provider: "apple")
                } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Image(systemName: "apple.logo")
                        Text("Sign in with Apple")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Tokens.spacing.md)
                    .background(Tokens.text)
                    .foregroundColor(Tokens.white)
                    .cornerRadius(Tokens.spacing.md)
                    .font(Tokens.fontCallout.weight(.semibold))
                }

                Button {
                    Haptics.light()
                    auth.login(provider: "google")
                } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Image(systemName: "g.circle.fill")
                        Text("Sign in with Google")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Tokens.spacing.md)
                    .background(Tokens.surface)
                    .foregroundColor(Tokens.text)
                    .overlay(RoundedRectangle(cornerRadius: Tokens.spacing.md).stroke(Tokens.border, lineWidth: 1))
                    .cornerRadius(Tokens.spacing.md)
                    .font(Tokens.fontCallout.weight(.semibold))
                }
            }
            .padding(.horizontal, Tokens.spacing.xl)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Tokens.bg.ignoresSafeArea())
    }
}
