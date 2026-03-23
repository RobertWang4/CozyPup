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
        if isCancelling { return Tokens.redSoft }
        if isListening { return Tokens.accentSoft }
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

// MARK: - Voice Recording Overlay (half-circle + live transcript)

struct VoiceRecordingOverlay: View {
    let transcript: String
    let audioLevel: Float
    let dragOffset: CGFloat
    let cancelThreshold: CGFloat

    private var isCancelling: Bool { dragOffset < cancelThreshold }
    private var pulse: CGFloat { CGFloat(audioLevel) * 20 }
    private let domeHeight: CGFloat = 240

    var body: some View {
        ZStack {
            // Background dims more when cancelling
            Tokens.dimOverlay.opacity(isCancelling ? 0.45 : 0.25)
                .ignoresSafeArea()
                .allowsHitTesting(false)

            // Live transcript in screen center
            VStack {
                Spacer()

                if !transcript.isEmpty {
                    Text(transcript)
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.text)
                        .multilineTextAlignment(.leading)
                        .lineLimit(8)
                        .padding(.horizontal, Tokens.spacing.md)
                        .padding(.vertical, Tokens.spacing.sm + Tokens.spacing.xs)
                        .background(Tokens.surface)
                        .clipShape(RoundedRectangle(cornerRadius: Tokens.radius))
                        .shadow(color: Tokens.dimOverlay.opacity(0.06), radius: 8, y: 2)
                        .padding(.horizontal, Tokens.spacing.xl)
                        .transition(.opacity)
                        .animation(.easeOut(duration: 0.15), value: transcript)
                } else {
                    Text(Lang.shared.isZh ? "正在聆听…" : "Listening…")
                        .font(Tokens.fontHeadline)
                        .foregroundColor(Tokens.textSecondary)
                }

                Spacer()

                // Cancel hint when dragging up
                if isCancelling {
                    Text(Lang.shared.isZh ? "松开取消" : "Release to cancel")
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.red)
                        .transition(.opacity)
                        .padding(.bottom, Tokens.spacing.md)
                }

                // Half-circle dome at bottom
                halfCircleDome
            }
            .ignoresSafeArea(edges: .bottom)
        }
        .animation(.spring(response: 0.25, dampingFraction: 0.85), value: isCancelling)
        .animation(.easeOut(duration: 0.08), value: audioLevel)
    }

    private var halfCircleDome: some View {
        let h = domeHeight + pulse
        return ZStack(alignment: .bottom) {
            // Pulse ring (outer glow)
            DomeRectShape()
                .fill(
                    (isCancelling ? Tokens.red : Tokens.accent)
                        .opacity(isCancelling ? 0.25 : 0.10 + Double(audioLevel) * 0.12)
                )
                .frame(height: h + 12)

            // Main shape
            DomeRectShape()
                .fill(isCancelling ? Tokens.red.opacity(0.85) : Tokens.accentSoft)

            // Waveform bars in the dome area
            domeWaveform
                .padding(.bottom, h * 0.4 + 20)

            // Mic icon in the rect area
            Image(systemName: isCancelling ? "xmark" : "mic.fill")
                .font(Tokens.fontLargeTitle.weight(.bold))
                .foregroundColor(isCancelling ? Tokens.white : Tokens.accent)
                .padding(.bottom, 20)
        }
        .frame(height: h)
    }

    private var domeWaveform: some View {
        TimelineView(.animation(minimumInterval: 0.05)) { context in
            let phase = context.date.timeIntervalSinceReferenceDate
            HStack(spacing: 3) {
                ForEach(0..<24, id: \.self) { i in
                    let center = 12.0
                    let dist = abs(Double(i) - center) / center
                    let envelope = CGFloat(1.0 - dist * 0.6)
                    let voice = CGFloat(audioLevel) * 28 * envelope
                    let wave = CGFloat(sin(phase * 5 + Double(i) * 0.5)) * CGFloat(audioLevel) * 8 * envelope
                    let idle = CGFloat(sin(phase * 2.0 + Double(i) * 0.3)) * 1.5 + 3
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(isCancelling ? Tokens.white.opacity(0.7) : Tokens.accent.opacity(0.55))
                        .frame(width: 2.5, height: max(3, idle + voice + wave))
                }
            }
        }
    }
}

// MARK: - Shapes

/// Rectangle base + fat semicircle on top, merged as one shape.
/// The bottom portion is a full-width rectangle, the top is a semicircular arc.
private struct DomeRectShape: Shape {
    /// How much of the total height is the rectangular base (0–1).
    var rectRatio: CGFloat = 0.4

    func path(in rect: CGRect) -> Path {
        let rectH = rect.height * rectRatio
        let arcTop = rect.maxY - rectH          // where the arc meets the rect
        var path = Path()
        // Bottom-right corner
        path.move(to: CGPoint(x: rect.maxX, y: rect.maxY))
        // Bottom-left corner
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        // Left edge up to arc join
        path.addLine(to: CGPoint(x: rect.minX, y: arcTop))
        // Fat semicircle across the top
        path.addCurve(
            to: CGPoint(x: rect.maxX, y: arcTop),
            control1: CGPoint(x: rect.minX, y: rect.minY),
            control2: CGPoint(x: rect.maxX, y: rect.minY)
        )
        // Right edge back down
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}
