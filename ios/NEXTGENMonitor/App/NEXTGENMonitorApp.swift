import SwiftUI

@main
@MainActor
struct NEXTGENMonitorApp: App {
    @StateObject private var configuration: ConfigurationStore
    @StateObject private var monitor: MonitorViewModel

    init() {
        let configuration = ConfigurationStore.shared
        _configuration = StateObject(wrappedValue: configuration)
        _monitor = StateObject(
            wrappedValue: MonitorViewModel(configuration: configuration)
        )
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(configuration)
                .environmentObject(monitor)
                .preferredColorScheme(configuration.theme.colorScheme)
        }
    }
}
