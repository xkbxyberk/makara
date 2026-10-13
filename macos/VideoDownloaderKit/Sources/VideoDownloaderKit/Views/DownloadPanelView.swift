import SwiftUI

/// "İndir": the output, the video's own quick choices, a summary, the plan (size, file name,
/// warnings) and the button; the full track picker one click away.
struct DownloadPanelView: View {
    @Bindable var planner: DownloadPlanner
    let client: APIClient
    let rules: QuickRules
    let openQueue: () -> Void
    let reinspect: () -> Void

    var body: some View {
        Panel(title: L("download.title")) {
            if planner.failure?.code == "INSPECT_EXPIRED" {
                // The server forgot this inspect (it restarted, or a long while passed).
                VStack(spacing: 10) {
                    ErrorStateView(error: planner.failure!)
                    Button(L("download.reinspect"), action: reinspect).buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity)
            } else {
                panel
            }
        }
        .task {
            if let settings = try? await client.settings() { planner.apply(settings: settings) }
        }
        // A moment after each change, the plan for exactly this selection (a newer change
        // cancels the older request).
        .task(id: planner.selection) {
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled else { return }
            await planner.refreshPlan(client: client)
        }
        // A container: without .contain its identifier would replace every child's.
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("download")
    }

    @ViewBuilder private var panel: some View {
        Picker(L("download.title"), selection: Binding(get: { planner.mode }, set: { planner.choose($0) })) {
            ForEach(Mode.allCases) { mode in
                Text(L("mode.\(mode.rawValue)")).tag(mode).help(L("download.modeHelp.\(mode.rawValue)"))
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .fixedSize()
        .accessibilityIdentifier("download.mode")
        Text(L("download.modeHelp.\(planner.mode.rawValue)"))
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)

        if !planner.quickRows.isEmpty { QuickChoices(planner: planner) }

        Summary(planner: planner)
        facts

        if let plan = planner.plan {
            // By position: one code can come once per track (AUDIO_REENCODE for each language).
            let notices = plan.notices.filter { $0.code != "UNKNOWN_SELECTION" || plan.blocking }
            ForEach(Array(notices.enumerated()), id: \.offset) { _, notice in
                NoticeRow(text: noticeText(notice), level: notice.level)
            }
        }
        if let failure = planner.failure {
            NoticeRow(text: ErrorCopy.title(failure.code) + " " + ErrorCopy.body(failure.code), level: "error")
        }
        if planner.queued {
            HStack {
                Label(L("download.queued"), systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                Spacer()
                Button(L("download.openQueue"), action: openQueue)
            }
            .padding(10)
            .background(.green.opacity(0.08), in: .rect(cornerRadius: 8))
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("download.queued")
        }

        HStack {
            Button {
                withAnimation(.snappy) { planner.pickerOpen.toggle() }
            } label: {
                Label(planner.pickerOpen ? L("download.hidePicker") : L("download.showPicker"), systemImage: "slider.horizontal.3")
            }
            .buttonStyle(.borderless)
            .accessibilityIdentifier("download.picker")
            Spacer()
            Button {
                Task { await planner.submit(client: client, rules: rules) }
            } label: {
                if planner.submitting {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text(L("download.submitting"))
                    }
                } else {
                    Label(L("download.submit"), systemImage: "arrow.down.circle")
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .keyboardShortcut(.return, modifiers: .command)
            .disabled(!planner.canSubmit)
            .accessibilityIdentifier("download.submit")
        }

        if planner.pickerOpen { TrackPicker(planner: planner) }
    }

    private var facts: some View {
        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
            GridRow {
                Text(L("download.estimatedSize")).foregroundStyle(.secondary)
                Group {
                    if let plan = planner.plan, plan.size.bytes != nil {
                        SizeText(bytes: plan.size.bytes, kind: plan.size.kind, unreliable: plan.size.unreliable)
                    } else {
                        Text(planner.plan == nil ? L("download.planning") : L("download.unknownSize")).foregroundStyle(.tertiary)
                    }
                }
                .accessibilityIdentifier("download.size")
            }
            GridRow {
                Text(L("download.willSaveTo")).foregroundStyle(.secondary)
                Group {
                    if let plan = planner.plan, let filename = plan.filename {
                        Text("\(Text(plan.downloadDir + "/").foregroundStyle(.tertiary))\(filename)")
                            .font(.system(.callout, design: .monospaced))
                            .textSelection(.enabled)
                    } else if let error = planner.plan?.filenameError {
                        Text(localizedIfPresent("error.\(error).title") ?? error).foregroundStyle(.red)
                    } else {
                        Text(L("download.planning")).foregroundStyle(.tertiary)
                    }
                }
                .accessibilityIdentifier("download.filename")
            }
        }
    }
}

struct NoticeRow: View {
    let text: String
    let level: String

    var body: some View {
        Label(text, systemImage: level == "error" ? "xmark.octagon.fill" : level == "warn" ? "exclamationmark.triangle.fill" : "info.circle")
            .foregroundStyle(level == "error" ? AnyShapeStyle(.red) : level == "warn" ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("notice.\(level)")
    }
}

/// What will be downloaded, in a line of chips.
struct Summary: View {
    let planner: DownloadPlanner

    var body: some View {
        let current = planner.current
        let audioOnly = planner.mode == .audio
        let video = planner.videos.first { $0.formatId == current.videoFormatId }
        // In the order chosen: the first one becomes the file's default track.
        let languages = current.audioFormatIds.compactMap { id in
            planner.model.audioLanguages.first { $0.tracks.contains { $0.formatId == id } }.map { group in
                "\(Format.language(group.language)) (\(localizedIfPresent("role.\(group.role)") ?? group.role))"
            }
        }
        let muxedSource = audioOnly ? planner.videos.first { current.audioFormatIds.contains($0.formatId) } : nil
        HStack(spacing: 6) {
            if !audioOnly { chip(videoLabel(video)) }
            if !languages.isEmpty {
                ForEach(languages, id: \.self) { chip($0) }
            } else if let muxedSource {
                chip(videoLabel(muxedSource))
            } else if audioOnly || video?.hasAudio != true {
                chip(L("download.noAudio"))
            }
            if !audioOnly {
                chip(current.subtitleKeys.isEmpty ? L("download.noSubtitles")
                     : L("download.subtitlesSummary", current.subtitleKeys.map(Format.language).joined(separator: ", ")))
            }
            if audioOnly { chip(planner.audioCodec.uppercased()) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("download.summary")
    }

    private func chip(_ text: String) -> some View {
        Text(text)
            .font(.callout)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(.quaternary.opacity(0.6), in: .capsule)
    }
}

func videoLabel(_ format: VideoFormat?) -> String {
    guard let format else { return L("download.noVideo") }
    let height = format.height.map { "\($0)p" } ?? format.resolution ?? format.formatId
    return [height, format.vcodecLabel].compactMap { $0 }.joined(separator: " · ")
}

// ---- quick choices -------------------------------------------------------------------------

/// One click per quality the video really has; the full picker stays below for everything else.
struct QuickChoices: View {
    let planner: DownloadPlanner

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline) {
                Text(L("download.quick.title")).font(.subheadline.weight(.semibold))
                Text(planner.mode == .audio ? L("download.quick.audioHelp") : L("download.quick.videoHelp"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding(.bottom, 4)
            ForEach(planner.quickRows) { row in
                QuickRowView(row: row, mode: planner.mode, checked: row.id == planner.activeRow?.id,
                             remembered: row.id == planner.rememberedId) { planner.apply(row) }
            }
        }
        .padding(10)
        .background(.quaternary.opacity(0.3), in: .rect(cornerRadius: 8))
        // A container: without .contain its identifier would replace every child's.
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("quick")
    }
}

struct QuickRowView: View {
    let row: DownloadPlanner.QuickRow
    let mode: Mode
    let checked: Bool
    let remembered: Bool
    let choose: () -> Void

    var body: some View {
        Button(action: choose) {
            HStack(spacing: 10) {
                Image(systemName: checked ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(checked ? Color.accentColor : .secondary)
                Text(label).font(.body.weight(.medium)).frame(minWidth: 90, alignment: .leading)
                Text(detail).foregroundStyle(.secondary)
                badges
                if remembered { Text(L("download.quick.remembered")).font(.caption).foregroundStyle(.secondary) }
                Spacer()
                size.monospacedDigit()
            }
            .padding(.vertical, 4)
            .padding(.horizontal, 6)
            .contentShape(.rect)
            .background(checked ? Color.accentColor.opacity(0.1) : .clear, in: .rect(cornerRadius: 6))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityValue(checked ? "1" : "0")
        .accessibilityAddTraits(checked ? .isSelected : [])
        .accessibilityIdentifier("quick.\(row.id)")
    }

    private var label: String {
        switch row {
        case .video(let offer): offer.height.map { "\($0)p" } ?? L("download.quick.unknownHeight")
        case .audio(let offer): localizedIfPresent("download.quick.format.\(offer.format)") ?? offer.format
        }
    }

    private var detail: String {
        switch row {
        case .video(let offer):
            [offer.output(for: mode).vcodecLabel, offer.fps.map { L("download.quick.fps", Format.plain($0)) }]
                .compactMap { $0 }.joined(separator: " · ")
        case .audio(let offer):
            [offer.sourceCodecLabel, offer.abr.map(Format.bitrate)].compactMap { $0 }.joined(separator: " · ")
        }
    }

    private var step: String {
        switch row {
        case .video(let offer): offer.output(for: mode).step
        case .audio(let offer): offer.step
        }
    }

    @ViewBuilder private var badges: some View {
        switch row {
        case .video(let offer):
            if let range = offer.dynamicRange, range != "SDR" { Badge(text: range, tone: .accent) }
            if offer.aiUpscaled { Badge(text: L("term.aiUpscaled.label"), tone: .warn) }
            if step != "copy" { StepBadge(step: step) }
        case .audio:
            StepBadge(step: step)
        }
    }

    /// Same honesty as the panel's own size; "known once converted" only for a conversion.
    @ViewBuilder private var size: some View {
        let size: OfferSize = switch row {
        case .video(let offer): offer.output(for: mode).size
        case .audio(let offer): offer.size
        }
        if size.bytes == nil {
            Text(step == "transcode" ? L("download.quick.sizeLater") : L("download.unknownSize")).foregroundStyle(.tertiary)
        } else {
            SizeText(bytes: size.bytes, kind: size.kind, unreliable: size.unreliable)
        }
    }
}

struct StepBadge: View {
    let step: String

    var body: some View {
        switch step {
        case "copy": Badge(text: L("download.quick.copy"), tone: .ok)
        case "probe": Badge(text: L("download.quick.probe"))
        default: Badge(text: L("download.quick.transcode"), tone: .warn)
        }
    }
}

// ---- the track picker ----------------------------------------------------------------------

struct TrackPicker: View {
    @Bindable var planner: DownloadPlanner
    @State private var showTranslated = false
    @State private var filter = ""

    var body: some View {
        let audioOnly = planner.mode == .audio
        let current = planner.current
        VStack(alignment: .leading, spacing: 14) {
            if !audioOnly {
                PickSection(L("download.section.video")) {
                    ForEach(planner.videos) { format in
                        Toggle(isOn: Binding(get: { current.videoFormatId == format.formatId },
                                             set: { if $0 { planner.update { $0.videoFormatId = format.formatId } } })) {
                            HStack(spacing: 6) {
                                Text(videoLabel(format)).font(.body.weight(.medium))
                                if let fps = format.fps { Text("\(Int(fps.rounded())) \(L("unit.fps"))").foregroundStyle(.secondary) }
                                if let range = format.dynamicRange, range != "SDR" {
                                    Badge(text: range, tone: .accent).help(L("term.hdr.body"))
                                }
                                FormatBadges(drm: "none", aiUpscaled: format.aiUpscaled, drc: false, muxed: format.hasAudio == true)
                                Spacer()
                                Text(format.formatId).font(.system(.callout, design: .monospaced)).foregroundStyle(.tertiary)
                                Text(format.filesize == nil ? "–" : Format.size(format.filesize, format.filesizeKind))
                                    .monospacedDigit().frame(minWidth: 70, alignment: .trailing)
                            }
                        }
                        .toggleStyle(RadioToggleStyle())
                        .accessibilityIdentifier("pick.video.\(format.formatId)")
                    }
                }
            }

            PickSection(L("download.section.audio")) {
                ForEach(planner.model.audioLanguages) { group in
                    let chosen = planner.chosen(in: group)
                    HStack {
                        Toggle(isOn: Binding(get: { chosen != nil },
                                             set: { planner.setGroup(group, to: $0 ? group.tracks.first?.formatId : nil) })) {
                            HStack(spacing: 6) {
                                Text(Format.language(group.language)).font(.body.weight(.medium))
                                RoleBadge(role: group.role)
                            }
                        }
                        .toggleStyle(audioOnly ? AnyToggleStyle(RadioToggleStyle()) : AnyToggleStyle(.checkbox))
                        .accessibilityIdentifier("pick.audio.\(group.id)")
                        Spacer()
                        Picker(L("download.variant"), selection: Binding(
                            get: { chosen?.formatId ?? group.tracks.first?.formatId ?? "" },
                            set: { planner.setGroup(group, to: $0) })) {
                            ForEach(group.tracks) { track in Text(trackLabel(track)).tag(track.formatId) }
                        }
                        .labelsHidden()
                        .fixedSize()
                        .accessibilityLabel("\(Format.language(group.language)) \(L("download.variant"))")
                    }
                }
                if audioOnly, planner.model.audioLanguages.isEmpty {
                    ForEach(planner.model.muxedFormats) { format in
                        Toggle(isOn: Binding(get: { current.audioFormatIds.contains(format.formatId) },
                                             set: { if $0 { planner.update { $0.audioFormatIds = [format.formatId] } } })) {
                            HStack {
                                Text(videoLabel(format))
                                Badge(text: L("term.muxed.label"), tone: .accent).help(L("term.muxed.body"))
                            }
                        }
                        .toggleStyle(RadioToggleStyle())
                    }
                }
            }

            if audioOnly {
                PickSection(L("download.section.audioFormat")) {
                    Picker(L("download.section.audioFormat"), selection: $planner.audioCodec) {
                        ForEach(DownloadPlanner.codecs, id: \.self) { Text(L("download.audioCodec.\($0)")).tag($0) }
                    }
                    if DownloadPlanner.lossy.contains(planner.audioCodec) {
                        Picker(L("download.quality"), selection: $planner.audioQuality) {
                            ForEach(DownloadPlanner.qualities, id: \.self) { Text("\($0) \(L("unit.kbps"))").tag($0) }
                        }
                    }
                }
            } else {
                PickSection(L("download.section.subtitles")) {
                    let subs = planner.model.subtitles
                    if subs.manual.isEmpty, subs.auto.isEmpty {
                        Text(L("inspect.noSubtitles")).foregroundStyle(.secondary)
                    }
                    if !subs.manual.isEmpty { Text(L("inspect.subManual")).font(.caption.weight(.semibold)).foregroundStyle(.secondary) }
                    ForEach(subs.manual) { subtitleRow($0) }
                    if !subs.auto.isEmpty { Text(L("inspect.subAuto")).font(.caption.weight(.semibold)).foregroundStyle(.secondary) }
                    ForEach(subs.auto) { subtitleRow($0) }
                    if !subs.autoTranslated.isEmpty {
                        Button(showTranslated ? L("inspect.subTranslatedHide") : L("inspect.subTranslatedCount", subs.autoTranslated.count)) {
                            showTranslated.toggle()
                        }
                        .buttonStyle(.link)
                        if showTranslated {
                            TextField(L("download.translatedFilter"), text: $filter).textFieldStyle(.roundedBorder).frame(maxWidth: 260)
                            ForEach(translated(subs.autoTranslated)) { subtitleRow($0) }
                        }
                    }
                }
            }

            PickSection(L("download.section.extras")) {
                Toggle(L("download.extra.thumbnail"), isOn: $planner.extras.thumbnail)
                Toggle(L("download.extra.thumbnail_file"), isOn: $planner.extras.thumbnailFile)
                Toggle(L("download.extra.description"), isOn: $planner.extras.description)
                Toggle(L("download.extra.info_json"), isOn: $planner.extras.infoJson)
            }

            PickSection(L("download.section.filename"), help: L("download.templateHelp")) {
                HStack {
                    TextField(L("download.section.filename"), text: Binding(get: { planner.templateText }, set: { planner.setTemplate($0) }))
                        .font(.system(.body, design: .monospaced))
                        .textFieldStyle(.roundedBorder)
                        .labelsHidden()
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("pick.template")
                    Button(L("download.templateReset")) { planner.resetTemplate() }
                }
            }

            if let command = planner.plan?.command, !command.isEmpty {
                PickSection(L("download.section.command")) { CommandText(command: command) }
            }
        }
        .padding(.top, 4)
        // A container: without .contain its identifier would replace every child's.
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("picker")
    }

    private func subtitleRow(_ row: SubtitleTrack) -> some View {
        Toggle(isOn: Binding(get: { planner.current.subtitleKeys.contains(row.key) }, set: { _ in planner.toggleSubtitle(row.key) })) {
            HStack(spacing: 6) {
                Text(Format.language(row.language))
                Text(row.key).font(.system(.callout, design: .monospaced)).foregroundStyle(.tertiary)
                if row.shadowedByManual == true { Text(L("inspect.subShadowed")).font(.caption).foregroundStyle(.secondary) }
            }
        }
        .toggleStyle(.checkbox)
        .disabled(row.shadowedByManual == true)
        .accessibilityIdentifier("pick.sub.\(row.key)")
    }

    private func translated(_ rows: [SubtitleTrack]) -> [SubtitleTrack] {
        let needle = filter.trimmingCharacters(in: .whitespaces).lowercased(with: Format.turkish)
        guard !needle.isEmpty else { return rows }
        return rows.filter { $0.key.contains(needle) || Format.language($0.language).lowercased(with: Format.turkish).contains(needle) }
    }
}

/// One part of the picker: a heading (with its explanation, if any) over its rows.
struct PickSection<Content: View>: View {
    let title: String
    var help: String? = nil
    @ViewBuilder var content: Content

    init(_ title: String, help: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.help = help
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Group {
                if let help { Term(title, help: help) } else { Text(title) }
            }
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 6) { content }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.quaternary.opacity(0.3), in: .rect(cornerRadius: 8))
        }
    }
}

func trackLabel(_ track: AudioFormat) -> String {
    var parts = [track.acodecLabel, Format.bitrate(track.abr ?? track.tbr)].compactMap { $0 }
    if track.filesize != nil { parts.append(Format.size(track.filesize, track.filesizeKind)) }
    return ([track.formatId] + [parts.filter { $0 != "–" }.joined(separator: " · ")]).joined(separator: " · ")
}

/// A radio button made of a toggle (macOS has no stand-alone one in SwiftUI).
struct RadioToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn = true
        } label: {
            HStack(spacing: 8) {
                Image(systemName: configuration.isOn ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(configuration.isOn ? Color.accentColor : .secondary)
                configuration.label
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(configuration.isOn ? .isSelected : [])
        .accessibilityValue(configuration.isOn ? "1" : "0")
    }
}

/// A toggle style chosen at run time (a radio in "audio only", a checkbox otherwise).
struct AnyToggleStyle: ToggleStyle {
    private let make: (Configuration) -> AnyView

    init<S: ToggleStyle>(_ style: S) { make = { AnyView(style.makeBody(configuration: $0)) } }

    func makeBody(configuration: Configuration) -> some View { make(configuration) }
}
