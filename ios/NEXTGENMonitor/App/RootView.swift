import SwiftUI

struct RootView: View {
    @EnvironmentObject private var monitor: MonitorViewModel

    var body: some View {
        TabView {
            DashboardView()
                .tabItem {
                    Label("Overview", systemImage: "gauge.with.dots.needle.67percent")
                }

            SwitchHistoryView()
                .tabItem {
                    Label("Switches", systemImage: "arrow.triangle.2.circlepath")
                }

            DecisionJournalView()
                .tabItem {
                    Label("Decisions", systemImage: "list.bullet.rectangle.portrait")
                }

            ChartScreen()
                .tabItem {
                    Label("Chart", systemImage: "chart.xyaxis.line")
                }

            ActivityView()
                .tabItem {
                    Label("Activity", systemImage: "waveform.path")
                }
        }
        .task {
            await monitor.runPollingLoop()
        }
    }
}
