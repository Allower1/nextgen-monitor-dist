import SwiftUI

struct DecisionJournalView: View {
    @EnvironmentObject private var monitor: MonitorViewModel
    @State private var signalFilter = "ALL"

    private var filtered: [Decision] {
        guard signalFilter != "ALL" else { return monitor.decisions }
        return monitor.decisions.filter { $0.signal.uppercased() == signalFilter }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("Signal", selection: $signalFilter) {
                    Text("All").tag("ALL")
                    Text("Long").tag("LONG")
                    Text("Short").tag("SHORT")
                    Text("Flat").tag("FLAT")
                }
                .pickerStyle(.segmented)
                .padding()

                if filtered.isEmpty {
                    EmptyState(
                        icon: "list.bullet.rectangle.portrait",
                        title: "No decisions",
                        message: "Closed-bar adaptive decisions will appear here."
                    )
                } else {
                    List(filtered) { decision in
                        NavigationLink {
                            DecisionDetailView(decision: decision)
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(decision.symbol)
                                        .font(.headline.monospaced())
                                    SignalBadge(signal: decision.signal)
                                    Spacer()
                                    Image(
                                        systemName: decision.executed
                                            ? "checkmark.circle.fill"
                                            : "clock.fill"
                                    )
                                    .foregroundStyle(
                                        decision.executed ? .green : .orange
                                    )
                                }
                                Text(
                                    "\(Formatters.strategy(decision.strategy)) · \(decision.marketRegime.uppercased())"
                                )
                                .font(.subheadline)
                                Text(
                                    "Bar \(Formatters.dateTime(decision.barTimestamp))"
                                )
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 3)
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Decision Journal")
            .refreshable {
                await monitor.refresh(includeHistory: false)
            }
        }
    }
}

struct DecisionDetailView: View {
    let decision: Decision

    var body: some View {
        List {
            Section("Decision") {
                LabeledContent("Symbol", value: decision.symbol)
                LabeledContent(
                    "Signal",
                    value: decision.signal.uppercased()
                )
                LabeledContent(
                    "Strategy",
                    value: Formatters.strategy(decision.strategy)
                )
                LabeledContent(
                    "Regime",
                    value: decision.marketRegime.uppercased()
                )
                LabeledContent(
                    "Executed",
                    value: decision.executed ? "YES" : "NO"
                )
            }

            Section("Controller") {
                LabeledContent(
                    "Equity",
                    value: Formatters.money(decision.equity)
                )
                LabeledContent(
                    "Pressure",
                    value: Formatters.number(decision.pressure, digits: 6)
                )
            }

            Section("Causal timing") {
                LabeledContent(
                    "Bar timestamp",
                    value: Formatters.dateTime(decision.barTimestamp)
                )
                LabeledContent(
                    "Execution not before",
                    value: Formatters.dateTime(decision.executionNotBefore)
                )
                Text(
                    "The signal is generated from the closed bar and may execute no earlier than the next eligible bar open."
                )
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Section("Frozen policy") {
                Text(decision.policySHA256)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
            }
        }
        .navigationTitle("Decision")
        .navigationBarTitleDisplayMode(.inline)
    }
}
