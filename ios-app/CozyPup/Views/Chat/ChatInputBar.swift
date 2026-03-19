import SwiftUI

struct ChatInputBar: View {
    @Binding var text: String
    var isStreaming: Bool
    var isListening: Bool
    var onSend: () -> Void
    var onMicToggle: () -> Void

    private var hasText: Bool { !text.trimmingCharacters(in: .whitespaces).isEmpty }

    var body: some View {
        HStack(spacing: 8) {
            Button { } label: {
                Image(systemName: "plus")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: 44, height: 44)
                    .overlay(Circle().stroke(Tokens.border))
            }

            HStack(spacing: 4) {
                TextField("Talk to Cozy Pup...", text: $text)
                    .font(.system(size: 16))
                    .foregroundColor(Tokens.text)
                    .disabled(isStreaming)
                    .onSubmit { if hasText { onSend() } }

                if hasText {
                    Button {
                        Haptics.light()
                        onSend()
                    } label: {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 40, height: 40)
                            .background(Tokens.accent)
                            .clipShape(Circle())
                    }
                    .disabled(isStreaming)
                } else {
                    Button {
                        onMicToggle()
                    } label: {
                        Image(systemName: "mic")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundColor(isListening ? Tokens.red : Tokens.textSecondary)
                            .frame(width: 40, height: 40)
                            .opacity(isListening ? 0.5 : 1)
                            .animation(.easeInOut(duration: 0.75).repeatForever(autoreverses: true), value: isListening)
                    }
                }
            }
            .padding(.leading, 16)
            .padding(.trailing, 4)
            .frame(height: 48)
            .background(Tokens.surface)
            .cornerRadius(24)
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(Tokens.border))
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 4)
        .background(Tokens.bg)
    }
}
