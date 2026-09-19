import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var configuration: ConfigurationStore
    @EnvironmentObject private var monitor: MonitorViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var tokenVisible = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Connection") {
                    TextField(
                        "Base URL",
                        text: $configuration.baseURLString,
                        prompt: Text("http://100.107.22.92:4100")
                    )
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)

                    HStack {
                        Group {
                            if tokenVisible {
                                TextField("Bearer token", text: $configuration.token)
                            } else {
                                SecureField("Bearer token", text: $configuration.token)
                            }
                        }
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                        Button {
                            tokenVisible.toggle()
                        } label: {
                            Image(
                                systemName: tokenVisible
                                    ? "eye.slash.fill"
                                    : "eye.fill"
                            )
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(
                            tokenVisible ? "Hide token" : "Show token"
                        )
                    }

                    LabeledContent(
                        "Poll interval",
                        value: "\(Int(configuration.pollInterval)) seconds"
                    )
                    Slider(
                        value: $configuration.pollInterval,
                        in: 1...5,
                        step: 1
                    )

                    Button("Test connection") {
                        monitor.saveSettings()
                        Task {
                            await monitor.refresh(includeHistory: false)
                        }
                    }

                    HStack {
                        Text("API")
                        Spacer()
                        StatusPill(
                            title: monitor.apiOnline ? "ONLINE" : "OFFLINE",
                            active: monitor.apiOnline
                        )
                    }
                }

                Section("Security") {
                    Label(
                        "The API token is stored in iOS Keychain.",
                        systemImage: "key.fill"
                    )
                    Text(
                        "Secrets are never embedded in the app source and are not written to the monitor cache."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }

                Section("Appearance") {
                    Picker("Theme", selection: $configuration.theme) {
                        ForEach(ThemePreference.allCases) { theme in
                            Text(theme.rawValue).tag(theme)
                        }
                    }
                }

                Section("Notifications") {
                    Toggle(
                        "Important local alerts",
                        isOn: $configuration.notificationsEnabled
                    )
                    Text(
                        "Local alerts cover events observed while the app is active. The project includes a clean remote-push abstraction for future APNs infrastructure."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }

                Section("Safety") {
                    LabeledContent("Mode", value: "PAPER ONLY")
                    LabeledContent("Manual BUY/SELL", value: "NOT AVAILABLE")
                    LabeledContent("Live trading", value: "NOT AVAILABLE")
                    Text(
                        "Controls are limited to STATUS, PAUSE and RESUME through the existing NEXTGEN command queue."
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") {
                        monitor.saveSettings()
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        monitor.saveSettings()
                        Task {
                            await monitor.refresh(includeHistory: true)
                        }
                        dismiss()
                    }
                }
            }
        }
    }
}
