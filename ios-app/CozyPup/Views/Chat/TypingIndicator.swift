import SwiftUI

struct TypingIndicator: View {
    @State private var phase = 0.0

    var body: some View {
        HStack {
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { i in
                    Circle()
                        .fill(Tokens.typingDot)
                        .frame(width: 8, height: 8)
                        .offset(y: sin(phase + Double(i) * .pi / 1.5) * 4)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(Tokens.bubbleAi)
            .cornerRadius(Tokens.radius)
            .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
            Spacer()
        }
        .onAppear {
            withAnimation(.linear(duration: 1.0).repeatForever(autoreverses: false)) {
                phase = .pi * 2
            }
        }
    }
}
