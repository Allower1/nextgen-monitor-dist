#if DEBUG
import Foundation
import SwiftUI

enum PreviewData {
    static let now = Date()

    static let status = MonitorStatus(
        apiOnline: true,
        agentRunning: true,
        reportedAgentRunning: true,
        workerRunning: true,
        currentStage: "adaptive-paper",
        phase6Protected: false,
        latestHealthCheck: "healthy",
        paused: false,
        health: "healthy",
        updatedAt: now,
        heartbeatAt: now.addingTimeInterval(-2),
        heartbeatAgeSeconds: 2,
        stale: false,
        paperMode: true,
        liveTradingEnabled: false,
        profitabilityStatus: "UNPROVEN",
        policySHA256: "ae0b0ba7aecd7c945ce2703a26cf4ac2da154e517db74e4a08c5ebcc16856243",
        policyVersion: 1,
        activeStrategy: "moving_average",
        marketRegime: "trend",
        equity: 10_248.42,
        cash: 7_980.10,
        totalPnl: 248.42,
        pnlPercent: 2.4842,
        unrealizedPnl: 48.10,
        realizedPnl: 200.32,
        drawdown: 0.013,
        drawdownDuration: 2,
        lossStreak: 1,
        dwellBars: 8,
        pressure: 0.72,
        switchCount: 5,
        lastProcessedBar: now.addingTimeInterval(-300),
        lastSwitch: now.addingTimeInterval(-3600),
        pendingSignals: ["BTCUSDT": "LONG", "ETHUSDT": "FLAT"],
        executionNotBefore: now.addingTimeInterval(5),
        statusSourcePresent: true
    )

    static let strategy = StrategyInfo(
        id: "moving_average",
        name: "Moving Average",
        active: true
    )

    static let switchEvent = StrategySwitch(
        id: "12",
        timestamp: now.addingTimeInterval(-3600),
        fromStrategy: "rsi",
        toStrategy: "moving_average",
        marketRegime: "trend",
        equity: 10_100,
        segmentPeak: 10_300,
        drawdown: 0.019417,
        drawdownDuration: 3,
        lossStreak: 2,
        dwellBars: 7,
        pressure: 1.23,
        policySHA256: status.policySHA256,
        reason: "pressure=1.230000>=1; drawdown=0.019417/0.015000; duration=3/2.000000; loss_streak=2/2; dwell=7/4",
        triggeringBarTimestamp: now.addingTimeInterval(-3600)
    )

    static let decision = Decision(
        id: "100",
        barTimestamp: now.addingTimeInterval(-300),
        executionNotBefore: now,
        symbol: "BTCUSDT",
        strategy: "moving_average",
        marketRegime: "trend",
        signal: "LONG",
        equity: 10_248.42,
        pressure: 0.72,
        policySHA256: status.policySHA256,
        executed: false
    )
}

#Preview("Active Strategy") {
    StrategyCard(strategy: PreviewData.strategy)
        .padding()
        .preferredColorScheme(.dark)
}

#Preview("Why Switched") {
    NavigationStack {
        SwitchDetailView(item: PreviewData.switchEvent)
    }
    .preferredColorScheme(.dark)
}

#Preview("Decision") {
    NavigationStack {
        DecisionDetailView(decision: PreviewData.decision)
    }
    .preferredColorScheme(.dark)
}
#endif
