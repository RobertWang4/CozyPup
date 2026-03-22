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
        HStack(alignment: .bottom, spacing: Tokens.spacing.sm) {
            Button { } label: {
                Image(systemName: "plus")
                    .font(Tokens.fontTitle.weight(.medium))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: Tokens.size.buttonMedium, height: Tokens.size.buttonMedium)
                    .overlay(Circle().stroke(Tokens.border))
            }

            HStack(alignment: .bottom, spacing: 0) {
                TextField(L.chatPlaceholder, text: $text, axis: .vertical)
                    .lineLimit(1...5)
                    .font(Tokens.fontCallout)
                    .foregroundColor(Tokens.text)
                    .disabled(isStreaming)
                    .onSubmit { if hasText { onSend() } }
                    .padding(.vertical, 12)
                    .padding(.leading, Tokens.spacing.md)
                    .padding(.trailing, Tokens.spacing.sm)

                Group {
                    if hasText {
                        Button {
                            Haptics.light()
                            onSend()
                        } label: {
                            Image(systemName: "arrow.up")
                                .font(Tokens.fontCallout.weight(.semibold))
                                .foregroundColor(Tokens.white)
                                .frame(width: Tokens.size.buttonSmall, height: Tokens.size.buttonSmall)
                                .background(Tokens.accent)
                                .clipShape(Circle())
                        }
                        .disabled(isStreaming)
                    } else {
                        micButton
                    }
                }
                .padding(.trailing, 6)
                .padding(.bottom, Tokens.spacing.xs)
            }
            .background(Tokens.surface)
            .clipShape(RoundedRectangle(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(Tokens.border))
        }
        .padding(.horizontal, 12)
        .padding(.top, Tokens.spacing.sm)
        .padding(.bottom, Tokens.spacing.xs)
        .background(Tokens.bg)
    }

    private var micButton: some View {
        Image(systemName: "mic")
            .font(Tokens.fontHeadline.weight(.medium))
            .foregroundColor(isListening ? Tokens.white : Tokens.textSecondary)
            .frame(width: Tokens.size.buttonSmall, height: Tokens.size.buttonSmall)
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
