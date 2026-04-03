import SwiftUI
import AuthenticationServices

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
                SignInWithAppleButton(.signIn) { request in
                    request.requestedScopes = [.fullName, .email]
                } onCompletion: { result in
                    Haptics.light()
                    auth.handleAppleSignIn(result: result)
                }
                .signInWithAppleButtonStyle(.black)
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .cornerRadius(Tokens.spacing.md)

                Button {
                    Haptics.light()
                    auth.loginWithGoogle()
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

                #if targetEnvironment(simulator)
                Button {
                    auth.loginDev()
                } label: {
                    Text("Dev Login (Simulator)")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
                .padding(.top, Tokens.spacing.xs)
                #endif
            }
            .padding(.horizontal, Tokens.spacing.xl)

            if let error = auth.errorMessage {
                Text(error)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
                    .padding(.horizontal, Tokens.spacing.xl)
            }

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Tokens.bg.ignoresSafeArea())
        .overlay {
            if auth.isLoading {
                Tokens.dimOverlay.opacity(0.35).ignoresSafeArea()
                ProgressView()
            }
        }
    }
}

#Preview {
    LoginView()
        .environmentObject(AuthStore())
}
