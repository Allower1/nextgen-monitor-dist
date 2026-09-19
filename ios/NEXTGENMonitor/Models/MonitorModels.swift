import Foundation

struct MonitorStatus: Codable, Equatable {
    let apiOnline: Bool
    let agentRunning: Bool
    let reportedAgentRunning: Bool?
    let workerRunning: Bool
    let currentStage: String?
    let phase6Protected: Bool?
    let latestHealthCheck: String?
    let paused: Bool
    let health: String
    let updatedAt: Date
    let heartbeatAt: Date?
    let heartbeatAgeSeconds: Double?
    let stale: Bool
    let paperMode: Bool
    let liveTradingEnabled: Bool
    let profitabilityStatus: String
    let policySHA256: String
    let policyVersion: Int?
    let activeStrategy: String
    let marketRegime: String
    let equity: Double
    let cash: Double
    let totalPnl: Double
    let pnlPercent: Double
    let unrealizedPnl: Double
    let realizedPnl: Double
    let drawdown: Double
    let drawdownDuration: Int
    let lossStreak: Int
    let dwellBars: Int
    let pressure: Double
    let switchCount: Int
    let lastProcessedBar: Date?
    let lastSwitch: Date?
    let pendingSignals: [String: String]
    let executionNotBefore: Date?
    let statusSourcePresent: Bool

    var heartbeatDescription: String {
        guard let age = heartbeatAgeSeconds else { return "No heartbeat" }
        if age < 1 { return "now" }
        if age < 60 { return "\(Int(age))s ago" }
        return "\(Int(age / 60))m ago"
    }

    var isAgentOffline: Bool { !agentRunning || stale }
}

struct StrategyInfo: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let active: Bool
}

struct StrategySwitch: Codable, Identifiable, Equatable {
    let id: String
    let timestamp: Date
    let fromStrategy: String
    let toStrategy: String
    let marketRegime: String
    let equity: Double
    let segmentPeak: Double
    let drawdown: Double
    let drawdownDuration: Int
    let lossStreak: Int
    let dwellBars: Int
    let pressure: Double
    let policySHA256: String
    let reason: String
    let triggeringBarTimestamp: Date?

    var reasonSegments: [String] {
        reason.split(separator: ";")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }
}

struct Decision: Codable, Identifiable, Equatable {
    let id: String
    let barTimestamp: Date
    let executionNotBefore: Date?
    let symbol: String
    let strategy: String
    let marketRegime: String
    let signal: String
    let equity: Double
    let pressure: Double
    let policySHA256: String
    let executed: Bool
}

struct PaperFill: Codable, Identifiable, Equatable {
    let id: String
    let timestamp: Date
    let symbol: String
    let side: String
    let quantity: Double
    let entryPrice: Double?
    let exitPrice: Double?
    let price: Double
    let fees: Double
    let slippage: Double?
    let realizedPnl: Double
    let fillID: String
    let notes: String
}

struct PaperPosition: Codable, Identifiable, Equatable {
    let id: String
    let symbol: String
    let side: String
    let quantity: Double
    let entryPrice: Double
    let markPrice: Double
    let unrealizedPnl: Double
    let exposure: Double
}

struct HistoryPoint: Codable, Identifiable, Equatable {
    let timestamp: Date
    let value: Double
    var id: Date { timestamp }
}

struct HistoryPayload: Codable, Equatable {
    let symbol: String
    let period: String
    let price: [HistoryPoint]
    let equity: [HistoryPoint]
    let pnl: [HistoryPoint]
    let drawdown: [HistoryPoint]
    let signals: [Decision]
    let fills: [PaperFill]
    let switches: [StrategySwitch]
}

struct ActivityEvent: Codable, Identifiable, Equatable {
    let id: String
    let timestamp: Date
    let type: String
    let title: String
    let detail: String
}

struct PortfolioSummary: Codable, Equatable {
    let equity: Double
    let cash: Double
    let unrealizedPnl: Double
    let realizedPnl: Double
}

struct ControlResponse: Codable, Equatable {
    let accepted: Bool
    let commandId: String
    let action: String
    let time: Date
}

enum SafeControlAction: String, Codable {
    case status = "STATUS"
    case pause = "PAUSE"
    case resume = "RESUME_STATUS"
}

enum ChartMetric: String, CaseIterable, Identifiable {
    case price = "Price"
    case equity = "Equity"
    case pnl = "PnL"
    case drawdown = "Drawdown"
    var id: String { rawValue }
}

enum ChartPeriod: String, CaseIterable, Identifiable {
    case oneHour = "1H"
    case sixHours = "6H"
    case oneDay = "1D"
    case oneWeek = "1W"
    case all = "ALL"
    var id: String { rawValue }
}

struct MonitorCache: Codable, Equatable {
    let savedAt: Date
    let status: MonitorStatus?
    let strategies: [StrategyInfo]
    let switches: [StrategySwitch]
    let decisions: [Decision]
    let fills: [PaperFill]
    let positions: [PaperPosition]
    let activity: [ActivityEvent]
    let history: HistoryPayload?
}
