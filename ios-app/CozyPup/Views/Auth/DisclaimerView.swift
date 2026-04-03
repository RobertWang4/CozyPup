import SwiftUI

struct DisclaimerView: View {
    @EnvironmentObject var auth: AuthStore

    var body: some View {
        ZStack {
            Tokens.drawerOverlay.ignoresSafeArea()

            VStack(spacing: 20) {
                Text("Before We Begin")
                    .font(Tokens.fontTitle)
                    .fontWeight(.semibold)
                    .foregroundColor(Tokens.text)

                Text("AI suggestions are for reference only and do not constitute veterinary advice. In emergencies, please contact a veterinarian immediately. By continuing, you acknowledge these limitations.")
                    .font(Tokens.fontBody)
                    .foregroundColor(Tokens.textSecondary)
                    .multilineTextAlignment(.center)

                Button {
                    Haptics.light()
                    auth.acknowledgeDisclaimer()
                } label: {
                    Text("I Understand")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Tokens.accent)
                        .foregroundColor(Tokens.white)
                        .cornerRadius(14)
                        .font(Tokens.fontCallout.weight(.semibold))
                }
            }
            .padding(28)
            .background(Tokens.surface)
            .cornerRadius(24)
            .shadow(color: Tokens.dimOverlay, radius: 20)
            .padding(.horizontal, Tokens.spacing.xl)
        }
        .background(Tokens.bg.ignoresSafeArea())
    }
}

#Preview {
    DisclaimerView()
        .environmentObject(AuthStore())
}
