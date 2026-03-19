import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthStore

    var body: some View {
        VStack(spacing: 40) {
            Spacer()
            VStack(spacing: 12) {
                Image("logo")
                    .resizable()
                    .frame(width: 80, height: 80)
                    .cornerRadius(20)
                Text("Cozy Pup")
                    .font(.system(.largeTitle, design: .serif))
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
                    HStack(spacing: 8) {
                        Image(systemName: "apple.logo")
                        Text("Sign in with Apple")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Tokens.text)
                    .foregroundColor(.white)
                    .cornerRadius(16)
                    .font(.system(size: 16, weight: .semibold))
                }

                Button {
                    Haptics.light()
                    auth.login(provider: "google")
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "g.circle.fill")
                        Text("Sign in with Google")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Tokens.surface)
                    .foregroundColor(Tokens.text)
                    .overlay(RoundedRectangle(cornerRadius: 16).stroke(Tokens.border, lineWidth: 1))
                    .cornerRadius(16)
                    .font(.system(size: 16, weight: .semibold))
                }
            }
            .padding(.horizontal, 32)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Tokens.bg.ignoresSafeArea())
    }
}
