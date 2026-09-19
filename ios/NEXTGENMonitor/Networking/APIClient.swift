import Foundation

enum APIClientError: LocalizedError, Equatable {
    case invalidBaseURL
    case invalidResponse
    case unauthorized
    case httpStatus(Int)
    case transport(String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL: return "The API base URL is invalid."
        case .invalidResponse: return "The server returned an invalid response."
        case .unauthorized: return "Authentication failed. Check the API token."
        case .httpStatus(let status): return "The API returned HTTP \(status)."
        case .transport(let message): return "Network error: \(message)"
        case .decoding(let message): return "The API response could not be decoded: \(message)"
        }
    }
}

actor APIClient {
    static let shared = APIClient()

    private var baseURL = URL(string: "http://100.107.22.92:4100")!
    private var token: String?
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(session: URLSession? = nil) {
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.default
            configuration.timeoutIntervalForRequest = 6
            configuration.timeoutIntervalForResource = 12
            configuration.waitsForConnectivity = false
            configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
            self.session = URLSession(configuration: configuration)
        }
        self.decoder = JSONDecoder.nextgen
        self.encoder = JSONEncoder()
        self.encoder.dateEncodingStrategy = .iso8601
    }

    func configure(baseURL: URL, token: String?) {
        self.baseURL = baseURL
        self.token = token?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func fetchStatus() async throws -> MonitorStatus { try await get("/api/status") }
    func fetchPortfolio() async throws -> PortfolioSummary { try await get("/api/portfolio") }
    func fetchStrategies() async throws -> [StrategyInfo] { try await get("/api/strategies") }
    func fetchSwitches(limit: Int = 300) async throws -> [StrategySwitch] {
        try await get("/api/switches?limit=\(limit)")
    }
    func fetchDecisions(limit: Int = 600) async throws -> [Decision] {
        try await get("/api/decisions?limit=\(limit)")
    }
    func fetchFills(limit: Int = 400) async throws -> [PaperFill] {
        try await get("/api/fills?limit=\(limit)")
    }
    func fetchPositions() async throws -> [PaperPosition] { try await get("/api/positions") }
    func fetchActivity(limit: Int = 500) async throws -> [ActivityEvent] {
        try await get("/api/activity?limit=\(limit)")
    }

    func fetchHistory(period: ChartPeriod, symbol: String?) async throws -> HistoryPayload {
        var components = URLComponents(
            url: baseURL.appending(path: "/api/history"),
            resolvingAgainstBaseURL: false
        )
        var items = [URLQueryItem(name: "period", value: period.rawValue)]
        if let symbol, !symbol.isEmpty {
            items.append(URLQueryItem(name: "symbol", value: symbol))
        }
        components?.queryItems = items
        guard let url = components?.url else { throw APIClientError.invalidBaseURL }
        return try await request(url: url, method: "GET", body: nil)
    }

    @discardableResult
    func send(_ action: SafeControlAction) async throws -> ControlResponse {
        let body = try encoder.encode(["action": action.rawValue])
        let url = baseURL.appending(path: "/api/control")
        return try await request(url: url, method: "POST", body: body)
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
            throw APIClientError.invalidBaseURL
        }
        return try await request(url: url, method: "GET", body: nil)
    }

    private func request<T: Decodable>(
        url: URL,
        method: String,
        body: Data?
    ) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 6
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIClientError.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }
        if http.statusCode == 401 { throw APIClientError.unauthorized }
        guard (200...299).contains(http.statusCode) else {
            throw APIClientError.httpStatus(http.statusCode)
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIClientError.decoding(error.localizedDescription)
        }
    }
}

extension JSONDecoder {
    static var nextgen: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            let fractional = ISO8601DateFormatter()
            fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = fractional.date(from: value) { return date }
            let standard = ISO8601DateFormatter()
            standard.formatOptions = [.withInternetDateTime]
            if let date = standard.date(from: value) { return date }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Invalid ISO-8601 date: \(value)"
            )
        }
        return decoder
    }
}

extension JSONEncoder {
    static var nextgen: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}
