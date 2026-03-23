import Speech
import AVFoundation

@MainActor
class SpeechService: ObservableObject {
    @Published var isListening = false
    @Published var transcript = ""
    @Published var audioLevel: Float = 0  // 0.0–1.0 normalized, for waveform UI

    private var recognizer: SFSpeechRecognizer?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var isCancelled = false
    private var interruptionObserver: Any?

    init() {
        // Prefer Chinese if user's language is zh, otherwise use device locale
        let lang = UserDefaults.standard.string(forKey: "cozypup_language") ?? "zh"
        let locale = lang == "zh" ? Locale(identifier: "zh-Hans-CN") : Locale.current
        recognizer = SFSpeechRecognizer(locale: locale)
    }

    func requestPermission() async -> Bool {
        await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { status in
                cont.resume(returning: status == .authorized)
            }
        }
    }

    func startListening() {
        guard !isListening, recognizer?.isAvailable == true else { return }
        isCancelled = false

        let audioSession = AVAudioSession.sharedInstance()
        // .voiceChat mode activates hardware noise suppression + echo cancellation
        try? audioSession.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth])
        try? audioSession.setActive(true, options: .notifyOthersOnDeactivation)

        // Listen for audio interruptions (e.g., phone call)
        interruptionObserver = NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.cancel()
            }
        }

        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let request = recognitionRequest else { return }
        request.shouldReportPartialResults = true

        let node = audioEngine.inputNode
        let format = node.outputFormat(forBus: 0)
        node.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            request.append(buffer)
            let level = self?.computeAudioLevel(from: buffer) ?? 0
            Task { @MainActor [weak self] in
                self?.audioLevel = level
            }
        }

        audioEngine.prepare()
        try? audioEngine.start()

        recognitionTask = recognizer?.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }
            if let result {
                Task { @MainActor in
                    if !self.isCancelled {
                        self.transcript = result.bestTranscription.formattedString
                    }
                }
            }
            if error != nil || result?.isFinal == true {
                Task { @MainActor in
                    self.stopListening()
                }
            }
        }

        transcript = ""
        isListening = true
    }

    func stopListening() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        recognitionRequest = nil
        recognitionTask = nil
        isListening = false
        audioLevel = 0
        if let observer = interruptionObserver {
            NotificationCenter.default.removeObserver(observer)
            interruptionObserver = nil
        }
    }

    func cancel() {
        isCancelled = true
        transcript = ""
        stopListening()
    }

    private func computeAudioLevel(from buffer: AVAudioPCMBuffer) -> Float {
        guard let data = buffer.floatChannelData?[0] else { return 0 }
        let count = Int(buffer.frameLength)
        var sum: Float = 0
        for i in 0..<count { sum += abs(data[i]) }
        let avg = sum / Float(max(count, 1))
        // Normalize: typical speech is 0.01–0.1 RMS
        return min(avg * 10, 1.0)
    }
}
