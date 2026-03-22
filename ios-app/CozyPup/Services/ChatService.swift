import Foundation

struct ChatRequest: Encodable {
    let message: String
    let session_id: String?
    let location: LocationCoord?
    let language: String?

    struct LocationCoord: Encodable {
        let lat: Double
        let lng: Double
    }
}

enum SSEEvent {
    case token(String)
    case card(CardData)
    case emergency(EmergencyData)
    case done(intent: String, sessionId: String)
}

class ChatService {
    static func streamChat(message: String, sessionId: String?,
                           location: (lat: Double, lng: Double)?) -> AsyncThrowingStream<SSEEvent, Error> {
        let lang = UserDefaults.standard.string(forKey: "cozypup_language") ?? "zh"
        return AsyncThrowingStream { continuation in
            Task {
                let body = ChatRequest(
                    message: message,
                    session_id: sessionId,
                    location: location.map { .init(lat: $0.lat, lng: $0.lng) },
                    language: lang
                )

                let stream = await APIClient.shared.streamRequest("/chat", body: body)

                do {
                    for try await (event, json) in stream {
                        switch event {
                        case "token":
                            if let obj = try? JSONDecoder().decode([String: String].self, from: json),
                               let text = obj["text"] {
                                continuation.yield(.token(text))
                            }
                        case "card":
                            if let card = try? JSONDecoder().decode(CardData.self, from: json) {
                                continuation.yield(.card(card))
                            }
                        case "emergency":
                            if let obj = try? JSONDecoder().decode([String: String].self, from: json),
                               let msg = obj["message"], let action = obj["action"] {
                                continuation.yield(.emergency(EmergencyData(message: msg, action: action)))
                            }
                        case "done":
                            if let obj = try? JSONDecoder().decode([String: String].self, from: json) {
                                continuation.yield(.done(
                                    intent: obj["intent"] ?? "chat",
                                    sessionId: obj["session_id"] ?? ""
                                ))
                            }
                        default: break
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}
