import XCTest
@testable import AcademyWatch

// Fixture provenance (serializer shapes, not hand-designed API contracts):
// - scout_verification.json mirrors `ScoutVerification.to_dict()` in
//   full-circle `src/models/trust.py` and the `verification` envelope in
//   `src/routes/trust.py` GET/POST `/api/scout/verification`.
// - contact_requests_sent.json mirrors `ContactRequest.to_dict()` in
//   full-circle `src/models/contact.py` and the paginated GET
//   `/api/contact/requests` envelope in `src/routes/contact.py`.
// - contact_messages.json mirrors `ContactMessage.to_dict()` and
//   `ContactRequest.to_dict()` in `src/models/contact.py`, plus the paginated
//   GET `/api/contact/requests/<id>/messages` envelope in `src/routes/contact.py`.
// - contact_outcome.json mirrors `ContactOutcome.to_dict()` and
//   `ContactRequest.to_dict()` in `src/models/contact.py`, plus the POST
//   `/api/contact/requests/<id>/outcome` envelope in `src/routes/contact.py`.
final class FullCircleDecodingTests: XCTestCase {
    func testDecodesScoutVerificationSerializerShape() throws {
        let response: ScoutVerificationResponse = try decodeFixture("scout_verification")
        let verification = try XCTUnwrap(response.verification)

        XCTAssertEqual(verification.id, 28)
        XCTAssertEqual(verification.fullName, "Alex Morgan")
        XCTAssertEqual(verification.organization, "Northbank Recruitment")
        XCTAssertEqual(verification.roleTitle, "First-team scout")
        XCTAssertEqual(verification.evidenceUrls.count, 2)
        XCTAssertEqual(verification.status, .rejected)
        XCTAssertEqual(verification.submittedAt, "2026-07-14T09:00:00")
        XCTAssertEqual(verification.reviewedAt, "2026-07-15T11:30:00")
        XCTAssertEqual(
            verification.reviewNotes,
            "Please provide evidence that identifies your current role at the organization."
        )
        XCTAssertNil(verification.revocationReason)
    }

    func testDecodesSentContactRequestsAndEveryStatus() throws {
        let response: ContactRequestsResponse = try decodeFixture("contact_requests_sent")

        XCTAssertEqual(response.box, .sent)
        XCTAssertEqual(response.total, 5)
        XCTAssertEqual(response.limit, 50)
        XCTAssertEqual(response.offset, 0)
        XCTAssertEqual(
            response.requests.map(\.status),
            [.accepted, .pending, .declined, .withdrawn, .expired]
        )

        let accepted = try XCTUnwrap(response.requests.first)
        XCTAssertEqual(accepted.id, "01010101-1111-4111-8111-010101010101")
        XCTAssertEqual(accepted.playerApiId, 403_064)
        XCTAssertEqual(accepted.participants.scout.displayName, "Alex Morgan")
        XCTAssertEqual(accepted.participants.player.displayName, "Jordan Reed")
        XCTAssertEqual(accepted.latestOutcome?.stage, .trialScheduled)
        XCTAssertEqual(accepted.latestOutcome?.notes, "Trial booked for next Thursday.")

        XCTAssertNil(response.requests[1].respondedAt)
        XCTAssertNil(response.requests[3].participants.player.displayName)
        XCTAssertNil(response.requests[4].latestOutcome)
    }

    func testDecodesContactMessagesSerializerAndRouteEnvelope() throws {
        let response: ContactMessagesResponse = try decodeFixture("contact_messages")

        XCTAssertEqual(response.total, 2)
        XCTAssertEqual(response.limit, 50)
        XCTAssertEqual(response.offset, 0)
        XCTAssertEqual(response.messages.map(\.senderRole), [.scout, .player])
        XCTAssertEqual(response.messages.first?.senderDisplayName, "Alex Morgan")
        XCTAssertEqual(
            response.messages.last?.contactRequestId,
            "01010101-1111-4111-8111-010101010101"
        )
        XCTAssertEqual(response.contactRequest.status, .accepted)
        XCTAssertEqual(response.contactRequest.latestOutcome?.stage, .contacted)
    }

    func testDecodesOutcomeAndRefreshedContactRequestEnvelope() throws {
        let response: ContactOutcomeResponse = try decodeFixture("contact_outcome")

        XCTAssertEqual(response.outcome.stage, .signed)
        XCTAssertEqual(response.outcome.notes, "Scholarship agreement completed.")
        XCTAssertEqual(response.outcome.occurredAt, "2026-07-17T12:00:00")
        XCTAssertEqual(response.contactRequest.latestOutcome, response.outcome)
    }

    func testEncodesMutationBodiesWithBackendFieldNamesAndEnumValues() throws {
        let verification = try encodeObject(
            ScoutVerificationSubmission(
                fullName: "Alex Morgan",
                organization: "Northbank Recruitment",
                roleTitle: "First-team scout",
                statement: "I cover academy recruitment.",
                evidenceUrls: ["https://northbank.example/scouting/alex-morgan"]
            )
        )
        XCTAssertEqual(verification["full_name"] as? String, "Alex Morgan")
        XCTAssertEqual(
            verification["evidence_urls"] as? [String],
            ["https://northbank.example/scouting/alex-morgan"]
        )

        let introduction = try encodeObject(
            CreateContactRequestBody(playerApiId: 403_064, message: "Could we speak?")
        )
        XCTAssertEqual(introduction["player_api_id"] as? Int, 403_064)
        XCTAssertEqual(introduction["message"] as? String, "Could we speak?")

        let threadMessage = try encodeObject(CreateContactMessageBody(body: "Tuesday works."))
        XCTAssertEqual(threadMessage["body"] as? String, "Tuesday works.")

        let outcome = try encodeObject(
            ReportContactOutcomeBody(
                stage: .trialCompleted,
                notes: nil,
                occurredAt: "2026-07-17T12:00:00Z"
            )
        )
        XCTAssertEqual(outcome["stage"] as? String, "trial_completed")
        XCTAssertEqual(outcome["occurred_at"] as? String, "2026-07-17T12:00:00Z")
        XCTAssertNil(outcome["notes"])
    }

    private func decodeFixture<Response: Decodable>(_ name: String) throws -> Response {
        let fixtureURL = try XCTUnwrap(
            Bundle(for: Self.self).url(forResource: name, withExtension: "json")
        )
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Response.self, from: Data(contentsOf: fixtureURL))
    }

    private func encodeObject<Body: Encodable>(_ body: Body) throws -> [String: Any] {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(body)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}
