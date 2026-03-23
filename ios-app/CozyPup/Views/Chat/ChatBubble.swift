import SwiftUI
import AVFoundation
import Translation

struct ChatBubble: View {
    let role: MessageRole
    let content: String

    private var isUser: Bool { role == .user }
    @State private var showShareSheet = false
    @State private var showTranslation = false

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 60) }
            Text(content)
                .font(Tokens.fontBody)
                .foregroundColor(isUser ? Tokens.white : Tokens.text)
                .textSelection(.enabled)
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.vertical, 10)
                .background(isUser ? Tokens.bubbleUser : Tokens.bubbleAi)
                .cornerRadius(Tokens.radius)
                .shadow(color: isUser ? .clear : Tokens.dimOverlay.opacity(0.06), radius: 8, y: 2)
                .contextMenu {
                    Button {
                        UIPasteboard.general.string = content
                    } label: {
                        Label("复制", systemImage: "doc.on.doc")
                    }
                    Button {
                        showTranslation = true
                    } label: {
                        Label("翻译", systemImage: "character.book.closed")
                    }
                    Button {
                        showShareSheet = true
                    } label: {
                        Label("分享", systemImage: "square.and.arrow.up")
                    }
                    Button {
                        let utterance = AVSpeechUtterance(string: content)
                        utterance.voice = AVSpeechSynthesisVoice(language: content.range(of: "\\p{Han}", options: .regularExpression) != nil ? "zh-CN" : "en-US")
                        utterance.rate = 0.5
                        AVSpeechSynthesizer().speak(utterance)
                    } label: {
                        Label("朗读", systemImage: "speaker.wave.2")
                    }
                }
                .sheet(isPresented: $showShareSheet) {
                    ShareSheet(items: [content])
                }
                .modifier(TranslationModifier(isPresented: $showTranslation, text: content))
            if !isUser { Spacer(minLength: 60) }
        }
    }

}

struct TranslationModifier: ViewModifier {
    @Binding var isPresented: Bool
    let text: String

    func body(content: Content) -> some View {
        if #available(iOS 17.4, *) {
            content.translationPresentation(isPresented: $isPresented, text: text)
        } else {
            content
        }
    }
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
