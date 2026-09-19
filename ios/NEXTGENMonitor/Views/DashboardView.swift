import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var monitor: MonitorViewModel
    @State private var confirmation: SafeControlAction?
    @State private var showingSettings = false

    private let columns = [
        GridItem(.flexible(), spacing: 10),
        GridItem(.flexible(), spacing: 10)
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 16) {
                    connectionHeader

                    if let status = monitor.status {
                        hero(status)
                        strategySection(status)
                        controllerSection(status)
                        timingSection(status)
                        pendingSection(status)
                        portfolioLinks
                        policySection(status)
                    } else {
                        EmptyState(
                            icon: "antenna.radiowaves.left.and.right.slash",
                            title: "No agent state yet",
                            message: "Configure the private NEXTGEN API in Settings. The last valid state will be cached automatically."
                        )
                        .frame(minHeight: 320)
                    }

                    if let error = monitor.errorText {
                        SurfaceCard {
                            Label(error, systemImage: "exclamationmark.triangle.fill")
                                .font(.footnote)
                                .foregroundStyle(.orange)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("NEXTGEN Monitor")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingSettings = true
                    } label: {
                        Image(systemName: "gearshape.fill")
                    }
                    .accessibilityLabel("Settings")
                }
            }
            .refreshable {
                await monitor.refresh(includeHistory: true)
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
                    .environmentObject(monitor.configuration)
                    .environmentObject(monitor)
            }
            .confirmationDialog(
                confirmationTitle,
                isPresented: Binding(
                    get: { confirmation != nil },
                    set: { if !$0 { confirmation = nil } }
                ),
                titleVisibility: .visible
            ) {
                if let confirmation {
                    Button(
                        confirmation == .pause ? "Pause agent" : "Resume agent",
                        role: confirmation == .pause ? .destructive : nil
                    ) {
                        let action = confirmation
                        self.confirmation = nil
                        Task { await monitor.control(action) }
                    }
                    Button("Cancel", role: .cancel) {
                        self.confirmation = nil
                    }
                }
            } message: {
                Text(
                    confirmation == .pause
                    ? "This pauses new adaptive paper decisions. It does not enable live trading."
                    : "This resumes the existing adaptive paper runtime."
                )
            }
        }
    }

    private var connectionHeader: some View {
        SurfaceCard {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    StatusPill(
                        title: monitor.apiOnline ? "API ONLINE" : "API OFFLINE",
                        active: monitor.apiOnline
                    )
                    if let status = monitor.status {
                        StatusPill(
                            title: status.agentRunning ? "AGENT ONLINE" : "AGENT OFFLINE",
                            active: status.agentRunning,
                            warning: status.stale
                        )
                        StatusPill(
                            title: "PAPER MODE",
                            active: true
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                if monitor.isUsingCachedState {
                    Label(
                        "Showing last valid cached state",
                        systemImage: "clock.arrow.circlepath"
                    )
                    .font(.caption)
                    .foregroundStyle(.orange)
                }

                if let refreshed = monitor.lastSuccessfulRefresh {
                    Text("Last API refresh: \(refreshed.formatted(date: .omitted, time: .standard))")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func hero(_ status: MonitorStatus) -> some View {
        VStack(spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                MetricCard(
                    title: "Equity",
                    value: Formatters.money(status.equity),
                    subtitle: "Cash \(Formatters.money(status.cash))",
                    emphasized: true
                )
                MetricCard(
                    title: "Total PnL",
                    value: Formatters.money(status.totalPnl),
                    subtitle: Formatters.pnlPercent(status.pnlPercent),
                    emphasized: true
                )
            }

            LazyVGrid(columns: columns, spacing: 10) {
                MetricCard(
                    title: "Strategy",
                    value: Formatters.strategy(status.activeStrategy),
                    subtitle: status.marketRegime.uppercased()
                )
                MetricCard(
                    title: status.paused ? "State" : "Heartbeat",
                    value: status.paused ? "PAUSED" : status.heartbeatDescription,
                    subtitle: status.health.uppercased()
                )
                MetricCard(
                    title: "Drawdown",
                    value: Formatters.percent(status.drawdown),
                    subtitle: "\(status.drawdownDuration) bars"
                )
                MetricCard(
                    title: "Pressure",
                    value: Formatters.number(status.pressure, digits: 3),
                    subtitle: "Switches \(status.switchCount)"
                )
            }

            controlBar(status)
        }
    }

    private func controlBar(_ status: MonitorStatus) -> some View {
        SurfaceCard {
            HStack(spacing: 10) {
                Button {
                    Task { await monitor.control(.status) }
                } label: {
                    Label("STATUS", systemImage: "arrow.clockwise")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)

                if status.paused {
                    Button {
                        confirmation = .resume
                    } label: {
                        Label("RESUME", systemImage: "play.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                } else {
                    Button {
                        confirmation = .pause
                    } label: {
                        Label("PAUSE", systemImage: "pause.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .tint(.orange)
                }
            }
            .disabled(!monitor.apiOnline)
        }
    }

    private func strategySection(_ status: MonitorStatus) -> some View {
        SurfaceCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("ADAPTIVE STRATEGIES")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
                    .tracking(0.7)

                LazyVGrid(columns: columns, spacing: 10) {
                    ForEach(displayStrategies(active: status.activeStrategy)) { strategy in
                        StrategyCard(strategy: strategy)
                    }
                }
            }
        }
    }

    private func controllerSection(_ status: MonitorStatus) -> some View {
        SurfaceCard {
            VStack(alignment: .leading, spacing: 14) {
                Text("CONTROLLER")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)

                LabeledContent("Market regime") {
                    Text(status.marketRegime.uppercased())
                }
                LabeledContent("Loss streak") {
                    Text("\(status.lossStreak)")
                        .monospacedDigit()
                }
                LabeledContent("Dwell bars") {
                    Text("\(status.dwellBars)")
                        .monospacedDigit()
                }
                LabeledContent("Pressure") {
                    Text(Formatters.number(status.pressure, digits: 4))
                        .monospacedDigit()
                }
                LabeledContent("Switch count") {
                    Text("\(status.switchCount)")
                        .monospacedDigit()
                }
            }
        }
    }

    private func timingSection(_ status: MonitorStatus) -> some View {
        SurfaceCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("CAUSAL TIMELINE")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)

                LabeledContent(
                    "Last processed bar",
                    value: Formatters.dateTime(status.lastProcessedBar)
                )
                LabeledContent(
                    "Last switch",
                    value: Formatters.dateTime(status.lastSwitch)
                )
                LabeledContent(
                    "Execution not before",
                    value: Formatters.dateTime(status.executionNotBefore)
                )
            }
        }
    }

    @ViewBuilder
    private func pendingSection(_ status: MonitorStatus) -> some View {
        if !status.pendingSignals.isEmpty {
            SurfaceCard {
                VStack(alignment: .leading, spacing: 10) {
                    Text("PENDING SIGNAL")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                    ForEach(status.pendingSignals.keys.sorted(), id: \.self) { symbol in
                        HStack {
                            Text(symbol)
                                .font(.headline.monospaced())
                            Spacer()
                            SignalBadge(signal: status.pendingSignals[symbol] ?? "FLAT")
                        }
                    }
                }
            }
        }
    }

    private var portfolioLinks: some View {
        SurfaceCard {
            VStack(spacing: 0) {
                NavigationLink {
                    PositionsView()
                } label: {
                    dashboardLink(
                        "Positions",
                        subtitle: "\(monitor.positions.count) paper positions",
                        icon: "briefcase.fill"
                    )
                }

                Divider().padding(.leading, 44)

                NavigationLink {
                    TradesView()
                } label: {
                    dashboardLink(
                        "Fills & Trades",
                        subtitle: "\(monitor.fills.count) recorded fills",
                        icon: "arrow.left.arrow.right"
                    )
                }
            }
        }
    }

    private func dashboardLink(
        _ title: String,
        subtitle: String,
        icon: String
    ) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .frame(width: 28)
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .foregroundStyle(.primary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption.weight(.bold))
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 12)
    }

    private func policySection(_ status: MonitorStatus) -> some View {
        SurfaceCard {
            VStack(alignment: .leading, spacing: 8) {
                Text("FROZEN POLICY SHA256")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.secondary)
                Text(status.policySHA256.isEmpty ? "Unavailable" : status.policySHA256)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
                Text("ENGINEERING_READY / PROFITABILITY_UNPROVEN")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func displayStrategies(active: String) -> [StrategyInfo] {
        if monitor.strategies.count == 4 {
            return monitor.strategies
        }
        let values = [
            ("rsi", "RSI"),
            ("moving_average", "Moving Average"),
            ("macd", "MACD"),
            ("combo", "Combo")
        ]
        return values.map {
            StrategyInfo(id: $0.0, name: $0.1, active: $0.0 == active)
        }
    }

    private var confirmationTitle: String {
        switch confirmation {
        case .pause: return "Pause NEXTGEN?"
        case .resume: return "Resume NEXTGEN?"
        default: return ""
        }
    }
}
