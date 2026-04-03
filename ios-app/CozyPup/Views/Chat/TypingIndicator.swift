import SwiftUI

struct TypingIndicator: View {
    var body: some View {
        HStack {
            dotRow
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.vertical, 14)
                .background(Tokens.bubbleAi)
                .cornerRadius(Tokens.radius)
                .shadow(color: Tokens.dimOverlay.opacity(0.06), radius: 8, y: 2)
            Spacer()
        }
    }

    private var dotRow: some View {
        TimelineView(.animation) { context in
            let phase = context.date.timeIntervalSinceReferenceDate * 4
            HStack(spacing: 5) {
                dot(phase: phase, index: 0)
                dot(phase: phase, index: 1)
                dot(phase: phase, index: 2)
            }
        }
    }

    private func dot(phase: Double, index: Int) -> some View {
        Circle()
            .fill(Tokens.typingDot)
            .frame(width: Tokens.spacing.sm, height: Tokens.spacing.sm)
            .offset(y: sin(phase + Double(index) * .pi / 1.5) * 4)
    }
}

#Preview {
    TypingIndicator()
        .padding()
        .background(Tokens.bg)
}
