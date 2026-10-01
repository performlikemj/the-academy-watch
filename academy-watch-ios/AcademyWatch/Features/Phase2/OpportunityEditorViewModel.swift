import Combine
import Foundation

enum OpportunityZones {
  static let allowed: [String] = {
    guard let url = Bundle.main.url(forResource: "opportunity-timezones", withExtension: "json"),
      let data = try? Data(contentsOf: url),
      let values = try? JSONDecoder().decode([String].self, from: data)
    else { return ["UTC"] }
    return values
  }()
  static func defaultZone(device: String = TimeZone.current.identifier) -> String {
    allowed.contains(device) ? device : "UTC"
  }
  static func label(_ id: String, at date: Date = Phase2Time.now) -> String {
    let offset = Phase2Time.zone(id).secondsFromGMT(for: date)
    return id.replacingOccurrences(of: "_", with: " ") + " — "
      + String(
        format: "UTC%@%02d:%02d (now)", offset < 0 ? "−" : "+", abs(offset) / 3600,
        abs(offset) % 3600 / 60)
  }
}

struct OpportunityDraft: Equatable {
  var type = "trial"
  var title = ""
  var description = ""
  var instructions = ""
  var positionRequirements = "All positions"
  var squadId: Int?
  var birthYearMin = ""
  var birthYearMax = ""
  var genderProgram = "all"
  var timezone = OpportunityZones.defaultZone()
  var venue = ""
  var address = ""
  var capacity = ""
  var startsAt: Date? = Phase2Time.now.addingTimeInterval(7 * 86400)
  var endsAt: Date? = Phase2Time.now.addingTimeInterval(7 * 86400 + 7200)
  var closesAt = Phase2Time.now.addingTimeInterval(6 * 86400)
  init() {}
  init(_ post: Phase2Opportunity) {
    type = post.type
    title = post.title
    description = post.description
    instructions = post.instructions
    positionRequirements = post.positionRequirements
    squadId = post.squadId
    birthYearMin = post.birthYearMin.map(String.init) ?? ""
    birthYearMax = post.birthYearMax.map(String.init) ?? ""
    genderProgram = post.genderProgram
    timezone = post.timezone
    venue = post.venue
    address = post.address
    capacity = post.capacity.map(String.init) ?? ""
    startsAt = Phase2Time.date(post.startsAt)
    endsAt = Phase2Time.date(post.endsAt)
    closesAt = Phase2Time.date(post.closesAt) ?? Phase2Time.now
  }
}

/// Encodes nullable terms explicitly so clearing an optional value actually clears it on PATCH.
/// With retained applications, the request contains lifecycle controls only.
struct OpportunityEditSubmission: Encodable {
  let draft: OpportunityDraft
  let status: String
  let expectedVersion: Int?
  let locked: Bool
  enum CodingKeys: String, CodingKey {
    case status, expectedVersion, type, title, description, instructions, positionRequirements,
      squadId
    case birthYearMin, birthYearMax, genderProgram, timezone, venue, address, capacity, startsAt,
      endsAt, closesAt
  }
  func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    try c.encode(status, forKey: .status)
    try c.encodeIfPresent(expectedVersion, forKey: .expectedVersion)
    guard !locked else { return }
    try c.encode(draft.type, forKey: .type)
    try c.encode(draft.title.trimmingCharacters(in: .whitespacesAndNewlines), forKey: .title)
    try c.encode(
      draft.description.trimmingCharacters(in: .whitespacesAndNewlines), forKey: .description)
    try c.encode(
      draft.instructions.trimmingCharacters(in: .whitespacesAndNewlines), forKey: .instructions)
    try c.encode(
      draft.positionRequirements.trimmingCharacters(in: .whitespacesAndNewlines),
      forKey: .positionRequirements)
    try c.encode(draft.squadId, forKey: .squadId)
    try c.encode(Int(draft.birthYearMin), forKey: .birthYearMin)
    try c.encode(Int(draft.birthYearMax), forKey: .birthYearMax)
    try c.encode(draft.genderProgram, forKey: .genderProgram)
    try c.encode(draft.timezone, forKey: .timezone)
    try c.encode(draft.venue.trimmingCharacters(in: .whitespacesAndNewlines), forKey: .venue)
    try c.encode(draft.address.trimmingCharacters(in: .whitespacesAndNewlines), forKey: .address)
    try c.encode(Int(draft.capacity), forKey: .capacity)
    try c.encode(
      draft.startsAt.map { Phase2Time.submission($0, zone: draft.timezone) }, forKey: .startsAt)
    try c.encode(
      draft.endsAt.map { Phase2Time.submission($0, zone: draft.timezone) }, forKey: .endsAt)
    try c.encode(Phase2Time.submission(draft.closesAt, zone: draft.timezone), forKey: .closesAt)
  }
}

@MainActor
final class OpportunityEditorViewModel: ObservableObject {
  @Published var draft: OpportunityDraft
  @Published private(set) var post: Phase2Opportunity?
  @Published private(set) var squads: [Phase2Squad] = []
  @Published private(set) var fieldErrors: [String: String] = [:]
  @Published private(set) var error: String?
  @Published private(set) var notice: String?
  @Published private(set) var isBusy = false
  @Published private(set) var ready = false
  @Published private(set) var conflict = false
  @Published private(set) var canRecruit = false
  let programId: Int
  private let client: any Phase2API
  private var creationClock: Date?
  private var savedDraft: OpportunityDraft
  var isDirty: Bool { draft != savedDraft }
  private var flags: Phase2Flags
  init(programId: Int, post: Phase2Opportunity? = nil, flags: Phase2Flags, client: any Phase2API) {
    self.programId = programId
    self.post = post
    self.flags = flags
    self.client = client
    let initial = post.map(OpportunityDraft.init) ?? OpportunityDraft()
    draft = initial
    savedDraft = initial
  }
  var locked: Bool { (post?.applicationCount ?? 0) > 0 }
  var terminal: Bool { ["closed", "cancelled"].contains(post?.status ?? "") }
  var canSave: Bool {
    ready && flags.opportunities && canRecruit && !isBusy && !conflict && !terminal
  }
  var horizon: Date? {
    if let created = Phase2Time.date(post?.createdAt) {
      return created.addingTimeInterval(90 * 86400)
    }
    if let post, post.type != "position" { return Phase2Time.date(post.trialInviteDeadline) }
    if let creationClock { return creationClock.addingTimeInterval(90 * 86400) }
    return post == nil ? Phase2Time.now.addingTimeInterval(90 * 86400) : nil
  }
  var inviteDeadline: Date? {
    draft.type == "position" ? draft.closesAt.addingTimeInterval(14 * 86400) : horizon
  }
  /// Changing a posting zone changes the intended instant, never the entered wall time.
  /// Reject a DST gap instead of Calendar silently normalizing it into another time.
  func changeZone(_ zone: String) {
    guard !isBusy, !locked, !terminal, OpportunityZones.allowed.contains(zone) else { return }
    var old = Calendar(identifier: .gregorian)
    old.timeZone = Phase2Time.zone(draft.timezone)
    var target = old
    target.timeZone = Phase2Time.zone(zone)
    let parts: Set<Calendar.Component> = [.year, .month, .day, .hour, .minute, .second]
    func remap(_ date: Date) -> Date? {
      let components = old.dateComponents(parts, from: date)
      guard let result = target.date(from: components),
        target.dateComponents(parts, from: result) == components else { return nil }
      let offsets = Set([-86400.0, 0, 86400.0].map {
        target.timeZone.secondsFromGMT(for: result.addingTimeInterval($0))
      })
      let offset = target.timeZone.secondsFromGMT(for: result)
      for other in offsets where other != offset {
        let alternative = result.addingTimeInterval(TimeInterval(offset - other))
        if target.dateComponents(parts, from: alternative) == components { return nil }
      }
      return result
    }
    var changed = draft
    for (key, date) in [("closes_at", Optional(draft.closesAt)), ("starts_at", draft.startsAt), ("ends_at", draft.endsAt)] {
      guard let date else { continue }
      guard let value = remap(date) else {
        fieldErrors[key] = "This wall time is skipped or repeated in \(zone) because the clocks change. Choose another time first."
        error = "Time zone was not changed. Check the highlighted date."
        return
      }
      switch key {
      case "closes_at": changed.closesAt = value
      case "starts_at": changed.startsAt = value
      default: changed.endsAt = value
      }
    }
    changed.timezone = zone
    draft = changed
    fieldErrors = [:]
    error = nil
  }
  func updateFlags(_ flags: Phase2Flags) { self.flags = flags }
  func load() async {
    guard !isBusy, flags.opportunities else {
      ready = false
      return
    }
    isBusy = true
    error = nil
    defer { isBusy = false }
    do {
      let access: ClubAccessResponse = try await client.read("club/\(programId)/access/me")
      canRecruit = access.access.programId == programId && access.access.canRecruit
      guard canRecruit else {
        ready = false
        error = "Only the club owner or manager can post opportunities."
        return
      }
      let response: SquadsResponse = try await client.read("club/\(programId)/squads")
      squads = response.squads
      ready = true
    } catch {
      ready = false
      self.error = phase2Error(error)
    }
  }
  @discardableResult func save(status: String, now: Date = Phase2Time.now) async -> Bool {
    guard canSave else { return false }
    fieldErrors = [:]
    error = nil
    notice = nil
    guard ["draft", "published"].contains(status),
      !(post?.status == "published" && status == "draft")
    else { return false }
    if !locked { validate(now: now) }
    guard fieldErrors.isEmpty else {
      error = "Check the highlighted fields. Nothing was saved."
      return false
    }
    isBusy = true
    defer { isBusy = false }
    do {
      let creating = post == nil
      let response: OpportunityResponse = try await client.write(
        "club/\(programId)/opportunities" + (post.map { "/\($0.id)" } ?? ""),
        method: post == nil ? "POST" : "PATCH",
        body: OpportunityEditSubmission(
          draft: draft, status: status, expectedVersion: post?.version, locked: locked))
      if creating { creationClock = now }
      post = response.opportunity
      draft = OpportunityDraft(response.opportunity)
      savedDraft = draft
      notice =
        status == "draft"
        ? "Draft saved. Visible only to your club." : "Published. Adult players can now apply."
      return true
    } catch {
      handle(error)
      return false
    }
  }
  @discardableResult func close(status: String) async -> Bool {
    guard canSave, let post, ["closed", "cancelled"].contains(status) else { return false }
    isBusy = true
    error = nil
    notice = nil
    fieldErrors = [:]
    defer { isBusy = false }
    do {
      let response: OpportunityResponse = try await client.write(
        "club/\(programId)/opportunities/\(post.id)/close",
        body: VersionAction(expectedVersion: post.version, status: status))
      self.post = response.opportunity
      notice =
        status == "closed"
        ? "Applications closed. Existing recruiting can continue."
        : "Opportunity cancelled. Outstanding applications and reservations are released."
      return true
    } catch {
      handle(error)
      return false
    }
  }
  /// Explicit reconciliation; no automatic retries with a new version or overwrite of a draft.
  func reloadLatest() async {
    guard let post, !isBusy else { return }
    isBusy = true
    defer { isBusy = false }
    do {
      var page = 1
      while true {
        let response: OpportunitiesResponse = try await client.read(
          "club/\(programId)/opportunities",
          query: [URLQueryItem(name: "page", value: String(page))])
        if let fresh = response.opportunities.first(where: { $0.id == post.id }) {
          self.post = fresh
          draft = OpportunityDraft(fresh)
          savedDraft = draft
          conflict = false
          fieldErrors = [:]
          error = nil
          notice = "Latest post loaded. Review before saving."
          return
        }
        guard response.hasMore else {
          ready = false
          error = "This post is no longer available."
          return
        }
        page += 1
      }
    } catch { self.error = phase2Error(error) }
  }
  func validate(now: Date) {
    let fields = [
      ("title", draft.title, 180), ("description", draft.description, 6000),
      ("instructions", draft.instructions, 3000),
      ("position_requirements", draft.positionRequirements, 200),
      ("venue", draft.venue, 200), ("address", draft.address, 300),
    ]
    for (key, value, limit) in fields {
      if value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        && !["instructions", "address"].contains(key)
      {
        fieldErrors[key] = "This field is required."
      } else if value.count > limit {
        fieldErrors[key] = "Use no more than \(limit) characters."
      }
    }
    if !OpportunityZones.allowed.contains(draft.timezone) {
      fieldErrors["timezone"] = "Choose an allowed time zone."
    }
    if !["trial", "open_session", "position"].contains(draft.type) {
      fieldErrors["type"] = "Choose an opportunity type."
    }
    if !["all", "boys", "girls", "men", "women", "mixed"].contains(draft.genderProgram) {
      fieldErrors["gender_program"] = "Choose a programme."
    }
    if let id = draft.squadId, !squads.contains(where: { $0.id == id }) {
      fieldErrors["squad_id"] = "Choose a squad in this club."
    }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    for (key, text, range) in [
      ("birth_year_min", draft.birthYearMin, 1900...calendar.component(.year, from: now)),
      ("birth_year_max", draft.birthYearMax, 1900...calendar.component(.year, from: now)),
      ("capacity", draft.capacity, 1...10000),
    ] {
      if !text.isEmpty && (Int(text).map { range.contains($0) } != true) {
        fieldErrors[key] =
          "Enter a whole number between \(range.lowerBound) and \(range.upperBound)."
      }
    }
    if let low = Int(draft.birthYearMin), let high = Int(draft.birthYearMax), low > high {
      fieldErrors["birth_year_max"] = "Latest birth year must be at least the earliest year."
    }
    if draft.closesAt <= now { fieldErrors["closes_at"] = "Choose a future closing date." }
    if let horizon, draft.closesAt > horizon {
      fieldErrors["closes_at"] = "Must be within 90 days of creation."
    }
    if draft.type != "position" && draft.startsAt == nil {
      fieldErrors["starts_at"] = "A start date is required for trials and sessions."
    }
    if let start = draft.startsAt {
      if start < draft.closesAt {
        fieldErrors["starts_at"] = "Must be on or after the closing date."
      }
      if let horizon, start > horizon {
        fieldErrors["starts_at"] = "Must be within 90 days of creation."
      }
    }
    if let end = draft.endsAt {
      if draft.startsAt.map({ end > $0 }) != true {
        fieldErrors["ends_at"] = "Must be after the start."
      }
      if let horizon, end > horizon {
        fieldErrors["ends_at"] = "Must be within 90 days of creation."
      }
    }
  }
  private func handle(_ failure: Error) {
    let code: String
    switch failure {
    case APIClientError.server(_, let value): code = value
    case APIClientError.codedServer(_, _, let value, _): code = value
    default: code = ""
    }
    if phase2Status(failure) == 409 {
      conflict = true
      error =
        code == "advertised_terms_locked"
        ? "An application arrived. Advertised terms are now locked. Load the latest post before continuing; your draft is still here."
        : "This post changed. Load the latest post and review before saving; your draft is still here."
      return
    }
    if [403, 404].contains(phase2Status(failure) ?? 0) { ready = false }
    if [400, 422].contains(phase2Status(failure) ?? 0) {
      let map: [String: [String]] = [
        "invalid_age_band": ["birth_year_max"], "deadline_too_far": ["closes_at"],
        "invalid_event_dates": ["starts_at", "ends_at"], "event_date_required": ["starts_at"],
        "required_opportunity_details": ["title", "description", "venue", "closes_at"],
      ]
      let fields = map[code] ?? (code.hasPrefix("invalid_") ? [String(code.dropFirst(8))] : [])
      let messages = [
        "title": "Enter a title of 1–180 characters.",
        "description": "Enter a description of 1–6,000 characters.",
        "instructions": "Use no more than 3,000 characters.",
        "position_requirements": "Enter eligibility of 1–200 characters.",
        "venue": "Enter a venue of 1–200 characters.",
        "address": "Use no more than 300 characters.",
        "timezone": "Choose a time zone from the server allowlist.",
        "squad_id": "Choose a squad belonging to this club.",
        "starts_at":
          "Start must be on or after closing, within the original creation +90-day horizon.",
        "ends_at": "End must follow start, within the original creation +90-day horizon.",
        "closes_at": "Choose a future closing date within the original creation +90-day horizon.",
        "birth_year_min": "Choose a valid earliest birth year.",
        "birth_year_max": "Choose a valid latest year on or after the earliest year.",
        "capacity": "Enter a whole number from 1 to 10,000.",
      ]
      for field in fields { fieldErrors[field] = messages[field] ?? "Check this field." }
    }
    error = phase2Error(failure)
  }
}
