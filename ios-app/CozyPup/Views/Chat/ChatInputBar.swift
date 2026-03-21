import SwiftUI

struct ChatInputBar: View {
    @Binding var text: String
    var isStreaming: Bool
    var isListening: Bool
    var onSend: () -> Void
    var onMicDown: () -> Void
    var onMicUp: () -> Void
    var onMicCancel: () -> Void

    @State private var dragOffset: CGFloat = 0
    @State private var micPressed = false  // Synchronous guard to prevent multiple onMicDown calls

    private var hasText: Bool { !text.trimmingCharacters(in: .whitespaces).isEmpty }
    private let cancelThreshold: CGFloat = -80

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            Button { } label: {
                Image(systemName: "plus")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: 44, height: 44)
                    .overlay(Circle().stroke(Tokens.border))
            }

            HStack(alignment: .bottom, spacing: 0) {
                TextField(L.chatPlaceholder, text: $text, axis: .vertical)
                    .lineLimit(1...5)
                    .font(.system(size: 16))
                    .foregroundColor(Tokens.text)
                    .disabled(isStreaming)
                    .onSubmit { if hasText { onSend() } }
                    .padding(.vertical, 12)
                    .padding(.leading, 16)
                    .padding(.trailing, 8)

                Group {
                    if hasText {
                        Button {
                            Haptics.light()
                            onSend()
                        } label: {
                            Image(systemName: "arrow.up")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.white)
                                .frame(width: 36, height: 36)
                                .background(Tokens.accent)
                                .clipShape(Circle())
                        }
                        .disabled(isStreaming)
                    } else {
                        micButton
                    }
                }
                .padding(.trailing, 6)
                .padding(.bottom, 4)
            }
            .background(Tokens.surface)
            .clipShape(RoundedRectangle(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(Tokens.border))
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 4)
        .background(Tokens.bg)
    }

    private var micButton: some View {
        Image(systemName: "mic")
            .font(.system(size: 18, weight: .medium))
            .foregroundColor(isListening ? .white : Tokens.textSecondary)
            .frame(width: 36, height: 36)
            .background(isListening ? Tokens.accent : Color.clear)
            .clipShape(Circle())
            .scaleEffect(isListening ? 1.15 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: isListening)
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        if !micPressed {
                            micPressed = true
                            Haptics.medium()
                            onMicDown()
                        }
                        dragOffset = value.translation.height
                    }
                    .onEnded { _ in
                        micPressed = false
                        if dragOffset < cancelThreshold {
                            Haptics.medium()
                            onMicCancel()
                        } else {
                            onMicUp()
                        }
                        dragOffset = 0
                    }
            )
            .disabled(isStreaming)
    }
}
