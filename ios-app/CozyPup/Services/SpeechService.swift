import AVFoundation

@MainActor
class SpeechService: ObservableObject {
    @Published var isListening = false
    @Published var transcript = ""
    @Published var audioLevel: Float = 0  // 0.0–1.0 normalized, for waveform UI
    @Published var detectedLanguage: String = ""

    private var audioEngine = AVAudioEngine()
    private var isCancelled = false
    private var interruptionObserver: Any?
    private var webSocket: URLSessionWebSocketTask?
    private var deepgramToken: String?
    private var receiveTask: Task<Void, Never>?
    private var converter: AVAudioConverter?
    private var accumulatedTranscript = ""

    private struct DeepgramTokenResponse: Decodable {
        let token: String
    }

    private func ensureToken() async -> String? {
        if let token = deepgramToken { return token }
        do {
            let resp: DeepgramTokenResponse = try await APIClient.shared.request("GET", "/auth/deepgram-token")
            deepgramToken = resp.token
            return resp.token
        } catch {
            print("Failed to fetch Deepgram token: \(error)")
            return nil
        }
    }

    func requestPermission() async -> Bool {
        await withCheckedContinuation { cont in
            AVAudioApplication.requestRecordPermission { granted in
                cont.resume(returning: granted)
            }
        }
    }

    func startListening() {
        guard !isListening else { return }
        isCancelled = false
        transcript = ""
        detectedLanguage = ""
        accumulatedTranscript = ""
        isListening = true

        Task {
            guard let token = await ensureToken() else {
                isListening = false
                return
            }
            beginStreaming(token: token)
        }
    }

    func stopListening() {
        guard isListening else { return }

        // Send CloseStream message before closing
        let closeMessage = URLSessionWebSocketTask.Message.string("{\"type\":\"CloseStream\"}")
        webSocket?.send(closeMessage) { _ in }

        teardown()
    }

    func cancel() {
        isCancelled = true
        transcript = ""
        teardown()
    }

    // MARK: - Private

    private func teardown() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        webSocket?.cancel(with: .normalClosure, reason: nil)
        webSocket = nil
        converter = nil
        receiveTask?.cancel()
        receiveTask = nil
        isListening = false
        audioLevel = 0
        if let observer = interruptionObserver {
            NotificationCenter.default.removeObserver(observer)
            interruptionObserver = nil
        }
    }

    private func beginStreaming(token: String) {
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

        // WebSocket connection
        let urlString = "wss://api.deepgram.com/v1/listen?model=nova-3&language=multi&punctuate=true&interim_results=true&encoding=linear16&sample_rate=16000&channels=1"
        var request = URLRequest(url: URL(string: urlString)!)
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")

        let session = URLSession(configuration: .default)
        let ws = session.webSocketTask(with: request)
        ws.resume()
        self.webSocket = ws

        // Start receive loop
        receiveTask = Task { [weak self] in
            await self?.receiveLoop()
        }

        // Audio capture
        let node = audioEngine.inputNode
        let inputFormat = node.outputFormat(forBus: 0)
        let outputFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true)!
        let audioConverter = AVAudioConverter(from: inputFormat, to: outputFormat)!
        self.converter = audioConverter

        node.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, _ in
            guard let self else { return }

            // Compute audio level from input buffer
            let level = self.computeAudioLevel(from: buffer)
            Task { @MainActor [weak self] in
                self?.audioLevel = level
            }

            // Convert to 16kHz mono PCM16
            let ratio = 16000.0 / inputFormat.sampleRate
            let frameCount = AVAudioFrameCount(Double(buffer.frameLength) * ratio)
            guard frameCount > 0,
                  let converted = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: frameCount) else { return }

            var convError: NSError?
            var consumed = false
            audioConverter.convert(to: converted, error: &convError) { _, outStatus in
                if consumed {
                    outStatus.pointee = .noDataNow
                    return nil
                }
                consumed = true
                outStatus.pointee = .haveData
                return buffer
            }
            guard convError == nil, converted.frameLength > 0 else { return }

            let byteCount = Int(converted.frameLength) * 2
            let data = Data(bytes: converted.int16ChannelData![0], count: byteCount)
            self.webSocket?.send(.data(data)) { _ in }
        }

        audioEngine.prepare()
        try? audioEngine.start()
    }

    private func receiveLoop() async {
        guard let ws = webSocket else { return }
        while !Task.isCancelled {
            do {
                let message = try await ws.receive()
                switch message {
                case .string(let text):
                    if let data = text.data(using: .utf8) {
                        await handleDeepgramResponse(data)
                    }
                case .data(let data):
                    await handleDeepgramResponse(data)
                @unknown default:
                    break
                }
            } catch {
                // WebSocket closed or error
                await MainActor.run { [weak self] in
                    guard let self, self.isListening else { return }
                    self.teardown()
                }
                break
            }
        }
    }

    @MainActor
    private func handleDeepgramResponse(_ data: Data) {
        guard !isCancelled else { return }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let channel = json["channel"] as? [String: Any],
              let alternatives = channel["alternatives"] as? [[String: Any]],
              let firstAlt = alternatives.first,
              let text = firstAlt["transcript"] as? String else {
            return
        }

        // Extract detected language
        if let languages = firstAlt["languages"] as? [String],
           let lang = languages.first, !lang.isEmpty {
            detectedLanguage = lang
        }

        let isFinal = json["is_final"] as? Bool ?? false

        if isFinal && !text.isEmpty {
            if !accumulatedTranscript.isEmpty {
                accumulatedTranscript += " "
            }
            accumulatedTranscript += text
            transcript = accumulatedTranscript
        } else if !text.isEmpty {
            // Show interim result
            transcript = accumulatedTranscript + (accumulatedTranscript.isEmpty ? "" : " ") + text
        }
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
