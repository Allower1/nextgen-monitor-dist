import Foundation
import UserNotifications

protocol RemotePushProviding {
    func registerIfAvailable() async
}

struct NoopRemotePushProvider: RemotePushProviding {
    func registerIfAvailable() async {}
}

@MainActor
final class NotificationService {
    static let shared = NotificationService()

    private let center: UNUserNotificationCenter
    private let remotePush: RemotePushProviding
    private var emitted = Set<String>()

    init(
        center: UNUserNotificationCenter = .current(),
        remotePush: RemotePushProviding = NoopRemotePushProvider()
    ) {
        self.center = center
        self.remotePush = remotePush
    }

    func requestAuthorizationIfNeeded(enabled: Bool) async {
        guard enabled else { return }
        _ = try? await center.requestAuthorization(
            options: [.alert, .sound, .badge]
        )
        await remotePush.registerIfAvailable()
    }

    func process(
        previous: MonitorStatus?,
        current: MonitorStatus,
        previousSwitchID: String?,
        switches: [StrategySwitch],
        activity: [ActivityEvent],
        enabled: Bool
    ) {
        guard enabled else { return }

        if current.stale && previous?.stale != true {
            schedule(
                key: "heartbeat-stale-\(current.heartbeatAt?.timeIntervalSince1970 ?? 0)",
                title: "NEXTGEN heartbeat missing",
                body: "The latest agent heartbeat is stale."
            )
        }
        if current.isAgentOffline && previous?.isAgentOffline != true {
            schedule(
                key: "agent-offline-\(current.updatedAt.timeIntervalSince1970)",
                title: "NEXTGEN agent offline",
                body: "The monitor API is reachable, but the paper agent is not active."
            )
        }
        if current.paused && previous?.paused != true {
            schedule(
                key: "paused-\(current.updatedAt.timeIntervalSince1970)",
                title: "NEXTGEN paused",
                body: "The adaptive paper agent is paused."
            )
        }
        if !current.paused && previous?.paused == true {
            schedule(
                key: "resumed-\(current.updatedAt.timeIntervalSince1970)",
                title: "NEXTGEN resumed",
                body: "The adaptive paper agent resumed."
            )
        }
        if current.drawdown >= 0.05 && (previous?.drawdown ?? 0) < 0.05 {
            schedule(
                key: "drawdown-\(current.lastProcessedBar?.timeIntervalSince1970 ?? 0)",
                title: "Large NEXTGEN drawdown",
                body: String(
                    format: "Current drawdown is %.2f%%.",
                    current.drawdown * 100
                )
            )
        }

        if let newest = switches.first,
           newest.id != previousSwitchID {
            schedule(
                key: "switch-\(newest.id)",
                title: "Strategy switched",
                body: "\(newest.fromStrategy) → \(newest.toStrategy) · \(newest.marketRegime)"
            )
        }

        for event in activity.prefix(20) {
            switch event.type {
            case "GAP_DETECTED":
                schedule(
                    key: "activity-\(event.id)",
                    title: "Market data gap detected",
                    body: event.detail
                )
            case "ERROR":
                schedule(
                    key: "activity-\(event.id)",
                    title: "NEXTGEN runtime error",
                    body: event.detail
                )
            default:
                break
            }
        }
    }

    func apiUnavailable(enabled: Bool) {
        guard enabled else { return }
        schedule(
            key: "api-offline",
            title: "NEXTGEN monitor offline",
            body: "The iPhone app cannot reach the monitoring API."
        )
    }

    private func schedule(key: String, title: String, body: String) {
        guard !emitted.contains(key) else { return }
        emitted.insert(key)
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(
            identifier: key,
            content: content,
            trigger: nil
        )
        center.add(request, withCompletionHandler: nil)
    }
}
