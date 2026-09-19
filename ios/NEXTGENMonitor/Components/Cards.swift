import SwiftUI

struct SurfaceCard<Content: View>: View {
    private let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
            .overlay {
                RoundedRectangle(cornerRadius: 18)
                    .strokeBorder(.quaternary, lineWidth: 1)
            }
    }
}

struct StatusPill: View {
    let title: String
    let active: Bool
    var warning = false

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(warning ? Color.orange : active ? Color.green : Color.red)
                .frame(width: 8, height: 8)
            Text(title.uppercased())
                .font(.caption2.weight(.bold))
                .tracking(0.6)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(.ultraThinMaterial, in: Capsule())
    }
}

struct MetricCard: View {
    let title: String
    let value: String
    var subtitle: String? = nil
    var emphasized = false

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title.uppercased())
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
                .tracking(0.6)
            Text(value)
                .font(
                    emphasized
                    ? .system(size: 28, weight: .bold, design: .rounded)
                    : .headline.monospacedDigit()
                )
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            if let subtitle {
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(14)
        .frame(
            maxWidth: .infinity,
            minHeight: emphasized ? 100 : 78,
            alignment: .leading
        )
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
    }
}
