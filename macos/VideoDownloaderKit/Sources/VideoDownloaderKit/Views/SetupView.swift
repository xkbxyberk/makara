import AppKit
import SwiftUI

/// The first start of a release (PLAN P8): what Makara needs, why, and one button. Nothing is
/// downloaded before it is pressed.
struct SetupView: View {
    let model: AppModel

    private var setup: RuntimeSetup { model.setup }
    private var release: BackendConfig.Release? { model.backend.config.release }

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                Image(nsImage: NSApp.applicationIconImage)
                    .resizable()
                    .frame(width: 84, height: 84)
                    .accessibilityHidden(true)
                VStack(spacing: 6) {
                    Text(L("setup.title")).font(.title.weight(.semibold))
                    Text(L("setup.body"))
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
                VStack(alignment: .leading, spacing: 0) {
                    VStack(alignment: .leading, spacing: 10) {
                        component("film", L("setup.ffmpeg"), L("setup.ffmpeg.help"))
                        component("checkmark.shield", L("setup.deno"), L("setup.deno.help"))
                        component("bolt.horizontal", L("setup.aria2"), L("setup.aria2.help"))
                        toolsStatus
                    }
                    .padding(14)
                    Divider()
                    HStack(alignment: .top) {
                        component("shippingbox", L("setup.python"), L("setup.python.help"))
                        Spacer(minLength: 12)
                        pythonStatus
                    }
                    .padding(14)
                }
                .background(.background.secondary, in: .rect(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(.separator))
                footer
            }
            .frame(maxWidth: 520)
            .padding(32)
            .frame(maxWidth: .infinity)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("setup")
    }

    private func component(_ symbol: String, _ name: String, _ help: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: symbol)
                .frame(width: 22)
                .foregroundStyle(.tint)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(.headline)
                Text(help).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private var toolsStatus: some View {
        switch setup.tools {
        case .waiting:
            EmptyView()
        case .downloading(let fraction):
            VStack(alignment: .leading, spacing: 4) {
                ProgressView(value: fraction)
                Text(L("setup.downloading", Int((fraction * 100).rounded()))).font(.caption).foregroundStyle(.secondary)
                    .monospacedDigit()
            }
        case .verifying:
            VStack(alignment: .leading, spacing: 4) {
                ProgressView().progressViewStyle(.linear)
                Text(L("setup.verifying")).font(.caption).foregroundStyle(.secondary)
            }
        case .done:
            Label(L("setup.ready"), systemImage: "checkmark.circle.fill").font(.callout).foregroundStyle(.green)
        case .failed(let failure):
            Label(Self.reason(failure), systemImage: "exclamationmark.triangle.fill")
                .font(.callout)
                .foregroundStyle(.red)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private var pythonStatus: some View {
        switch model.backend.state {
        case .syncing:
            HStack(spacing: 6) {
                ProgressView().controlSize(.small)
                Text(L("setup.installing")).font(.caption).foregroundStyle(.secondary)
            }
        case .starting, .ready:
            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                .accessibilityLabel(L("setup.ready"))
        default:
            EmptyView()
        }
    }

    @ViewBuilder private var footer: some View {
        VStack(spacing: 10) {
            if let release, let size = RuntimeSetup.downloadSize(release) {
                Text(L("setup.size", Format.bytes(Double(size))))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            if case .failed = setup.tools {
                Button(L("setup.retry")) { install() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
            } else {
                Button(L("setup.install")) { install() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .keyboardShortcut(.defaultAction)
                    .disabled(setup.running || model.backend.state != .needsSetup)
            }
        }
    }

    private func install() {
        Task { await model.installRuntime() }
    }

    static func reason(_ failure: RuntimeTools.Failure) -> String {
        switch failure {
        case .network(let detail): L("setup.error.network", detail)
        case .checksum: L("setup.error.checksum")
        case .space(let needed): L("setup.error.space", Format.bytes(Double(needed)))
        case .broken(let detail): L("setup.error.broken", detail)
        }
    }
}
