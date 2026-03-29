import Foundation

actor APIClient {
    static let shared = APIClient()

    #if targetEnvironment(simulator)
    private let baseURL = "http://localhost:8000/api/v1"
    #else
    private let baseURL = "https://backend-601329501885.northamerica-northeast1.run.app/api/v1"
    #endif

    private var accessToken: String?
    private var refreshToken: String?

    private let tokenKey = "cozypup_access_token"
    private let refreshKey = "cozypup_refresh_token"

    private init() {
        accessToken = UserDefaults.standard.string(forKey: tokenKey)
        refreshToken = UserDefaults.standard.string(forKey: refreshKey)
    }

    // MARK: - URL helpers

    nonisolated func avatarURL(_ path: String) -> URL? {
        guard !path.isEmpty else { return nil }
        // path is like "/api/v1/pets/{id}/avatar", baseURL already has "/api/v1"
        let base = baseURL.replacingOccurrences(of: "/api/v1", with: "")
        return URL(string: "\(base)\(path)")
    }

    // MARK: - Token management

    func setTokens(access: String, refresh: String) {
        accessToken = access
        refreshToken = refresh
        UserDefaults.standard.set(access, forKey: tokenKey)
        UserDefaults.standard.set(refresh, forKey: refreshKey)
    }

    func clearTokens() {
        accessToken = nil
        refreshToken = nil
        UserDefaults.standard.removeObject(forKey: tokenKey)
        UserDefaults.standard.removeObject(forKey: refreshKey)
    }

    func getAccessToken() -> String? {
        accessToken
    }

    // MARK: - Auth requests (no token needed)

    func authRequest<T: Decodable>(_ path: String, body: some Encodable) async throws -> T {
        let url = URL(string: "\(baseURL)\(path)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 || http.statusCode == 201 else {
            throw APIError.badStatus((response as? HTTPURLResponse)?.statusCode ?? 0)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    // MARK: - Authenticated requests

    func request<T: Decodable>(
        _ method: String, _ path: String,
        body: (any Encodable)? = nil,
        query: [String: String]? = nil
    ) async throws -> T {
        let data = try await rawRequest(method, path, body: body, query: query)
        return try JSONDecoder().decode(T.self, from: data)
    }

    func requestNoContent(
        _ method: String, _ path: String
    ) async throws {
        _ = try await rawRequest(method, path)
    }

    private func rawRequest(
        _ method: String, _ path: String,
        body: (any Encodable)? = nil,
        query: [String: String]? = nil
    ) async throws -> Data {
        guard let token = accessToken else { throw APIError.notAuthenticated }

        var components = URLComponents(string: "\(baseURL)\(path)")!
        if let query {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }

        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(body)
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0

        if status == 401 {
            // Try refresh
            if try await attemptRefresh() {
                return try await rawRequest(method, path, body: body, query: query)
            }
            throw APIError.notAuthenticated
        }

        guard (200...299).contains(status) else {
            throw APIError.badStatus(status)
        }
        return data
    }

    private func attemptRefresh() async throws -> Bool {
        guard let refresh = refreshToken else { return false }

        struct RefreshBody: Encodable { let refresh_token: String }
        struct RefreshResp: Decodable { let access_token: String }

        let url = URL(string: "\(baseURL)/auth/refresh")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(RefreshBody(refresh_token: refresh))

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200,
              let resp = try? JSONDecoder().decode(RefreshResp.self, from: data) else {
            return false
        }

        accessToken = resp.access_token
        UserDefaults.standard.set(resp.access_token, forKey: tokenKey)
        return true
    }

    // MARK: - Multipart upload

    func uploadMultipart(
        _ path: String,
        fileData: Data,
        fileName: String,
        mimeType: String
    ) async throws -> Data {
        guard let token = accessToken else { throw APIError.notAuthenticated }

        let url = URL(string: "\(baseURL)\(path)")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0

        if status == 401 {
            if try await attemptRefresh() {
                return try await uploadMultipart(path, fileData: fileData, fileName: fileName, mimeType: mimeType)
            }
            throw APIError.notAuthenticated
        }

        guard (200...299).contains(status) else {
            throw APIError.badStatus(status)
        }
        return data
    }

    // MARK: - SSE streaming with auth

    func streamRequest(_ path: String, body: some Encodable) -> AsyncThrowingStream<(String, Data), Error> {
        // Capture token and URL synchronously on the actor before creating the stream
        let token = self.accessToken
        let urlString = "\(self.baseURL)\(path)"
        let bodyData = try? JSONEncoder().encode(body)

        return AsyncThrowingStream { continuation in
            Task {
                guard let token else {
                    continuation.finish(throwing: APIError.notAuthenticated)
                    return
                }

                // Helper to make the SSE request with a given token
                func doStream(authToken: String) async throws {
                    let url = URL(string: urlString)!
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
                    request.httpBody = bodyData

                    // Use ephemeral session to avoid HTTP connection reuse issues with SSE
                    let sseConfig = URLSessionConfiguration.ephemeral
                    sseConfig.timeoutIntervalForRequest = 120
                    let sseSession = URLSession(configuration: sseConfig)
                    let (bytes, response) = try await sseSession.bytes(for: request)
                    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                    guard status == 200 else {
                        throw APIError.badStatus(status)
                    }

                    var currentEvent = ""
                    for try await line in bytes.lines {
                        if line.hasPrefix("event: ") {
                            currentEvent = String(line.dropFirst(7))
                        } else if line.hasPrefix("data: "), !currentEvent.isEmpty {
                            let json = Data(line.dropFirst(6).utf8)
                            continuation.yield((currentEvent, json))
                            currentEvent = ""
                        }
                    }
                }

                do {
                    try await doStream(authToken: token)
                    continuation.finish()
                } catch APIError.badStatus(401) {
                    // Try refresh and retry once
                    if let refreshed = try? await APIClient.shared.attemptRefreshAndGetToken() {
                        do {
                            try await doStream(authToken: refreshed)
                            continuation.finish()
                        } catch {
                            continuation.finish(throwing: error)
                        }
                    } else {
                        continuation.finish(throwing: APIError.notAuthenticated)
                    }
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    /// Attempt refresh and return the new access token, or nil on failure.
    func attemptRefreshAndGetToken() async throws -> String? {
        guard try await attemptRefresh() else { return nil }
        return accessToken
    }
}

enum APIError: Error, LocalizedError {
    case notAuthenticated
    case badStatus(Int)

    var errorDescription: String? {
        switch self {
        case .notAuthenticated: return "Not authenticated"
        case .badStatus(let code): return "Server error (\(code))"
        }
    }
}
