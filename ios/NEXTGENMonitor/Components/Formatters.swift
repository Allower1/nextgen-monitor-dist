import Foundation

enum Formatters {
    static func money(_ value: Double) -> String {
        value.formatted(
            .currency(code: "USD")
                .precision(.fractionLength(2))
        )
    }

    static func number(_ value: Double, digits: Int = 2) -> String {
        value.formatted(
            .number.precision(.fractionLength(0...digits))
        )
    }

    static func percent(_ fraction: Double) -> String {
        (fraction * 100).formatted(
            .number.precision(.fractionLength(2))
        ) + "%"
    }

    static func pnlPercent(_ percent: Double) -> String {
        percent.formatted(
            .number
                .sign(strategy: .always())
                .precision(.fractionLength(2))
        ) + "%"
    }

    static func dateTime(_ date: Date?) -> String {
        guard let date else { return "—" }
        return date.formatted(
            date: .abbreviated,
            time: .standard
        )
    }

    static func shortTime(_ date: Date) -> String {
        date.formatted(
            date: .omitted,
            time: .shortened
        )
    }

    static func strategy(_ raw: String) -> String {
        switch raw {
        case "rsi": return "RSI"
        case "moving_average": return "Moving Average"
        case "macd": return "MACD"
        case "combo": return "Combo"
        default:
            return raw
                .replacingOccurrences(of: "_", with: " ")
                .capitalized
        }
    }
}
