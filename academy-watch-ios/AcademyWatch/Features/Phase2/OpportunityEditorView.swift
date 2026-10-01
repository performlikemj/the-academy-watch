import SwiftUI

struct OpportunityEditorView: View {
  @StateObject private var model: OpportunityEditorViewModel
  @EnvironmentObject private var workspace: Phase2Workspace
  @Environment(\.dismiss) private var dismiss
  @FocusState private var focused: String?
  @State private var choosingZone = false
  @State private var zoneSearch = ""
  @State private var confirmation: String?
  @State private var confirmingDiscard = false
  private let onSaved: (Phase2Opportunity) -> Void
  init(
    programId: Int, post: Phase2Opportunity? = nil, flags: Phase2Flags,
    client: any Phase2API, onSaved: @escaping (Phase2Opportunity) -> Void = { _ in }
  ) {
    _model = StateObject(
      wrappedValue: OpportunityEditorViewModel(
        programId: programId, post: post, flags: flags, client: client))
    self.onSaved = onSaved
  }
  private var readOnly: Bool {
    model.locked || model.terminal || !model.canRecruit || !workspace.flags.opportunities
  }
  var body: some View {
    Phase2Page(
      title: model.post == nil ? "A place for someone new." : model.post!.title,
      eyebrow: "Recruiting · \(model.post?.status.capitalized ?? "New opportunity")"
    ) {
      if !model.ready && model.isBusy { CleatLoader("Loading editor…") }
      if let notice = model.notice {
        Text(notice).font(AcademyType.body).accessibilityIdentifier("post-notice")
      }
      Phase2ErrorView(message: model.error)
      if model.conflict {
        Button("Load latest post (replaces this draft)") { Task { await model.reloadLatest() } }
          .buttonStyle(FloodlightPillStyle(variant: .outline)).disabled(model.isBusy)
          .accessibilityIdentifier("post-reload-latest")
      }
      if model.locked {
        Text(
          "Advertised details and capacity are fixed once applications arrive. Trial changes use the applicant invitation."
        )
        .font(AcademyType.body).accessibilityIdentifier("post-terms-locked")
      }
      Phase2Section(title: "The opportunity")
      field("type", "Opportunity type") {
        Picker("Opportunity type", selection: $model.draft.type) {
          Text("Trial").tag("trial")
          Text("Open session").tag("open_session")
          Text("Position").tag("position")
        }.pickerStyle(.menu).accessibilityIdentifier("post-type")
      }
      input("title", "Title", text: $model.draft.title)
      input(
        "description", "About this opportunity", text: $model.draft.description, multiline: true)
      input("instructions", "What to bring", text: $model.draft.instructions, multiline: true)
      input(
        "position_requirements", "Positions / eligibility", text: $model.draft.positionRequirements)
      field("squad_id", "Squad") {
        Picker("Squad", selection: $model.draft.squadId) {
          Text("Whole club").tag(Optional<Int>.none)
          ForEach(model.squads) { Text($0.name).tag(Optional($0.id)) }
        }.pickerStyle(.menu).accessibilityIdentifier("post-squad")
      }
      Phase2Section(title: "Eligibility")
      field("gender_program", "Programme") {
        Picker("Programme", selection: $model.draft.genderProgram) {
          ForEach(["all", "boys", "girls", "men", "women", "mixed"], id: \.self) {
            Text($0.capitalized).tag($0)
          }
        }.pickerStyle(.menu).accessibilityIdentifier("post-programme")
      }
      input(
        "birth_year_min", "Earliest birth year (optional)", text: $model.draft.birthYearMin,
        numeric: true)
      input(
        "birth_year_max", "Latest birth year (optional)", text: $model.draft.birthYearMax,
        numeric: true)
      Phase2Section(title: "Place and time")
      input("venue", "Venue", text: $model.draft.venue)
      input("address", "Address (optional)", text: $model.draft.address)
      field("timezone", "Time zone") {
        Button {
          choosingZone = true
        } label: {
          HStack {
            Text(OpportunityZones.label(model.draft.timezone)).font(AcademyType.body)
            Spacer()
            Image(systemName: "chevron.down")
          }.padding(13).background(
            AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 12))
        }.buttonStyle(.plain).accessibilityIdentifier("post-timezone")
      }
      dateField("closes_at", "Applications close", date: $model.draft.closesAt)
      optionalDate(
        "starts_at", "Starts", date: $model.draft.startsAt, required: model.draft.type != "position"
      )
      optionalDate("ends_at", "Ends", date: $model.draft.endsAt, required: false)
      Text(
        "Dates use \(model.draft.timezone). Every advertised date must fall within 90 days of the original creation."
      )
      .font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
      if model.draft.type == "position", let deadline = model.inviteDeadline {
        Text(
          "Position invitations may run through \(Phase2Time.display(Phase2Time.submission(deadline, zone: model.draft.timezone), zone: model.draft.timezone)) — closing date +14 days. Application privacy limits still apply."
        )
        .font(AcademyType.caption).foregroundStyle(AcademyColors.secondaryText)
      }
      input("capacity", "Trial capacity (optional)", text: $model.draft.capacity, numeric: true)
      if !model.terminal {
        Phase2Section(title: "Publication")
        if model.post?.status != "published" {
          Button("Save draft") { save("draft") }.buttonStyle(FloodlightPillStyle(variant: .outline))
            .disabled(!model.canSave).accessibilityIdentifier("post-save-draft")
        }
        Button(model.post?.status == "published" ? "Save published post" : "Publish") {
          save("published")
        }
        .buttonStyle(FloodlightPillStyle()).disabled(!model.canSave).accessibilityIdentifier(
          "post-publish")
        if model.post != nil {
          Button("Close applications") { confirmation = "closed" }.buttonStyle(
            FloodlightPillStyle(variant: .outline)
          )
          .disabled(!model.canSave).accessibilityIdentifier("post-close")
          Button("Cancel opportunity") { confirmation = "cancelled" }.buttonStyle(
            FloodlightPillStyle(variant: .outline)
          )
          .disabled(!model.canSave).accessibilityIdentifier("post-cancel")
        }
      }
      if model.isBusy && model.ready { CleatLoader("Saving…") }
    }
    .navigationTitle(model.post == nil ? "Post a trial" : "Edit opportunity")
    .toolbar {
      ToolbarItem(placement: .confirmationAction) {
        Button("Done") {
          if model.isDirty { confirmingDiscard = true } else { dismiss() }
        }.disabled(model.isBusy)
      }
      ToolbarItemGroup(placement: .keyboard) {
        Spacer()
        Button("Done") { focused = nil }
      }
    }
    .task {
      await model.load()
      #if DEBUG && targetEnvironment(simulator)
        if Phase2Fixtures.screen == "post-error" { _ = await model.save(status: "draft") }
      #endif
    }
    .onChange(of: workspace.flags) { _, flags in model.updateFlags(flags) }
    .interactiveDismissDisabled(model.isDirty || model.isBusy)
    .sheet(isPresented: $choosingZone) { zonePicker }
    .confirmationDialog("Discard unsaved changes?", isPresented: $confirmingDiscard, titleVisibility: .visible) {
      Button("Discard changes", role: .destructive) { dismiss() }
      Button("Keep editing", role: .cancel) {}
    }
    .confirmationDialog(
      confirmation == "cancelled"
        ? "Cancel this opportunity and release outstanding reservations?"
        : "Close applications? Existing recruiting can continue.",
      isPresented: Binding(get: { confirmation != nil }, set: { if !$0 { confirmation = nil } }),
      titleVisibility: .visible
    ) {
      Button(
        confirmation == "cancelled" ? "Cancel opportunity" : "Close applications",
        role: .destructive
      ) {
        let status = confirmation!
        confirmation = nil
        Task { if await model.close(status: status), let post = model.post { onSaved(post) } }
      }
    }
    .accessibilityIdentifier("post-editor")
  }
  private func save(_ status: String) {
    focused = nil
    Task { if await model.save(status: status), let post = model.post { onSaved(post) } }
  }
  private func field<Content: View>(
    _ key: String, _ label: String, @ViewBuilder content: () -> Content
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Phase2Eyebrow(text: label)
      content().disabled(readOnly || model.isBusy)
      if let error = model.fieldErrors[key] {
        Text(error).font(AcademyType.caption).foregroundStyle(AcademyColors.danger)
          .accessibilityIdentifier("post-error-\(key)")
      }
    }
  }
  private func input(
    _ key: String, _ label: String, text: Binding<String>, multiline: Bool = false,
    numeric: Bool = false
  ) -> some View {
    field(key, label) {
      TextField(label, text: text, axis: multiline ? .vertical : .horizontal)
        .lineLimit(multiline ? 3...6 : 1...1).textFieldStyle(Phase2InputStyle())
        .keyboardType(numeric ? .numberPad : .default).focused($focused, equals: key)
        .submitLabel(.done).onSubmit { focused = nil }
        .accessibilityIdentifier("post-\(key)")
    }
  }
  private func dateField(_ key: String, _ label: String, date: Binding<Date>) -> some View {
    field(key, "\(label) (\(model.draft.timezone))") {
      DatePicker(label, selection: date, displayedComponents: [.date, .hourAndMinute])
        .environment(\.timeZone, Phase2Time.zone(model.draft.timezone))
        .accessibilityIdentifier("post-\(key)")
    }
  }
  private func optionalDate(_ key: String, _ label: String, date: Binding<Date?>, required: Bool)
    -> some View
  {
    VStack(alignment: .leading, spacing: 8) {
      if !required {
        Toggle(
          "Include \(label.lowercased()) date",
          isOn: Binding(
            get: { date.wrappedValue != nil },
            set: {
              date.wrappedValue = $0 ? model.draft.closesAt.addingTimeInterval(86400) : nil
            })
        ).disabled(readOnly || model.isBusy).accessibilityIdentifier("post-include-\(key)")
      }
      if date.wrappedValue != nil || required {
        dateField(
          key, label,
          date: Binding(
            get: { date.wrappedValue ?? model.draft.closesAt.addingTimeInterval(86400) },
            set: { date.wrappedValue = $0 }))
      }
    }
  }
  private var zonePicker: some View {
    NavigationStack {
      List {
        let zones = OpportunityZones.allowed.filter {
          zoneSearch.isEmpty || $0.localizedCaseInsensitiveContains(zoneSearch)
        }
        let groups = Dictionary(grouping: zones) {
          $0.split(separator: "/").first.map(String.init) ?? "UTC"
        }
        ForEach(groups.keys.sorted(), id: \.self) { region in
          Section(region) {
            ForEach(groups[region] ?? [], id: \.self) { zone in
              Button {
                model.changeZone(zone)
                choosingZone = false
              } label: {
                HStack {
                  Text(OpportunityZones.label(zone))
                  Spacer()
                  if zone == model.draft.timezone { Image(systemName: "checkmark") }
                }
              }.foregroundStyle(AcademyColors.text).accessibilityIdentifier("post-zone-\(zone)")
            }
          }
        }
      }.searchable(text: $zoneSearch, prompt: "Find city or region").navigationTitle("Time zone")
        .toolbar {
          ToolbarItem(placement: .confirmationAction) { Button("Done") { choosingZone = false } }
        }
    }
  }
}
