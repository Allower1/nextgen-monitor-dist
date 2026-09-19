import SwiftUI

struct PositionsView: View {
    @EnvironmentObject private var monitor: MonitorViewModel

    var body: some View {
        Group {
            if monitor.positions.isEmpty {
                EmptyState(
                    icon: "briefcase",
                    title: "No open paper positions",
                    message: "Open NEXTGEN paper positions will appear here."
                )
            } else {
                List(monitor.positions) { position in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text(position.symbol)
                                .font(.headline.monospaced())
                            SignalBadge(signal: position.side)
                            Spacer()
                            Text(Formatters.money(position.unrealizedPnl))
                                .font(.headline.monospacedDigit())
                        }
                        HStack {
                            VStack(alignment: .leading) {
                                Text("Quantity")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(Formatters.number(position.quantity, digits: 8))
                                    .monospacedDigit()
                            }
                            Spacer()
                            VStack(alignment: .trailing) {
                                Text("Exposure")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(Formatters.money(position.exposure))
                                    .monospacedDigit()
                            }
                        }
                        HStack {
                            Text("Entry \(Formatters.money(position.entryPrice))")
                            Spacer()
                            Text("Mark \(Formatters.money(position.markPrice))")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 6)
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Paper Positions")
        .refreshable {
            await monitor.refresh(includeHistory: false)
        }
    }
}

struct TradesView: View {
    @EnvironmentObject private var monitor: MonitorViewModel

    var body: some View {
        Group {
            if monitor.fills.isEmpty {
                EmptyState(
                    icon: "arrow.left.arrow.right",
                    title: "No paper fills",
                    message: "Executed paper fills will appear here."
                )
            } else {
                List(monitor.fills) { fill in
                    NavigationLink {
                        FillDetailView(fill: fill)
                    } label: {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(fill.symbol)
                                    .font(.headline.monospaced())
                                SignalBadge(signal: fill.side)
                                Spacer()
                                Text(Formatters.money(fill.realizedPnl))
                                    .font(.subheadline.monospacedDigit())
                            }
                            Text(
                                "\(Formatters.number(fill.quantity, digits: 8)) @ \(Formatters.money(fill.price))"
                            )
                            .font(.subheadline)
                            Text(Formatters.dateTime(fill.timestamp))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 3)
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Fills & Trades")
        .refreshable {
            await monitor.refresh(includeHistory: false)
        }
    }
}

struct FillDetailView: View {
    let fill: PaperFill

    var body: some View {
        List {
            Section("Fill") {
                LabeledContent("Symbol", value: fill.symbol)
                LabeledContent("Side", value: fill.side)
                LabeledContent(
                    "Quantity",
                    value: Formatters.number(fill.quantity, digits: 8)
                )
                LabeledContent("Price", value: Formatters.money(fill.price))
                if let entry = fill.entryPrice {
                    LabeledContent("Entry", value: Formatters.money(entry))
                }
                if let exit = fill.exitPrice {
                    LabeledContent("Exit", value: Formatters.money(exit))
                }
            }

            Section("Costs & PnL") {
                LabeledContent("Fees", value: Formatters.money(fill.fees))
                LabeledContent(
                    "Slippage",
                    value: fill.slippage.map(Formatters.money) ?? "—"
                )
                LabeledContent(
                    "Realised PnL",
                    value: Formatters.money(fill.realizedPnl)
                )
                if fill.slippage == nil {
                    Text(
                        "Historical slippage is not persisted by the current authoritative accounting journal, so the monitor displays it as unavailable rather than inventing a value."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
            }

            Section("Identity") {
                LabeledContent(
                    "Timestamp",
                    value: Formatters.dateTime(fill.timestamp)
                )
                Text(fill.fillID)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
            }
        }
        .navigationTitle("Fill Detail")
        .navigationBarTitleDisplayMode(.inline)
    }
}
