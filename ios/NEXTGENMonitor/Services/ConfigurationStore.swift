import SwiftUI

enum ThemePreference: String, CaseIterable, Identifiable {
    case dark = "Dark"
    case light = "Light"
    case system = "System"

    var id: String { rawValue }

    var colorScheme: ColorScheme? {
        switch self {
        case .dark: return .dark
        case .light: return .light
        case .system: return nil
        }
    }
}

@MainActor
final class ConfigurationStore: ObservableObject {
    static let shared = ConfigurationStore()

    @Published var baseURLString: String {
        didSet { UserDefaults.standard.set(baseURLString, forKey: "nextgen.baseURL") }
    }
    @Published var token: String = ""
    @Published var pollInterval: Double {
        didSet {
            let clamped = min(max(pollInterval, 1), 5)
            if clamped != pollInterval { pollInterval = clamped }
            UserDefaults.standard.set(clamped, forKey: "nextgen.pollInterval")
        }
    }
    @Published var theme: ThemePreference {
        didSet { UserDefaults.standard.set(theme.rawValue, forKey: "nextgen.theme") }
    }
    @Published var notificationsEnabled: Bool {
        didSet {
            UserDefaults.standard.set(
                notificationsEnabled,
                forKey: "nextgen.notifications"
            )
        }
    }

    private let keychain = KeychainService()

    init(defaults: UserDefaults = .standard) {
        self.baseURLString = defaults.string(forKey: "nextgen.baseURL")
            ?? "http://100.107.22.92:4100"
        let savedInterval = defaults.object(forKey: "nextgen.pollInterval") as? Double
        self.pollInterval = min(max(savedInterval ?? 2.0, 1), 5)
        let savedTheme = defaults.string(forKey: "nextgen.theme")
        self.theme = ThemePreference(rawValue: savedTheme ?? "") ?? .dark
        if defaults.object(forKey: "nextgen.notifications") == nil {
            self.notificationsEnabled = true
        } else {
            self.notificationsEnabled = defaults.bool(
                forKey: "nextgen.notifications"
            )
        }
        self.token = (try? keychain.readToken()) ?? ""
    }

    var baseURL: URL? {
        let trimmed = baseURLString.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard let url = URL(string: trimmed),
              let scheme = url.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              url.host != nil else {
            return nil
        }
        return url
    }

    func persistToken() throws {
        try keychain.saveToken(token)
    }
}
