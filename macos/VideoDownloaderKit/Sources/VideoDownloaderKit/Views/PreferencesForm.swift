import AppKit
import SwiftUI

/// The settings, in the Mac's own Settings window. Changes apply at once (see `Preferences`).
struct PreferencesForm: View {
    @Bindable var preferences: Preferences
    let shell: Shell
    /// A text field applies when Berk presses Return or leaves it.
    @FocusState private var field: String?

    var body: some View {
        Group {
            switch preferences.phase {
            case .loading:
                ProgressView(L("settings.loading")).frame(maxWidth: .infinity, maxHeight: .infinity)
            case .failed(let error):
                ErrorStateView(error: error) { Task { await preferences.load() } }
            case .ready:
                if preferences.draft != nil { form }
            }
        }
        .task { await preferences.load() }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("settings")
    }

    private var draft: Binding<AppSettings> {
        Binding(get: { preferences.draft! }, set: { preferences.draft = $0 })
    }

    /// A switch or a picker: saved the moment it changes.
    private func instant<T>(_ keyPath: WritableKeyPath<AppSettings, T>) -> Binding<T> {
        Binding(get: { preferences.draft![keyPath: keyPath] },
                set: { value in
                    // Refused: back to what is really in effect (text fields keep their edit).
                    preferences.apply({ $0[keyPath: keyPath] = value }, springBack: true)
                })
    }

    private var form: some View {
        Form {
            ShellSection(shell: shell)
            if let failure = preferences.failure {
                Section {
                    Label(ErrorCopy.title(failure.code), systemImage: "xmark.octagon.fill").foregroundStyle(.red)
                    Text(ErrorCopy.body(failure.code)).font(.callout).foregroundStyle(.secondary)
                    if preferences.dirty {
                        Text(L("settings.unsaved")).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("settings.failure")
            }
            Section {
                LabeledContent(L("settings.downloadDir")) {
                    HStack {
                        TextField(L("settings.downloadDir"), text: draft.downloadDir)
                            .labelsHidden()
                            .focused($field, equals: "downloadDir")
                            .font(.system(.body, design: .monospaced))
                            .onSubmit { preferences.commitText() }
                            .accessibilityIdentifier("settings.downloadDir")
                        Button(L("settings.chooseFolder")) { chooseFolder() }
                    }
                }
                Text(L("settings.downloadDirHelp")).font(.caption).foregroundStyle(.secondary)
                LabeledContent {
                    HStack {
                        TextField(L("settings.template"), text: draft.filenameTemplate)
                            .labelsHidden()
                            .focused($field, equals: "template")
                            .font(.system(.body, design: .monospaced))
                            .onSubmit { preferences.commitText() }
                            .accessibilityIdentifier("settings.template")
                        Button(L("settings.templateReset")) {
                            if let original = preferences.saved?.defaultFilenameTemplate {
                                preferences.apply({ $0.filenameTemplate = original }, springBack: false)
                            }
                        }
                        .disabled(preferences.saved?.defaultFilenameTemplate == nil)
                    }
                } label: {
                    Term(L("settings.template"), help: L("download.templateHelp"))
                }
                Group {
                    switch preferences.templatePreview {
                    case .success(let name)?:
                        Text("\(L("settings.templatePreview")): \(name)")
                    case .failure(let error)?:
                        Text(ErrorCopy.title(error.code)).foregroundStyle(.red)
                    case nil:
                        Text(" ")
                    }
                }
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("settings.templatePreview")
            }
            .task(id: preferences.draft?.filenameTemplate) {
                try? await Task.sleep(for: .milliseconds(150))
                guard !Task.isCancelled else { return }
                await preferences.previewTemplate()
            }

            Section {
                Stepper(value: instant(\.concurrency), in: 1...6) {
                    HStack {
                        Term(L("settings.concurrency"), help: L("settings.concurrencyHelp"))
                        Spacer()
                        Text("\(preferences.draft!.concurrency)").monospacedDigit()
                    }
                }
                Picker(L("settings.defaultMode"), selection: instant(\.defaultMode)) {
                    ForEach(Mode.allCases) { Text(L("mode.\($0.rawValue)")).tag($0.rawValue) }
                }
            }

            Section {
                toggle(L("settings.accelerate"), help: L("settings.accelerateHelp"), \.accelerate, id: "accelerate")
                Stepper(value: instant(\.connections), in: 2...16) {
                    HStack {
                        Term(L("settings.connections"), help: L("settings.connectionsHelp"))
                        Spacer()
                        Text("\(preferences.draft!.connections)").monospacedDigit()
                    }
                }
                .disabled(!preferences.draft!.accelerate)
                .accessibilityIdentifier("settings.connections")
                Picker(selection: instant(\.rateLimit)) {
                    Text(L("settings.rateLimit.none")).tag(0)
                    ForEach(Self.rateLimits, id: \.self) { bytes in
                        Text(L("settings.rateLimit.value", Format.bytes(Double(bytes)))).tag(bytes)
                    }
                    // A value set elsewhere (by hand in settings.json) stays selectable.
                    if let rate = preferences.draft?.rateLimit, rate > 0, !Self.rateLimits.contains(rate) {
                        Text(L("settings.rateLimit.value", Format.bytes(Double(rate)))).tag(rate)
                    }
                } label: {
                    Term(L("settings.rateLimit"), help: L("settings.rateLimitHelp"))
                }
                .accessibilityIdentifier("settings.rateLimit")
            }

            Section {
                toggle(L("settings.clipboard"), help: L("settings.clipboardHelp"), \.clipboardWatch, id: "clipboard")
                toggle(L("settings.notifications"), help: L("settings.notificationsHelp"), \.notifications, id: "notifications")
                toggle(L("settings.safariLogin"), help: L("settings.safariLoginHelp"), \.safariLogin, id: "safariLogin")
                toggle(L("settings.autoUpdate"), help: L("settings.autoUpdateHelp"), \.autoUpdateYtdlp, id: "autoUpdate")
            }

            Section {
                Picker(selection: instant(\.extensionOffer)) {
                    Text(L("settings.extensionOffer.page")).tag("page")
                    Text(L("settings.extensionOffer.icon")).tag("icon")
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(L("settings.extensionOffer"))
                        Text(L("settings.extensionOfferHelp")).font(.caption).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .accessibilityIdentifier("settings.extensionOffer")
            }

        }
        .formStyle(.grouped)
        .onChange(of: field) { old, _ in if old != nil { preferences.commitText() } }
    }

    /// Speed caps on offer, in bytes per second (0.5 to 50 MB/s).
    static let rateLimits = [512 << 10, 1 << 20, 2 << 20, 5 << 20, 10 << 20, 20 << 20, 50 << 20]

    private func toggle(_ title: String, help: String, _ keyPath: WritableKeyPath<AppSettings, Bool>, id: String) -> some View {
        Toggle(isOn: instant(keyPath)) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                Text(help).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityLabel(title)
        .accessibilityHint(help)
        .accessibilityIdentifier("settings.\(id)")
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.message = L("settings.choosePrompt")
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.directoryURL = URL(fileURLWithPath: preferences.draft?.downloadDir ?? NSHomeDirectory())
        if panel.runModal() == .OK, let url = panel.url {
            let folder = url.path
            preferences.apply({ $0.downloadDir = folder }, springBack: false)
        }
    }
}

/// Ayarlar' first box: how the app lives on this Mac (P4). Native only, so it works before the
/// backend answers too.
struct ShellSection: View {
    let shell: Shell

    var body: some View {
        Section(L("settings.section.app")) {
            row(L("settings.launchAtLogin"), L("settings.launchAtLoginHelp"), id: "launchAtLogin",
                Binding(get: { shell.launchAtLogin }, set: { shell.setLaunchAtLogin($0) }))
            if shell.loginStatus == .requiresApproval {
                HStack {
                    Text(L("settings.launchAtLoginApproval")).font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button(L("settings.openLoginItems")) { shell.openLoginItemsSettings() }
                }
            }
            if let error = shell.loginError {
                Text(error).font(.caption).foregroundStyle(.red)
            }
            row(L("settings.menuBarIcon"), L("settings.menuBarIconHelp"), id: "menuBarIcon",
                Binding(get: { shell.menuBarIcon }, set: { shell.setMenuBarIcon($0) }))
            row(L("settings.showInDock"), L("settings.showInDockHelp"), id: "showInDock",
                Binding(get: { shell.showInDock }, set: { shell.setShowInDock($0) }))
                .disabled(!shell.menuBarIcon)
        }
        // Approved or revoked in System Settings meanwhile.
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            shell.refreshLogin()
        }
    }

    private func row(_ title: String, _ help: String, id: String, _ isOn: Binding<Bool>) -> some View {
        Toggle(isOn: isOn) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                Text(help).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityLabel(title)
        .accessibilityHint(help)
        .accessibilityIdentifier("settings.\(id)")
    }
}
