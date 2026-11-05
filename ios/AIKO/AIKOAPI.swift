import Foundation
import Security

struct ChatResponse: Decodable {
    let reply: String
}

struct ImageResponse: Decodable {
    let imageURLs: [String]

    enum CodingKeys: String, CodingKey {
        case imageURLs = "image_urls"
    }
}

struct Reminder: Decodable, Identifiable {
    let id: String
    let title: String
    let dueAt: Date
    let notified: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case dueAt = "due_at"
        case notified
    }
}

struct AIKOAPIClient {
    private let baseURL: URL
    private let apiKey: String
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    init?(baseURLString: String, apiKey: String) {
        guard
            let url = URL(string: baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)),
            let scheme = url.scheme?.lowercased(),
            let host = url.host?.lowercased(),
            url.user == nil,
            url.password == nil,
            url.query == nil,
            url.fragment == nil,
            !apiKey.isEmpty,
            scheme == "https" || (scheme == "http" && ["localhost", "127.0.0.1"].contains(host))
        else {
            return nil
        }
        self.baseURL = url
        self.apiKey = apiKey
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601
    }

    func sendChat(_ message: String, sessionID: String) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: [
            "message": message,
            "session_id": sessionID
        ])
        let response: ChatResponse = try await request(
            path: "v1/chat",
            method: "POST",
            body: body
        )
        return response.reply
    }

    func generateImages(prompt: String) async throws -> [Data] {
        let body = try JSONSerialization.data(withJSONObject: ["prompt": prompt])
        let response: ImageResponse = try await request(
            path: "v1/images",
            method: "POST",
            body: body
        )
        var images: [Data] = []
        for path in response.imageURLs {
            guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
                throw APIError.invalidResponse
            }
            images.append(try await requestData(url: url))
        }
        return images
    }

    func getReminders() async throws -> [Reminder] {
        try await request(path: "v1/reminders", method: "GET")
    }

    func createReminder(title: String, dueAt: Date) async throws -> Reminder {
        let body = try encoder.encode(ReminderRequest(title: title, dueAt: dueAt))
        return try await request(path: "v1/reminders", method: "POST", body: body)
    }

    private func request<Response: Decodable>(
        path: String,
        method: String,
        body: Data? = nil
    ) async throws -> Response {
        let components = path.split(separator: "/")
        let url = components.reduce(baseURL) {
            $0.appendingPathComponent(String($1))
        }
        return try await request(url: url, method: method, body: body)
    }

    private func request<Response: Decodable>(
        url: URL,
        method: String,
        body: Data? = nil
    ) async throws -> Response {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.setValue(apiKey, forHTTPHeaderField: "X-AIKO-API-Key")
        if body != nil {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw APIError.invalidResponse
        }
    }

    private func requestData(url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        request.setValue(apiKey, forHTTPHeaderField: "X-AIKO-API-Key")
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        return data
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let response = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200..<300).contains(response.statusCode) else {
            let message = (try? JSONDecoder().decode(APIErrorBody.self, from: data).detail)
                ?? "The AIKO server returned HTTP \(response.statusCode)."
            throw APIError.server(message)
        }
    }
}

private struct ReminderRequest: Encodable {
    let title: String
    let dueAt: Date

    enum CodingKeys: String, CodingKey {
        case title
        case dueAt = "due_at"
    }
}

private struct APIErrorBody: Decodable {
    let detail: String
}

enum APIError: LocalizedError {
    case invalidResponse
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "The AIKO server returned an invalid response."
        case .server(let message):
            return message
        }
    }
}

enum APIKeychain {
    private static let service = Bundle.main.bundleIdentifier ?? "com.aiko.ios"
    private static let account = "server-api-key"

    static func load() -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data,
              let value = String(data: data, encoding: .utf8) else {
            return ""
        }
        return value
    }

    static func save(_ value: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        let data = Data(value.utf8)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var insert = query
            insert[kSecValueData as String] = data
            let insertStatus = SecItemAdd(insert as CFDictionary, nil)
            guard insertStatus == errSecSuccess else {
                throw APIError.server("Could not save the API key to iPhone Keychain.")
            }
        } else if status != errSecSuccess {
            throw APIError.server("Could not save the API key to iPhone Keychain.")
        }
    }
}
