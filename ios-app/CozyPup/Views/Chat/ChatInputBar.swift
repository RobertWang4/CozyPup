import SwiftUI
import PhotosUI

struct ChatInputBar: View {
    @Binding var text: String
    @Binding var pendingPhotos: [Data]
    var isStreaming: Bool
    var isListening: Bool
    var transcript: String
    var audioLevel: Float
    var onSend: () -> Void
    var onMicDown: () -> Void
    var onMicUp: () -> Void
    var onMicCancel: () -> Void
    @Binding var dragOffsetOut: CGFloat

    @State private var voiceMode = false
    @State private var dragOffset: CGFloat = 0
    @State private var micPressed = false
    @State private var showPhotoPicker = false
    @State private var showCamera = false
    @State private var selectedItems: [PhotosPickerItem] = []
    @State private var showPlusMenu = false

    private var hasText: Bool { !text.trimmingCharacters(in: .whitespaces).isEmpty }
    private var hasContent: Bool { hasText || !pendingPhotos.isEmpty }
    private let cancelThreshold: CGFloat = -120
    private var isCancelling: Bool { dragOffset < cancelThreshold }
    private let maxPhotos = 9

    var body: some View {
        VStack(spacing: 0) {
            // Photo preview row
            if !pendingPhotos.isEmpty {
                photoPreview
            }

            HStack(alignment: .bottom, spacing: Tokens.spacing.sm) {
                if !voiceMode {
                    plusButton
                }

                if voiceMode {
                    voiceBar
                } else {
                    textBar
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, Tokens.spacing.sm)
            .padding(.bottom, Tokens.spacing.xs)
        }
        .background(Tokens.bg.ignoresSafeArea(edges: .bottom))
        .animation(.easeInOut(duration: 0.2), value: voiceMode)
        .animation(.easeInOut(duration: 0.2), value: pendingPhotos.count)
        .photosPicker(
            isPresented: $showPhotoPicker,
            selection: $selectedItems,
            maxSelectionCount: maxPhotos - pendingPhotos.count,
            matching: .images
        )
        .onChange(of: selectedItems) { _, items in
            Task { await loadPhotos(from: items) }
        }
        .fullScreenCover(isPresented: $showCamera) {
            CameraView { imageData in
                if pendingPhotos.count < maxPhotos {
                    pendingPhotos.append(imageData)
                }
            }
            .ignoresSafeArea()
        }
    }

    // MARK: - Plus Button (menu)

    private var plusButton: some View {
        Menu {
            Button {
                showPhotoPicker = true
            } label: {
                Label(
                    Lang.shared.isZh ? "从相册选择" : "Photo Library",
                    systemImage: "photo.on.rectangle"
                )
            }

            Button {
                showCamera = true
            } label: {
                Label(
                    Lang.shared.isZh ? "拍照" : "Take Photo",
                    systemImage: "camera"
                )
            }
        } label: {
            Image(systemName: "plus")
                .font(Tokens.fontTitle.weight(.medium))
                .foregroundColor(Tokens.textSecondary)
                .frame(width: Tokens.size.buttonMedium, height: Tokens.size.buttonMedium)
                .overlay(Circle().stroke(Tokens.border))
        }
    }

    // MARK: - Photo Preview

    private var photoPreview: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Tokens.spacing.sm) {
                ForEach(Array(pendingPhotos.enumerated()), id: \.offset) { index, data in
                    ZStack(alignment: .topTrailing) {
                        if let uiImage = UIImage(data: data) {
                            Image(uiImage: uiImage)
                                .resizable()
                                .scaledToFill()
                                .frame(width: 64, height: 64)
                                .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
                        }

                        // Delete button
                        Button {
                            withAnimation { _ = pendingPhotos.remove(at: Int(index)) }
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 18))
                                .foregroundColor(Tokens.white)
                                .background(Circle().fill(Color.black.opacity(0.5)))
                        }
                        .offset(x: 6, y: -6)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, Tokens.spacing.sm)
        }
    }

    // MARK: - Text Input Bar

    private var textBar: some View {
        HStack(alignment: .bottom, spacing: 0) {
            TextField(L.chatPlaceholder, text: $text, axis: .vertical)
                .lineLimit(1...5)
                .font(Tokens.fontCallout)
                .foregroundColor(Tokens.text)
                .onSubmit { if hasContent { onSend() } }
                .padding(.vertical, 12)
                .padding(.leading, Tokens.spacing.md)
                .padding(.trailing, Tokens.spacing.sm)

            Group {
                if hasContent {
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
                    Button {
                        Haptics.light()
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                            voiceMode = true
                        }
                    } label: {
                        Image(systemName: "mic")
                            .font(Tokens.fontHeadline.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                            .frame(width: Tokens.size.buttonSmall, height: Tokens.size.buttonSmall)
                    }
                }
            }
            .padding(.trailing, 6)
            .padding(.bottom, Tokens.spacing.xs)
        }
        .background(Tokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 24))
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(Tokens.border))
    }

    // MARK: - Photo Loading

    private func loadPhotos(from items: [PhotosPickerItem]) async {
        for item in items {
            guard pendingPhotos.count < maxPhotos else { break }
            if let data = try? await item.loadTransferable(type: Data.self) {
                // Compress to JPEG
                if let uiImage = UIImage(data: data),
                   let jpeg = uiImage.jpegData(compressionQuality: 0.7) {
                    await MainActor.run { pendingPhotos.append(jpeg) }
                }
            }
        }
        await MainActor.run { selectedItems = [] }
    }

    // MARK: - Voice Bar (morphs into dome when pressed)

    private var voiceBar: some View {
        HStack(spacing: Tokens.spacing.sm) {
            // Keyboard button (hide when listening)
            if !isListening {
                Button {
                    Haptics.light()
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                        voiceMode = false
                    }
                } label: {
                    Image(systemName: "keyboard")
                        .font(Tokens.fontHeadline.weight(.medium))
                        .foregroundColor(Tokens.textSecondary)
                        .frame(width: Tokens.size.buttonMedium, height: Tokens.size.buttonMedium)
                        .overlay(Circle().stroke(Tokens.border))
                }
                .transition(.opacity)
            }

            // The morphing bar
            holdToTalkMorph
        }
        .animation(.spring(response: 0.3, dampingFraction: 0.8), value: isListening)
    }

    private var holdToTalkMorph: some View {
        let pulse = CGFloat(audioLevel) * 8

        return ZStack {
            RoundedRectangle(cornerRadius: isListening ? 28 : 24)
                .fill(barFillColor)
            if !isListening {
                RoundedRectangle(cornerRadius: 24)
                    .stroke(barBorderColor)
            }

            if isListening {
                barWaveform
            } else {
                HStack(spacing: Tokens.spacing.sm) {
                    Image(systemName: "mic.fill")
                        .font(Tokens.fontSubheadline)
                        .foregroundColor(Tokens.textSecondary)
                    Text(Lang.shared.isZh ? "按住 说话" : "Hold to Talk")
                        .font(Tokens.fontCallout)
                        .foregroundColor(Tokens.textSecondary)
                }
            }
        }
        .frame(height: isListening ? 56 + pulse : Tokens.size.buttonMedium)
        .shadow(color: isListening ? Tokens.accent.opacity(0.12) : .clear,
                radius: isListening ? 12 : 0, y: isListening ? -4 : 0)
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { value in
                    if !micPressed {
                        micPressed = true
                        Haptics.medium()
                        onMicDown()
                    }
                    dragOffset = value.translation.height
                    dragOffsetOut = value.translation.height
                }
                .onEnded { _ in
                    micPressed = false
                    if isCancelling {
                        Haptics.medium()
                        onMicCancel()
                    } else {
                        onMicUp()
                    }
                    dragOffset = 0
                    dragOffsetOut = 0
                }
        )
    }

    private var barFillColor: Color {
        if isCancelling { return Color(hex: "F5C4C4") } // More red to match dome
        if isListening { return Color(hex: "F0DDD3") }
        return Tokens.bg
    }

    private var barBorderColor: Color {
        if isCancelling { return Tokens.red.opacity(0.3) }
        if isListening { return Tokens.accent.opacity(0.3) }
        return Tokens.border
    }

    // MARK: - Bar Waveform

    private var barWaveform: some View {
        TimelineView(.animation(minimumInterval: 0.05)) { context in
            let phase = context.date.timeIntervalSinceReferenceDate
            let idle = CGFloat(sin(phase * 2) * 1 + 3)
            let voice = CGFloat(audioLevel)
            HStack(spacing: 2) {
                ForEach(0..<22, id: \.self) { i in
                    let center = 11.0
                    let dist = abs(Double(i) - center) / center
                    let env = CGFloat(1.0 - dist * 0.3)
                    let vH = voice * 30 * env
                    let vW = CGFloat(sin(phase * 6 + Double(i) * 0.5) * Double(voice) * 10) * env
                    let iW = CGFloat(sin(phase * 2.5 + Double(i) * 0.3)) * 1
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(isCancelling ? Tokens.red.opacity(0.5) : Tokens.accent.opacity(0.65))
                        .frame(width: 2.5, height: Swift.max(3, idle + vH + vW + iW))
                }
            }
        }
    }
}

// MARK: - Voice Recording Overlay (dome + transcript)

struct VoiceRecordingOverlay: View {
    let transcript: String
    let audioLevel: Float
    let dragOffset: CGFloat
    let cancelThreshold: CGFloat

    private var isCancelling: Bool { dragOffset < cancelThreshold }
    private var screenW: CGFloat { UIScreen.main.bounds.width }
    private var pulse: CGFloat { CGFloat(audioLevel) * 20 }

    // Warm cream palette
    private var domeBase: Color { Color(hex: "E8D5C4") }
    private var domeTop: Color { Color(hex: "F5ECE3") }
    private var cancelBase: Color { Color(hex: "E8A0A0") } // More red
    private var cancelTop: Color { Color(hex: "F5C4C4") } // More red

    var body: some View {
        ZStack {
            // Dim background (darker like WeChat)
            Color.black.opacity(0.6)
                .ignoresSafeArea()
                .allowsHitTesting(false)

            VStack(spacing: 0) {
                Spacer()

                // Green Bubble with waveform
                transcriptBubble
                    .padding(.bottom, 40)
                    .transition(.opacity.combined(with: .scale(scale: 0.9)))

                // Dome
                dome
            }
            .ignoresSafeArea(edges: .bottom)
        }
        .animation(.spring(response: 0.25, dampingFraction: 0.85), value: isCancelling)
        .animation(.easeOut(duration: 0.08), value: audioLevel)
    }

    private var transcriptBubble: some View {
        VStack(spacing: 0) {
            // Green bubble like WeChat
            HStack(spacing: 4) {
                // Simple waveform inside bubble
                ForEach(0..<15, id: \.self) { i in
                    let h = CGFloat.random(in: 4...16) + CGFloat(audioLevel) * 10
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color.black.opacity(0.6))
                        .frame(width: 2, height: h)
                        .animation(.linear(duration: 0.1), value: audioLevel)
                }
            }
            .frame(height: 40)
            .padding(.horizontal, 24)
            .padding(.vertical, 12)
            .background(Color(hex: "58C877")) // WeChat green
            .cornerRadius(12)
            .shadow(color: .black.opacity(0.1), radius: 5, y: 2)

            // Small triangle tail pointing down
            BubbleTail()
                .fill(Color(hex: "58C877"))
                .frame(width: 16, height: 8)
        }
        .padding(.horizontal, Tokens.spacing.xl)
        // Always show the green bubble when recording, ignore transcript text for now to match WeChat style
    }

    private var dome: some View {
        let arcHeight: CGFloat = 200 + pulse * 0.5
        let isCancelZone = dragOffset < -80 && dragOffset > -160 // Left zone for cancel
        let isTextZone = dragOffset < -80 && dragOffset < -160 // Right zone for text (not implemented yet, but for UI)
        
        return ZStack(alignment: .bottom) {
            // Main dome body - Dark gray like WeChat
            DomeShape(arcHeight: arcHeight)
                .fill(Color(white: 0.15))
                .shadow(color: .black.opacity(0.3), radius: 10, y: -5)

            // Content
            VStack(spacing: 20) {
                // Action buttons row
                HStack(spacing: 60) {
                    // Cancel Button
                    VStack(spacing: 8) {
                        ZStack {
                            Circle()
                                .fill(isCancelZone ? Color.white : Color(white: 0.25))
                                .frame(width: isCancelZone ? 70 : 60, height: isCancelZone ? 70 : 60)
                            
                            Image(systemName: "xmark")
                                .font(.system(size: 24, weight: .medium))
                                .foregroundColor(isCancelZone ? .black : .white)
                        }
                        
                        Text("Cancel")
                            .font(.system(size: 14))
                            .foregroundColor(.white)
                            .opacity(isCancelZone ? 1 : 0.6)
                    }
                    .offset(y: isCancelZone ? -10 : 0)
                    .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isCancelZone)
                    
                    // Convert to Text Button (Placeholder for UI)
                    VStack(spacing: 8) {
                        ZStack {
                            Circle()
                                .fill(Color(white: 0.25))
                                .frame(width: 60, height: 60)
                            
                            Image(systemName: "text.quote")
                                .font(.system(size: 24, weight: .medium))
                                .foregroundColor(.white)
                        }
                        
                        Text("Convert to Text")
                            .font(.system(size: 14))
                            .foregroundColor(.white)
                            .opacity(0.6)
                    }
                }
                .padding(.bottom, 20)

                // Release to send text
                Text(isCancelZone ? "Release to cancel" : "Release to send")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(isCancelZone ? Tokens.red : .white.opacity(0.8))
                    .padding(.bottom, 40)
            }
            .padding(.bottom, 20) // Extra padding for safe area
        }
        .frame(height: arcHeight)
    }

    private var domeWaveform: some View {
        EmptyView() // Removed old waveform
    }
}

// MARK: - Shapes

/// Pure semi-circle dome
private struct DomeShape: Shape {
    var arcHeight: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        // Start bottom-left
        path.move(to: CGPoint(x: rect.minX, y: rect.maxY))
        // Arc from left to right (quad curve with control point at top-center)
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX, y: rect.maxY),
            control: CGPoint(x: rect.midX, y: rect.maxY - arcHeight)
        )
        path.closeSubpath()
        return path
    }
}

/// Open path for the dome's top curve only.
private struct DomeArcHighlightShape: Shape {
    var arcHeight: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX, y: rect.maxY),
            control: CGPoint(x: rect.midX, y: rect.maxY - arcHeight)
        )
        return path
    }
}

private struct BubbleTail: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        path.closeSubpath()
        return path
    }
}
