import Foundation

struct ChatRequest: Encodable {
    let message: String
    let session_id: String?
    let location: LocationCoord?

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
    static let baseURL = "http://localhost:8000/api/v1"

    static func streamChat(message: String, sessionId: String?,
                           location: (lat: Double, lng: Double)?) -> AsyncThrowingStream<SSEEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                let url = URL(string: "\(baseURL)/chat")!
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")

                let body = ChatRequest(
                    message: message,
                    session_id: sessionId,
                    location: location.map { .init(lat: $0.lat, lng: $0.lng) }
                )
                request.httpBody = try? JSONEncoder().encode(body)

                do {
                    let (bytes, response) = try await URLSession.shared.bytes(for: request)
                    guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                        continuation.finish(throwing: URLError(.badServerResponse))
                        return
                    }

                    var currentEvent = ""
                    for try await line in bytes.lines {
                        if line.hasPrefix("event: ") {
                            currentEvent = String(line.dropFirst(7))
                        } else if line.hasPrefix("data: "), !currentEvent.isEmpty {
                            let json = Data(line.dropFirst(6).utf8)
                            switch currentEvent {
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
                            currentEvent = ""
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
