import SwiftUI

struct StrategyCard: View {
    let strategy: StrategyInfo

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: strategyIcon(strategy.id))
                    .font(.title3)
                Spacer()
                if strategy.active {
                    Image(systemName: "bolt.fill")
                        .foregroundStyle(.green)
                }
            }
            Text(strategy.name)
                .font(.headline)
            Text(strategy.active ? "ACTIVE NOW" : "Standby")
                .font(.caption2.weight(.bold))
                .foregroundStyle(strategy.active ? .green : .secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 112, alignment: .leading)
        .background(
            strategy.active
                ? Color.green.opacity(0.13)
                : Color.secondary.opacity(0.06),
            in: RoundedRectangle(cornerRadius: 16)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .stroke(
                    strategy.active
                        ? Color.green.opacity(0.8)
                        : Color.secondary.opacity(0.12),
                    lineWidth: strategy.active ? 2 : 1
                )
        }
        .accessibilityLabel(
            strategy.active
                ? "\(strategy.name), active strategy"
                : strategy.name
        )
    }

    private func strategyIcon(_ id: String) -> String {
        switch id {
        case "rsi": return "waveform.path.ecg"
        case "moving_average": return "chart.line.uptrend.xyaxis"
        case "macd": return "point.3.connected.trianglepath.dotted"
        default: return "square.stack.3d.up.fill"
        }
    }
}

struct SignalBadge: View {
    let signal: String

    var body: some View {
        Text(signal.uppercased())
            .font(.caption.weight(.bold))
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .foregroundStyle(signalColor)
            .background(signalColor.opacity(0.12), in: Capsule())
    }

    private var signalColor: Color {
        switch signal.uppercased() {
        case "LONG": return .green
        case "SHORT": return .red
        default: return .secondary
        }
    }
}

struct EmptyState: View {
    let icon: String
    let title: String
    let message: String

    var body: some View {
        ContentUnavailableView(
            title,
            systemImage: icon,
            description: Text(message)
        )
    }
}
