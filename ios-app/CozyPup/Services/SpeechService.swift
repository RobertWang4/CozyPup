import AVFoundation
import Speech

@MainActor
class SpeechService: ObservableObject {
    @Published var isListening = false
    @Published var transcript = ""
    @Published var audioLevel: Float = 0  // 0.0–1.0 normalized, for waveform UI
    @Published var detectedLanguage: String = ""

    private var audioEngine = AVAudioEngine()
    private var isCancelled = false
    private var interruptionObserver: Any?
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var speechRecognizer: SFSpeechRecognizer?

    func requestPermission() async -> Bool {
        // Request both microphone and speech recognition permissions
        let micGranted = await withCheckedContinuation { cont in
            AVAudioApplication.requestRecordPermission { granted in
                cont.resume(returning: granted)
            }
        }
        guard micGranted else { return false }

        let speechGranted = await withCheckedContinuation { (cont: CheckedContinuation<Bool, Never>) in
            SFSpeechRecognizer.requestAuthorization { status in
                cont.resume(returning: status == .authorized)
            }
        }
        return speechGranted
    }

    func startListening() {
        guard !isListening else { return }
        isCancelled = false
        transcript = ""

        // Use app's language setting from Settings page
        let isChinese = Lang.shared.isZh
        detectedLanguage = isChinese ? "zh" : "en"
        speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: isChinese ? "zh-Hans-CN" : "en-US"))
        guard speechRecognizer?.isAvailable == true else {
            return
        }

        isListening = true
        beginRecognition()
    }

    func stopListening() {
        guard isListening else { return }
        recognitionRequest?.endAudio()
        teardown()
    }

    func cancel() {
        isCancelled = true
        transcript = ""
        recognitionTask?.cancel()
        teardown()
    }

    // MARK: - Private

    private func teardown() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest = nil
        recognitionTask = nil
        isListening = false
        audioLevel = 0
        if let observer = interruptionObserver {
            NotificationCenter.default.removeObserver(observer)
            interruptionObserver = nil
        }
    }

    private func beginRecognition() {
        // Audio session setup
        let audioSession = AVAudioSession.sharedInstance()
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

        // Speech recognition request
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if #available(iOS 18.0, *) {
            request.addsPunctuation = true
        }
        self.recognitionRequest = request

        recognitionTask = speechRecognizer?.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor [weak self] in
                guard let self, !self.isCancelled else { return }

                if let result {
                    self.transcript = result.bestTranscription.formattedString
                }

                if error != nil || result?.isFinal == true {
                    self.teardown()
                }
            }
        }

        // Audio capture — feed buffers to speech recognizer
        let node = audioEngine.inputNode
        let recordingFormat = node.outputFormat(forBus: 0)

        node.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, _ in
            guard let self else { return }

            // Feed audio to speech recognizer
            self.recognitionRequest?.append(buffer)

            // Compute audio level for waveform UI
            let level = self.computeAudioLevel(from: buffer)
            Task { @MainActor [weak self] in
                self?.audioLevel = level
            }
        }

        audioEngine.prepare()
        try? audioEngine.start()
    }

    private nonisolated func computeAudioLevel(from buffer: AVAudioPCMBuffer) -> Float {
        guard let data = buffer.floatChannelData?[0] else { return 0 }
        let count = Int(buffer.frameLength)
        var sum: Float = 0
        for i in 0..<count { sum += abs(data[i]) }
        let avg = sum / Float(max(count, 1))
        // Normalize: typical speech is 0.01–0.1 RMS
        return min(avg * 10, 1.0)
    }
}
