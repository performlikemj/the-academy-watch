import XCTest

@testable import AcademyWatch

private actor EditorAPI: Phase2API {
  let fixture = Phase2FixtureTransport(mode: "editor")
  var failure: Error?
  var bodies: [[String: Any]] = []
  func refuse(_ error: Error?) { failure = error }
  func lastBody() -> [String: Any] { bodies.last ?? [:] }
  func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws
    -> Data
  {
    if let body { bodies.append(try JSONSerialization.jsonObject(with: body) as! [String: Any]) }
    if let failure { throw failure }
    return try await fixture.phase2Data(path: path, method: method, query: query, body: body)
  }
}
@MainActor
final class OpportunityEditorTests: XCTestCase {
  private let now = Phase2Time.date("2026-10-01T10:00:00Z")!
  private func model(_ api: any Phase2API, flags: Phase2Flags = Phase2Flags(opportunities: true))
    -> OpportunityEditorViewModel
  {
    OpportunityEditorViewModel(programId: 101, flags: flags, client: api)
  }
  private func fill(_ m: OpportunityEditorViewModel) {
    m.draft.title = "Open trial"
    m.draft.description = "A training session."
    m.draft.venue = "Training ground"
    m.draft.timezone = "Europe/London"
    m.draft.closesAt = now.addingTimeInterval(86400)
    m.draft.startsAt = now.addingTimeInterval(2 * 86400)
    m.draft.endsAt = now.addingTimeInterval(2 * 86400 + 7200)
  }
  func testCreatePublishReconcileApplicationLockAndClose() async throws {
    let api = EditorAPI()
    let m = model(api)
    await m.load()
    fill(m)
    XCTAssertTrue(m.canSave)
    let draftSaved = await m.save(status: "draft", now: now)
    XCTAssertTrue(draftSaved)
    XCTAssertEqual(m.post?.status, "draft")
    XCTAssertEqual(m.post?.version, 1)
    let published = await m.save(status: "published", now: now)
    XCTAssertTrue(published)
    XCTAssertEqual(m.post?.status, "published")
    XCTAssertEqual(m.post?.version, 2)
    await m.reloadLatest()
    XCTAssertTrue(m.locked)
    m.draft.title = "Unsent locked edit"
    let lifecycleSaved = await m.save(status: "published", now: now)
    XCTAssertTrue(lifecycleSaved)
    let payload = await api.lastBody()
    XCTAssertEqual(Set(payload.keys), ["expected_version", "status"])
    XCTAssertEqual(m.post?.title, "Open trial")
    let closed = await m.close(status: "closed")
    XCTAssertTrue(closed)
    XCTAssertTrue(m.terminal)
    XCTAssertFalse(m.canSave)
  }
  func testFlagsAndCurrentServerCapabilityFailClosed() async {
    for mode in ["coach", "off"] {
      let m = model(
        Phase2FixtureTransport(mode: mode), flags: Phase2Flags(opportunities: mode != "off"))
      await m.load()
      XCTAssertFalse(m.canSave)
    }
    let m = model(EditorAPI())
    await m.load()
    m.updateFlags(Phase2Flags())
    XCTAssertFalse(m.canSave)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    for role in ["coach", "analyst", "viewer"] {
      let data = Data(
        "{\"program_id\":101,\"role\":\"\(role)\",\"verified\":true,\"whole_club\":true,\"all_squads\":true,\"squad_ids\":[],\"capabilities\":[\"recruiting\"]}"
          .utf8)
      XCTAssertFalse(try! decoder.decode(ClubAccess.self, from: data).canRecruit)
    }
  }
  func testAllFieldValidationAndCreationHorizon() async {
    let m = model(EditorAPI())
    await m.load()
    fill(m)
    m.draft.title = String(repeating: "x", count: 181)
    m.draft.description = ""
    m.draft.capacity = "0"
    m.draft.birthYearMin = "2009"
    m.draft.birthYearMax = "2000"
    m.draft.timezone = "Factory"
    m.draft.squadId = 999
    m.draft.closesAt = now.addingTimeInterval(91 * 86400)
    m.draft.startsAt = nil
    m.validate(now: now)
    for key in [
      "title", "description", "capacity", "birth_year_max", "timezone", "squad_id", "closes_at",
      "starts_at",
    ] {
      XCTAssertNotNil(m.fieldErrors[key], key)
    }
  }
  func testOriginalClockAndPositionClosePlus14Days() async throws {
    let api = EditorAPI()
    let m = model(api)
    await m.load()
    fill(m)
    m.draft.type = "position"
    m.draft.startsAt = nil
    m.draft.endsAt = nil
    XCTAssertEqual(m.inviteDeadline, m.draft.closesAt.addingTimeInterval(14 * 86400))
    let saved = await m.save(status: "draft", now: now)
    XCTAssertTrue(saved)
    let horizon = try XCTUnwrap(m.horizon)
    XCTAssertEqual(horizon, now.addingTimeInterval(90 * 86400))
    m.draft.closesAt = now.addingTimeInterval(91 * 86400)
    let updated = await m.save(status: "draft", now: now.addingTimeInterval(20 * 86400))
    XCTAssertFalse(updated)
    XCTAssertNotNil(m.fieldErrors["closes_at"])
  }
  func test422Field409ReconciliationAnd429KeepDraft() async {
    let api = EditorAPI()
    let m = model(api)
    await m.load()
    fill(m)
    let saved = await m.save(status: "draft", now: now)
    XCTAssertTrue(saved)
    m.draft.title = "My retained draft"
    await api.refuse(APIClientError.server(statusCode: 422, message: "invalid_title"))
    let rejected = await m.save(status: "published", now: now)
    XCTAssertFalse(rejected)
    XCTAssertNotNil(m.fieldErrors["title"])
    XCTAssertEqual(m.draft.title, "My retained draft")
    await api.refuse(APIClientError.server(statusCode: 429, message: "rate_limit"))
    _ = await m.save(status: "published", now: now)
    XCTAssertTrue(m.error?.contains("Too many attempts") == true)
    await api.refuse(APIClientError.server(statusCode: 409, message: "advertised_terms_locked"))
    _ = await m.save(status: "published", now: now)
    XCTAssertTrue(m.conflict)
    XCTAssertFalse(m.canSave)
    XCTAssertEqual(m.draft.title, "My retained draft")
    await api.refuse(nil)
    await m.reloadLatest()
    XCTAssertFalse(m.conflict)
    XCTAssertEqual(m.draft.title, "Open trial")
  }
  func testNullableFieldsAreExplicitAndPostedZoneHasOffset() throws {
    var draft = OpportunityDraft()
    draft.timezone = "Asia/Kolkata"
    draft.startsAt = now
    draft.endsAt = nil
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    let data = try encoder.encode(
      OpportunityEditSubmission(draft: draft, status: "draft", expectedVersion: 7, locked: false))
    let body = try JSONSerialization.jsonObject(with: data) as! [String: Any]
    for key in ["ends_at", "birth_year_min", "birth_year_max", "capacity", "squad_id"] {
      XCTAssertTrue(body[key] is NSNull, key)
    }
    XCTAssertTrue((body["starts_at"] as? String)?.hasSuffix("+05:30") == true)
  }
  func testPickerExactlyMatchesServerAllowlistAndDefaultsOnlyAllowedDeviceZones() throws {
    let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("academy-watch-backend/src/data/opportunity_timezones.json")
    XCTAssertEqual(
      OpportunityZones.allowed,
      try JSONDecoder().decode([String].self, from: Data(contentsOf: source)))
    for zone in ["UTC", "Asia/Kolkata", "Europe/Kyiv", "US/Eastern"] {
      if OpportunityZones.allowed.contains(zone) {
        XCTAssertEqual(OpportunityZones.defaultZone(device: zone), zone)
      }
    }
    XCTAssertEqual(OpportunityZones.defaultZone(device: "Factory"), "UTC")
  }
}
