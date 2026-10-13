import AppKit
import SwiftUI

/// The inspector of Stüdyo: the operation, its settings, the output, the exact plan and "Çalıştır".
struct StudioPanel: View {
    @Bindable var studio: Studio
    let openQueue: () -> Void

    var body: some View {
        Form {
            Section {
                Picker(L("studio.operation"), selection: $studio.operation) {
                    ForEach(Studio.Operation.allCases) { op in
                        Label(L("studio.tabs.\(op.rawValue)"), systemImage: op.symbol)
                            .tag(op)
                            .disabled(!studio.allowed(op))
                    }
                }
                .accessibilityIdentifier("studio.operation")
            }
            switch studio.operation {
            case .trim: trimSettings
            case .audio: audioSettings
            case .remux: remuxSettings
            case .subtitle: subtitleSettings
            }
            Section(L("studio.output")) {
                TextField(L("studio.output"), text: $studio.outputName)
                    .labelsHidden()
                    .accessibilityIdentifier("studio.outputName")
                if let outputs = studio.plan?.outputs, studio.planIsCurrent {
                    ForEach(outputs, id: \.self) { output in
                        Text(output).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityIdentifier("studio.outputs")
                }
            }
            planSection
        }
        .formStyle(.grouped)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("studio.panel")
    }

    // ---- per operation --------------------------------------------------------------------

    @ViewBuilder private var trimSettings: some View {
        Section {
            Picker(L("studio.trim.mode"), selection: $studio.trimMode) {
                Text(L("studio.trim.accurate")).tag(Studio.TrimMode.accurate)
                Text(L("studio.trim.lossless")).tag(Studio.TrimMode.lossless)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .accessibilityIdentifier("studio.trimMode")
            Text(studio.trimMode == .accurate ? L("studio.terms.accurate.body") : L("studio.terms.lossless.body"))
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if studio.trimMode == .lossless {
                Term(L("studio.terms.keyframe.label"), help: L("studio.terms.keyframe.body")).font(.caption)
            }
        } header: {
            Text(L("studio.trim.mode"))
        }
    }

    @ViewBuilder private var audioSettings: some View {
        Section {
            if let source = studio.source, source.audioStreams.count > 1 {
                Picker(L("studio.audio.track"), selection: $studio.audioIndex) {
                    ForEach(Array(source.audioStreams.enumerated()), id: \.offset) { index, stream in
                        Text("\(index + 1). \(Format.language(stream.language)) · \(stream.codec ?? "?")").tag(index)
                    }
                }
            }
            Picker(L("studio.audio.codec"), selection: $studio.audioCodec) {
                ForEach(Studio.codecs, id: \.self) { Text(L("download.audioCodec.\($0)")).tag($0) }
            }
            if Studio.lossy.contains(studio.audioCodec) {
                Picker(selection: $studio.bitrate) {
                    ForEach(Studio.bitrates, id: \.self) { Text("\($0) \(L("unit.kbps"))").tag($0) }
                } label: { Term(term: "bitrate") }
            }
            Picker(selection: $studio.sampleRate) {
                Text(L("studio.audio.auto")).tag("")
                if studio.audioCodec != "opus" { Text("44,1 \(L("unit.khz"))").tag("44100") }
                Text("48 \(L("unit.khz"))").tag("48000")
            } label: { Term(term: "sampleRate") }
            Picker(selection: $studio.channels) {
                Text(L("studio.audio.auto")).tag("")
                Text(L("studio.audio.mono")).tag("1")
                Text(L("studio.audio.stereo")).tag("2")
            } label: { Term(term: "channels") }
            Toggle(isOn: $studio.loudnorm) {
                HStack(spacing: 4) {
                    Text(L("studio.audio.loudnorm"))
                    Term(L("studio.terms.loudnorm.label"), help: L("studio.terms.loudnorm.body")).foregroundStyle(.secondary)
                }
            }
        }
    }

    @ViewBuilder private var remuxSettings: some View {
        Section {
            Picker(selection: $studio.container) {
                ForEach(["mkv", "mp4", "mov"], id: \.self) { Text($0.uppercased()).tag($0) }
            } label: {
                Term(L("studio.terms.container.label"), help: L("studio.terms.container.body"))
            }
            .pickerStyle(.segmented)
            Text(L("studio.terms.remux.body")).font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        Section(L("studioNative.tracks")) {
            ForEach(Array(studio.tracks.enumerated()), id: \.element.id) { index, track in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Toggle(isOn: $studio.tracks[index].keep) {
                            Text("\(localizedIfPresent("studio.streamKinds.\(track.stream.type ?? "")") ?? (track.stream.type ?? "")) · \(track.stream.codec ?? "?")")
                                .font(.callout.weight(.medium))
                        }
                        .toggleStyle(.checkbox)
                        .accessibilityLabel("\(L("studio.remux.keep")) \(index + 1)")
                        Spacer()
                        Button { studio.moveTrack(index, by: -1) } label: { Image(systemName: "chevron.up") }
                            .buttonStyle(.borderless).help(L("studio.remux.moveUp")).accessibilityLabel(L("studio.remux.moveUp"))
                        Button { studio.moveTrack(index, by: 1) } label: { Image(systemName: "chevron.down") }
                            .buttonStyle(.borderless).help(L("studio.remux.moveDown")).accessibilityLabel(L("studio.remux.moveDown"))
                    }
                    if track.input > 0 {
                        Text(L("studio.remux.fromExtra", track.from)).font(.caption).foregroundStyle(.secondary)
                    }
                    HStack {
                        TextField(L("studio.remux.language"), text: $studio.tracks[index].language,
                                  prompt: Text(L("studio.remux.languagePlaceholder")))
                            .frame(width: 80)
                        TextField(L("studio.remux.title"), text: $studio.tracks[index].title, prompt: Text(L("studio.remux.title")))
                        Toggle(L("studio.remux.isDefault"), isOn: $studio.tracks[index].isDefault).toggleStyle(.checkbox)
                    }
                    .labelsHidden()
                    .disabled(!track.keep)
                }
                .opacity(track.keep ? 1 : 0.5)
            }
            Button(L("studio.remux.addFile"), systemImage: "plus") {
                let panel = NSOpenPanel()
                panel.canChooseDirectories = false
                if panel.runModal() == .OK, let url = panel.url { Task { await studio.addExtra(path: url.path) } }
            }
        }
    }

    @ViewBuilder private var subtitleSettings: some View {
        Section {
            if studio.source?.youtubeAutoCaptions == true {
                Label(L("studio.subtitle.looksAuto"), systemImage: "info.circle").foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Picker(L("studio.subtitle.action"), selection: $studio.subtitleAction) {
                ForEach(["convert", "shift", "clean"], id: \.self) { Text(L("studio.subtitle.actions.\($0)")).tag($0) }
            }
            Picker(L("studio.subtitle.target"), selection: $studio.subtitleTarget) {
                ForEach(["srt", "vtt", "ass"], id: \.self) { Text($0.uppercased()).tag($0) }
            }
            if studio.subtitleAction == "shift" {
                TextField(L("studio.subtitle.offset"), text: $studio.offset)
                if studio.offsetSeconds == nil {
                    Text(L("studio.subtitle.offsetInvalid")).foregroundStyle(.red).font(.caption)
                }
            }
        }
    }

    // ---- the plan ---------------------------------------------------------------------------

    @ViewBuilder private var planSection: some View {
        Section {
            if !studio.planIsCurrent {
                Text(L("studio.planning")).foregroundStyle(.tertiary)
            }
            if let plan = studio.plan, studio.planIsCurrent {
                ForEach(Array(plan.notices.enumerated()), id: \.offset) { _, notice in
                    NoticeRow(text: studioNoticeText(notice), level: notice.level)
                }
                DisclosureGroup(L("studio.commands")) {
                    ForEach(Array(plan.steps.enumerated()), id: \.offset) { _, step in
                        if step.kind == "ffmpeg" {
                            CommandText(command: step.command)
                        } else {
                            Text(localizedIfPresent("studio.steps.\(step.action)") ?? step.action)
                                .font(.callout).foregroundStyle(.secondary)
                        }
                    }
                }
                .accessibilityIdentifier("studio.commands")
            }
            if let failure = studio.failure {
                NoticeRow(text: ErrorCopy.title(failure.code) + " " + ErrorCopy.body(failure.code), level: "error")
            }
            if studio.queued {
                HStack {
                    Label(L("studio.queued"), systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                    Spacer()
                    Button(L("studio.openQueue"), action: openQueue)
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("studio.queued")
            }
            Button {
                Task { await studio.run() }
            } label: {
                Label(L("studio.run"), systemImage: "play.fill").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .keyboardShortcut(.return, modifiers: .command)
            .disabled(!studio.canRun)
            .accessibilityIdentifier("studio.run")
        }
    }
}

/// A Stüdyo plan notice in words (templates as in the download panel's).
func studioNoticeText(_ notice: Plan.Notice) -> String {
    localizedIfPresent("studio.notice.\(notice.code)").map { Format.notice($0, notice.params) } ?? notice.code
}
