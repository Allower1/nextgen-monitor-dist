import SwiftUI

struct SwitchHistoryView: View {
    @EnvironmentObject private var monitor: MonitorViewModel

    var body: some View {
        NavigationStack {
            Group {
                if monitor.switches.isEmpty {
                    EmptyState(
                        icon: "arrow.triangle.2.circlepath",
                        title: "No strategy switches",
                        message: "Switches will appear here when the adaptive controller changes strategy."
                    )
                } else {
                    List(monitor.switches) { item in
                        NavigationLink {
                            SwitchDetailView(item: item)
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(Formatters.strategy(item.fromStrategy))
                                    Image(systemName: "arrow.right")
                                        .foregroundStyle(.secondary)
                                    Text(Formatters.strategy(item.toStrategy))
                                        .fontWeight(.semibold)
                                    Spacer()
                                    Text(Formatters.shortTime(item.timestamp))
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                HStack(spacing: 12) {
                                    Label(
                                        item.marketRegime.uppercased(),
                                        systemImage: "waveform.path.ecg"
                                    )
                                    Text("DD \(Formatters.percent(item.drawdown))")
                                    Text("P \(Formatters.number(item.pressure, digits: 2))")
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Strategy Switches")
            .refreshable {
                await monitor.refresh(includeHistory: false)
            }
        }
    }
}

struct SwitchDetailView: View {
    let item: StrategySwitch

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                SurfaceCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("WHY DID THE BOT SWITCH?")
                            .font(.title2.bold())
                        Text(
                            "\(Formatters.strategy(item.fromStrategy)) → \(Formatters.strategy(item.toStrategy))"
                        )
                        .font(.title3.weight(.semibold))
                        Text(item.timestamp.formatted(date: .complete, time: .standard))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                SurfaceCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("AUTHORITATIVE JOURNAL REASON")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                        ForEach(Array(item.reasonSegments.enumerated()), id: \.offset) { _, segment in
                            Label(segment, systemImage: "checkmark.circle")
                                .font(.body.monospaced())
                        }
                    }
                }

                SurfaceCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("CONTROLLER VALUES AT SWITCH")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                        LabeledContent("Market regime", value: item.marketRegime.uppercased())
                        LabeledContent("Equity", value: Formatters.money(item.equity))
                        LabeledContent("Segment peak", value: Formatters.money(item.segmentPeak))
                        LabeledContent("Drawdown", value: Formatters.percent(item.drawdown))
                        LabeledContent("Drawdown duration", value: "\(item.drawdownDuration) bars")
                        LabeledContent("Loss streak", value: "\(item.lossStreak)")
                        LabeledContent("Dwell", value: "\(item.dwellBars) bars")
                        LabeledContent("Pressure", value: Formatters.number(item.pressure, digits: 6))
                    }
                }

                SurfaceCard {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("WHAT CHANGED")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                        Text(
                            "The controller journal recorded pressure at or above its switching condition after the required dwell. The exact measured values and thresholds are shown above exactly as persisted by NEXTGEN."
                        )
                        .font(.callout)
                        Text(
                            "The iPhone app does not recalculate or reinterpret the adaptive policy."
                        )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                }

                SurfaceCard {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("POLICY SHA256")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(.secondary)
                        Text(item.policySHA256)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                    }
                }
            }
            .padding()
        }
        .navigationTitle("Switch Detail")
        .navigationBarTitleDisplayMode(.inline)
    }
}
