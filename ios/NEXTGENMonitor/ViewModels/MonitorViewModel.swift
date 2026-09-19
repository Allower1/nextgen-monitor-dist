import Foundation
import SwiftUI

@MainActor
final class MonitorViewModel: ObservableObject {
    @Published private(set) var status: MonitorStatus?
    @Published private(set) var strategies: [StrategyInfo] = []
    @Published private(set) var switches: [StrategySwitch] = []
    @Published private(set) var decisions: [Decision] = []
    @Published private(set) var fills: [PaperFill] = []
    @Published private(set) var positions: [PaperPosition] = []
    @Published private(set) var activity: [ActivityEvent] = []
    @Published private(set) var history: HistoryPayload?
    @Published private(set) var apiOnline = false
    @Published private(set) var isRefreshing = false
    @Published private(set) var isUsingCachedState = false
    @Published private(set) var lastSuccessfulRefresh: Date?
    @Published var errorText: String?
    @Published var selectedSymbol: String?
    @Published var chartPeriod: ChartPeriod = .oneDay

    let configuration: ConfigurationStore
    private let client: APIClient
    private let cache: CacheService
    private let notifications: NotificationService
    private var refreshTick = 0

    init(
        configuration: ConfigurationStore = .shared,
        client: APIClient = .shared,
        cache: CacheService = CacheService(),
        notifications: NotificationService = .shared
    ) {
        self.configuration = configuration
        self.client = client
        self.cache = cache
        self.notifications = notifications
        restoreCache()
    }

    var availableSymbols: [String] {
        let values = decisions.map(\.symbol) + positions.map(\.symbol)
        return Array(Set(values)).sorted()
    }

    func runPollingLoop() async {
        await notifications.requestAuthorizationIfNeeded(
            enabled: configuration.notificationsEnabled
        )
        await refresh(includeHistory: true)
        while !Task.isCancelled {
            let nanoseconds = UInt64(
                max(1, configuration.pollInterval) * 1_000_000_000
            )
            try? await Task.sleep(nanoseconds: nanoseconds)
            if Task.isCancelled { break }
            refreshTick += 1
            await refresh(includeHistory: refreshTick % 5 == 0)
        }
    }

    func refresh(includeHistory: Bool = false) async {
        guard let baseURL = configuration.baseURL else {
            apiOnline = false
            errorText = APIClientError.invalidBaseURL.localizedDescription
            isUsingCachedState = status != nil
            return
        }

        isRefreshing = true
        defer { isRefreshing = false }
        await client.configure(
            baseURL: baseURL,
            token: configuration.token.isEmpty ? nil : configuration.token
        )

        let priorStatus = status
        let priorSwitchID = switches.first?.id

        do {
            let freshStatus = try await client.fetchStatus()
            status = freshStatus
            apiOnline = true
            isUsingCachedState = false
            errorText = nil
            lastSuccessfulRefresh = Date()

            async let strategyResult = optional { try await self.client.fetchStrategies() }
            async let switchResult = optional { try await self.client.fetchSwitches() }
            async let decisionResult = optional { try await self.client.fetchDecisions() }
            async let fillResult = optional { try await self.client.fetchFills() }
            async let positionResult = optional { try await self.client.fetchPositions() }
            async let activityResult = optional { try await self.client.fetchActivity() }

            let (
                freshStrategies,
                freshSwitches,
                freshDecisions,
                freshFills,
                freshPositions,
                freshActivity
            ) = await (
                strategyResult,
                switchResult,
                decisionResult,
                fillResult,
                positionResult,
                activityResult
            )

            if let freshStrategies { strategies = freshStrategies }
            if let freshSwitches { switches = freshSwitches }
            if let freshDecisions {
                decisions = freshDecisions
                if selectedSymbol == nil {
                    selectedSymbol = freshDecisions.first?.symbol
                }
            }
            if let freshFills { fills = freshFills }
            if let freshPositions { positions = freshPositions }
            if let freshActivity { activity = freshActivity }

            if includeHistory {
                await refreshHistory()
            }

            notifications.process(
                previous: priorStatus,
                current: freshStatus,
                previousSwitchID: priorSwitchID,
                switches: switches,
                activity: activity,
                enabled: configuration.notificationsEnabled
            )
            saveCache()
        } catch {
            apiOnline = false
            isUsingCachedState = status != nil
            errorText = error.localizedDescription
            notifications.apiUnavailable(
                enabled: configuration.notificationsEnabled
            )
        }
    }

    func refreshHistory() async {
        guard apiOnline else { return }
        do {
            history = try await client.fetchHistory(
                period: chartPeriod,
                symbol: selectedSymbol
            )
            if selectedSymbol == nil {
                selectedSymbol = history?.symbol
            }
            saveCache()
        } catch {
            if history == nil {
                errorText = error.localizedDescription
            }
        }
    }

    func selectPeriod(_ period: ChartPeriod) async {
        chartPeriod = period
        await refreshHistory()
    }

    func selectSymbol(_ symbol: String) async {
        selectedSymbol = symbol
        await refreshHistory()
    }

    func control(_ action: SafeControlAction) async {
        guard let baseURL = configuration.baseURL else {
            errorText = APIClientError.invalidBaseURL.localizedDescription
            return
        }
        await client.configure(
            baseURL: baseURL,
            token: configuration.token.isEmpty ? nil : configuration.token
        )
        do {
            _ = try await client.send(action)
            try? await Task.sleep(nanoseconds: 350_000_000)
            await refresh(includeHistory: false)
        } catch {
            errorText = error.localizedDescription
        }
    }

    func saveSettings() {
        do {
            try configuration.persistToken()
            errorText = nil
        } catch {
            errorText = "Could not save API token to Keychain."
        }
    }

    private func restoreCache() {
        guard let cached = cache.load() else { return }
        status = cached.status
        strategies = cached.strategies
        switches = cached.switches
        decisions = cached.decisions
        fills = cached.fills
        positions = cached.positions
        activity = cached.activity
        history = cached.history
        selectedSymbol = cached.history?.symbol ?? cached.decisions.first?.symbol
        isUsingCachedState = cached.status != nil
    }

    private func saveCache() {
        let snapshot = MonitorCache(
            savedAt: Date(),
            status: status,
            strategies: strategies,
            switches: switches,
            decisions: decisions,
            fills: fills,
            positions: positions,
            activity: activity,
            history: history
        )
        try? cache.save(snapshot)
    }
}

private func optional<T>(
    _ operation: @escaping () async throws -> T
) async -> T? {
    try? await operation()
}
