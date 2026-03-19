import SwiftUI

struct ChatBubble: View {
    let role: MessageRole
    let content: String

    private var isUser: Bool { role == .user }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 60) }
            Text(content)
                .font(.system(size: 15))
                .foregroundColor(isUser ? .white : Tokens.text)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(isUser ? Tokens.bubbleUser : Tokens.bubbleAi)
                .cornerRadius(Tokens.radius)
                .shadow(color: isUser ? .clear : .black.opacity(0.06), radius: 8, y: 2)
            if !isUser { Spacer(minLength: 60) }
        }
    }
}
