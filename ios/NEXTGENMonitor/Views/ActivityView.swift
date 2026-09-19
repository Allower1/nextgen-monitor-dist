import SwiftUI

struct ActivityView: View {
    @EnvironmentObject private var monitor: MonitorViewModel
    @State private var typeFilter = "ALL"

    private var filtered: [ActivityEvent] {
        guard typeFilter != "ALL" else { return monitor.activity }
        return monitor.activity.filter { $0.type == typeFilter }
    }

    private let quickTypes = [
        "ALL", "STRATEGY_SWITCH", "FILL", "ERROR", "GAP_DETECTED"
    ]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(quickTypes, id: \.self) { type in
                            Button {
                                typeFilter = type
                            } label: {
                                Text(label(for: type))
                                    .font(.caption.weight(.semibold))
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background(
                                        typeFilter == type
                                            ? Color.accentColor.opacity(0.18)
                                            : Color.secondary.opacity(0.08),
                                        in: Capsule()
                                    )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 10)
                }

                if filtered.isEmpty {
                    EmptyState(
                        icon: "waveform.path",
                        title: "No activity",
                        message: "The chronological life of the adaptive agent will appear here."
                    )
                } else {
                    List(filtered) { event in
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: icon(for: event.type))
                                .foregroundStyle(color(for: event.type))
                                .frame(width: 28)
                                .padding(.top, 2)
                            VStack(alignment: .leading, spacing: 5) {
                                HStack {
                                    Text(event.title)
                                        .font(.subheadline.weight(.semibold))
                                    Spacer()
                                    Text(Formatters.shortTime(event.timestamp))
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                Text(event.type.replacingOccurrences(of: "_", with: " "))
                                    .font(.caption2.weight(.bold))
                                    .foregroundStyle(color(for: event.type))
                                if !event.detail.isEmpty {
                                    Text(event.detail)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(4)
                                }
                            }
                        }
                        .padding(.vertical, 5)
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Activity")
            .refreshable {
                await monitor.refresh(includeHistory: false)
            }
        }
    }

    private func label(for type: String) -> String {
        type == "ALL"
            ? "All"
            : type.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private func icon(for type: String) -> String {
        switch type {
        case "BAR_CLOSED": return "clock.badge.checkmark"
        case "SIGNAL_GENERATED": return "bolt.fill"
        case "PENDING": return "hourglass"
        case "FILL": return "checkmark.seal.fill"
        case "POSITION_OPENED": return "arrow.up.forward.circle.fill"
        case "POSITION_CLOSED": return "arrow.down.backward.circle.fill"
        case "STRATEGY_SWITCH": return "arrow.triangle.2.circlepath"
        case "PAUSE": return "pause.circle.fill"
        case "RESUME": return "play.circle.fill"
        case "GAP_DETECTED": return "exclamationmark.triangle.fill"
        case "DUPLICATE_BAR": return "doc.on.doc.fill"
        case "ERROR": return "xmark.octagon.fill"
        default: return "circle.fill"
        }
    }

    private func color(for type: String) -> Color {
        switch type {
        case "ERROR", "GAP_DETECTED": return .red
        case "STRATEGY_SWITCH": return .orange
        case "FILL", "POSITION_OPENED", "POSITION_CLOSED": return .blue
        case "RESUME": return .green
        case "PAUSE", "PENDING": return .yellow
        default: return .secondary
        }
    }
}
