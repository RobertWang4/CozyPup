import SwiftUI

struct VoiceInputOverlay: View {
    let transcript: String
    let audioLevel: Float
    let isCancelling: Bool

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            // Live transcript
            if !transcript.isEmpty {
                Text(transcript)
                    .font(.system(size: 18))
                    .foregroundColor(Tokens.text)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .transition(.opacity)
            }

            // Waveform bars
            waveformBars
                .frame(height: 40)
                .padding(.horizontal, 60)

            // Mic circle with pulse
            ZStack {
                Circle()
                    .fill(isCancelling ? Tokens.red.opacity(0.15) : Tokens.accentSoft)
                    .frame(width: 100 + CGFloat(audioLevel) * 40,
                           height: 100 + CGFloat(audioLevel) * 40)
                    .animation(.easeOut(duration: 0.1), value: audioLevel)

                Circle()
                    .fill(isCancelling ? Tokens.red : Tokens.accent)
                    .frame(width: 80, height: 80)
                    .shadow(color: (isCancelling ? Tokens.red : Tokens.accent).opacity(0.3), radius: 12)

                Image(systemName: isCancelling ? "xmark" : "mic.fill")
                    .font(.system(size: 32, weight: .medium))
                    .foregroundColor(.white)
            }

            // Hint text
            Text(isCancelling ? L.voiceReleaseCancel : L.voiceSwipeCancel)
                .font(.system(size: 13))
                .foregroundColor(isCancelling ? Tokens.red : Tokens.textSecondary)

            Spacer()
                .frame(height: 120)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.ultraThinMaterial)
        .animation(.easeInOut(duration: 0.2), value: isCancelling)
    }

    private var waveformBars: some View {
        TimelineView(.animation(minimumInterval: 0.05)) { context in
            let phase = context.date.timeIntervalSinceReferenceDate
            HStack(spacing: 3) {
                ForEach(0..<20, id: \.self) { i in
                    let base = CGFloat(audioLevel) * 30
                    let wave = sin(phase * 6 + Double(i) * 0.4) * Double(audioLevel) * 10
                    RoundedRectangle(cornerRadius: 2)
                        .fill(isCancelling ? Tokens.red.opacity(0.4) : Tokens.waveform.opacity(0.6))
                        .frame(width: 3, height: max(4, base + CGFloat(wave)))
                }
            }
        }
    }
}
