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

// MARK: - Previews

#Preview("AI Bubble") {
    ChatBubble(role: .assistant, content: "你好！我是 CozyPup，你的宠物健康助手。今天可以帮你记录宠物的饮食、运动和健康情况。")
        .padding()
        .background(Tokens.bg)
}

#Preview("User Bubble") {
    ChatBubble(role: .user, content: "我家狗今天不吃饭怎么办")
        .padding()
        .background(Tokens.bg)
}

#Preview("Long Message") {
    ScrollView {
        VStack(spacing: 12) {
            ChatBubble(role: .user, content: "我家金毛今天早上开始不吃饭，精神也不太好，平时很活泼的，今天一直趴着不动")
            ChatBubble(role: .assistant, content: "金毛不吃饭且精神萎靡需要注意。建议先观察以下几点：\n\n1. 是否有呕吐或腹泻\n2. 鼻头是否干燥发热\n3. 最近是否更换了狗粮\n4. 有没有误食异物的可能\n\n如果症状持续超过24小时，建议及时就医。")
        }
        .padding()
    }
    .background(Tokens.bg)
}
