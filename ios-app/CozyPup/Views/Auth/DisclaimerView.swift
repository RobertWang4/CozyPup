import SwiftUI

struct DisclaimerView: View {
    @EnvironmentObject var auth: AuthStore

    var body: some View {
        ZStack {
            Tokens.drawerOverlay.ignoresSafeArea()

            VStack(spacing: 20) {
                Text("Before We Begin")
                    .font(.system(.title2, design: .serif))
                    .fontWeight(.semibold)
                    .foregroundColor(Tokens.text)

                Text("AI suggestions are for reference only and do not constitute veterinary advice. In emergencies, please contact a veterinarian immediately. By continuing, you acknowledge these limitations.")
                    .font(.system(size: 15))
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
                        .foregroundColor(.white)
                        .cornerRadius(14)
                        .font(.system(size: 16, weight: .semibold))
                }
            }
            .padding(28)
            .background(Tokens.surface)
            .cornerRadius(24)
            .shadow(color: .black.opacity(0.1), radius: 20)
            .padding(.horizontal, 32)
        }
        .background(Tokens.bg.ignoresSafeArea())
    }
}
