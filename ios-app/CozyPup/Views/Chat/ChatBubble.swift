import SwiftUI

struct ChatBubble: View {
    let role: MessageRole
    let content: String

    private var isUser: Bool { role == .user }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 60) }
            Text(content)
                .font(Tokens.fontBody)
                .foregroundColor(isUser ? Tokens.white : Tokens.text)
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.vertical, 10)
                .background(isUser ? Tokens.bubbleUser : Tokens.bubbleAi)
                .cornerRadius(Tokens.radius)
                .shadow(color: isUser ? .clear : Tokens.dimOverlay.opacity(0.06), radius: 8, y: 2)
                .textSelection(.enabled)
            if !isUser { Spacer(minLength: 60) }
        }
    }
}
