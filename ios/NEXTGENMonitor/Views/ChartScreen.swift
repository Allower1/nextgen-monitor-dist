import SwiftUI
import Charts

struct ChartScreen: View {
    @EnvironmentObject private var monitor: MonitorViewModel
    @State private var metric: ChartMetric = .price
    @State private var selectedDate: Date?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    controls

                    if let history = monitor.history {
                        chartCard(history)
                        legend
                    } else {
                        EmptyState(
                            icon: "chart.xyaxis.line",
                            title: "No chart history",
                            message: "History appears after the monitoring API returns authoritative price and portfolio data."
                        )
                        .frame(minHeight: 360)
                    }
                }
                .padding()
            }
            .navigationTitle("Chart")
            .refreshable {
                await monitor.refreshHistory()
            }
            .task {
                if monitor.history == nil {
                    await monitor.refreshHistory()
                }
            }
        }
    }

    private var controls: some View {
        SurfaceCard {
            VStack(spacing: 14) {
                Picker("Metric", selection: $metric) {
                    ForEach(ChartMetric.allCases) { item in
                        Text(item.rawValue).tag(item)
                    }
                }
                .pickerStyle(.segmented)

                HStack {
                    if !monitor.availableSymbols.isEmpty {
                        Menu {
                            ForEach(monitor.availableSymbols, id: \.self) { symbol in
                                Button(symbol) {
                                    Task { await monitor.selectSymbol(symbol) }
                                }
                            }
                        } label: {
                            Label(
                                monitor.selectedSymbol ?? "Symbol",
                                systemImage: "bitcoinsign.circle"
                            )
                        }
                    }

                    Spacer()

                    Menu {
                        ForEach(ChartPeriod.allCases) { period in
                            Button(period.rawValue) {
                                Task { await monitor.selectPeriod(period) }
                            }
                        }
                    } label: {
                        Label(
                            monitor.chartPeriod.rawValue,
                            systemImage: "clock"
                        )
                    }
                }
                .font(.subheadline.weight(.semibold))
            }
        }
    }

    private func chartCard(_ history: HistoryPayload) -> some View {
        let metricPoints = points(history)
        return SurfaceCard {
            VStack(alignment: .leading, spacing: 12) {
                chartHeader(history, metricPoints: metricPoints)
                chartPlot(history, metricPoints: metricPoints)
            }
        }
    }

    @ViewBuilder
    private func chartHeader(
        _ history: HistoryPayload,
        metricPoints: [HistoryPoint]
    ) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(history.symbol)
                    .font(.headline.monospaced())
                Text("\(metric.rawValue) · \(history.period)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let selectedDate,
               let point = nearestPoint(to: selectedDate, in: metricPoints) {
                VStack(alignment: .trailing, spacing: 2) {
                    Text(valueText(point.value))
                        .font(.headline.monospacedDigit())
                    Text(Formatters.shortTime(point.timestamp))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func chartPlot(
        _ history: HistoryPayload,
        metricPoints: [HistoryPoint]
    ) -> some View {
        Chart {
            lineMarks(metricPoints)
            fillMarks(history)
            signalMarks(history, metricPoints: metricPoints)
            switchMarks(history)
            selectionMark()
        }
        .frame(height: 330)
        .chartXSelection(value: $selectedDate)
        .chartYAxis {
            AxisMarks(position: .leading)
        }
        .accessibilityLabel(
            "\(history.symbol) \(metric.rawValue) chart for \(history.period)"
        )
    }

    @ChartContentBuilder
    private func lineMarks(_ metricPoints: [HistoryPoint]) -> some ChartContent {
        ForEach(metricPoints) { point in
            LineMark(
                x: .value("Time", point.timestamp),
                y: .value(metric.rawValue, point.value)
            )
            .interpolationMethod(.catmullRom)
        }
    }

    @ChartContentBuilder
    private func fillMarks(_ history: HistoryPayload) -> some ChartContent {
        if metric == .price {
            ForEach(history.fills) { fill in
                if fill.side == "FLAT" {
                    PointMark(
                        x: .value("Fill time", fill.timestamp),
                        y: .value("Fill price", fill.price)
                    )
                    .symbol(.circle)
                    .symbolSize(60)
                    .foregroundStyle(.secondary)
                } else {
                    PointMark(
                        x: .value("Fill time", fill.timestamp),
                        y: .value("Fill price", fill.price)
                    )
                    .symbol(.diamond)
                    .symbolSize(60)
                    .foregroundStyle(.blue)
                }
            }
        }
    }

    @ChartContentBuilder
    private func signalMarks(
        _ history: HistoryPayload,
        metricPoints: [HistoryPoint]
    ) -> some ChartContent {
        ForEach(history.signals) { decision in
            if let y = value(near: decision.barTimestamp, in: metricPoints) {
                PointMark(
                    x: .value("Signal time", decision.barTimestamp),
                    y: .value("Signal", y)
                )
                .symbolSize(34)
                .foregroundStyle(signalColor(decision.signal))
            }
        }
    }

    @ChartContentBuilder
    private func switchMarks(_ history: HistoryPayload) -> some ChartContent {
        ForEach(history.switches) { item in
            if let y = switchValue(item, history: history) {
                PointMark(
                    x: .value("Switch time", item.timestamp),
                    y: .value("Switch", y)
                )
                .symbol(.square)
                .symbolSize(70)
                .foregroundStyle(.orange)
            }
        }
    }

    @ChartContentBuilder
    private func selectionMark() -> some ChartContent {
        if let selectedDate {
            RuleMark(x: .value("Selected", selectedDate))
                .foregroundStyle(.secondary.opacity(0.5))
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [4]))
        }
    }

    private var legend: some View {
        SurfaceCard {
            HStack(spacing: 18) {
                legendItem("LONG", color: .green, symbol: "circle.fill")
                legendItem("SHORT", color: .red, symbol: "circle.fill")
                legendItem("FILL", color: .blue, symbol: "diamond.fill")
                legendItem("SWITCH", color: .orange, symbol: "square.fill")
            }
            .font(.caption2.weight(.semibold))
        }
    }

    private func legendItem(
        _ title: String,
        color: Color,
        symbol: String
    ) -> some View {
        Label {
            Text(title)
        } icon: {
            Image(systemName: symbol)
                .foregroundStyle(color)
        }
    }

    private func points(_ history: HistoryPayload) -> [HistoryPoint] {
        switch metric {
        case .price: return history.price
        case .equity: return history.equity
        case .pnl: return history.pnl
        case .drawdown: return history.drawdown
        }
    }

    private func nearestPoint(
        to date: Date,
        in points: [HistoryPoint]
    ) -> HistoryPoint? {
        points.min {
            abs($0.timestamp.timeIntervalSince(date))
                < abs($1.timestamp.timeIntervalSince(date))
        }
    }

    private func value(
        near date: Date,
        in points: [HistoryPoint]
    ) -> Double? {
        nearestPoint(to: date, in: points)?.value
    }

    private func switchValue(
        _ item: StrategySwitch,
        history: HistoryPayload
    ) -> Double? {
        switch metric {
        case .equity:
            return item.equity
        case .pnl:
            if let status = monitor.status {
                let initial = status.equity - status.totalPnl
                return item.equity - initial
            }
            return value(near: item.timestamp, in: history.pnl)
        case .drawdown:
            return item.drawdown
        case .price:
            return value(near: item.timestamp, in: history.price)
        }
    }

    private func valueText(_ value: Double) -> String {
        switch metric {
        case .price, .equity, .pnl:
            return Formatters.money(value)
        case .drawdown:
            return Formatters.percent(value)
        }
    }

    private func signalColor(_ signal: String) -> Color {
        switch signal.uppercased() {
        case "LONG": return .green
        case "SHORT": return .red
        default: return .secondary
        }
    }
}
