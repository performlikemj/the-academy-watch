import XCTest
@testable import AcademyWatch

// Fixture provenance (serializer shapes, not hand-designed API contracts):
// - scout_verification.json mirrors `ScoutVerification.to_dict()` in
//   full-circle `src/models/trust.py` and the `verification` envelope in
//   `src/routes/trust.py` GET/POST `/api/scout/verification`.
// - contact_requests_sent.json mirrors `ContactRequest.to_dict()` in
//   full-circle `src/models/contact.py` and the paginated GET
//   `/api/contact/requests` envelope in `src/routes/contact.py`, including
//   FC-B3 routing, club-consent, permission-attestation and messaging gates.
// - contact_requests_inbox.json mirrors that same serializer and the
//   `box=inbox` owner envelope exercised by full-circle `test_contact.py`.
// - contact_messages.json mirrors `ContactMessage.to_dict()` and
//   `ContactRequest.to_dict()` in `src/models/contact.py`, plus the paginated
//   GET `/api/contact/requests/<id>/messages` envelope in `src/routes/contact.py`;
//   its club message and programme participant follow `test_contact.py`'s
//   three-party thread assertion.
// - contact_outcome.json mirrors `ContactOutcome.to_dict()` and
//   `ContactRequest.to_dict()` in `src/models/contact.py`, plus the POST
//   `/api/contact/requests/<id>/outcome` envelope in `src/routes/contact.py`.
// - interest_signals.json is the exact aggregate asserted by
//   `TestInterestSignals.test_aggregates_are_correct_distinct_and_identity_free`
//   and mirrors `my_interest_signals()` in `src/routes/showcase.py`.
// - content_report.json mirrors `ContentReport.to_dict()` in
//   `src/models/trust.py` and the POST `/api/reports` envelope, using the
//   contact-message payload from `test_participant_can_report_message...`.
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
        XCTAssertEqual(accepted.participants.club?.displayName, "On Platform FC")
        XCTAssertEqual(accepted.participants.club?.clubProgramId, 101)
        XCTAssertEqual(accepted.routingMode, .clubIncluded)
        XCTAssertEqual(accepted.clubConsentStatus, .granted)
        XCTAssertTrue(accepted.messagingOpen)
        XCTAssertEqual(accepted.latestOutcome?.stage, .trialScheduled)
        XCTAssertEqual(accepted.latestOutcome?.notes, "Trial booked for next Thursday.")

        XCTAssertNil(response.requests[1].respondedAt)
        XCTAssertEqual(response.requests[1].routingMode, .clubIncluded)
        XCTAssertEqual(response.requests[1].clubConsentStatus, .pending)
        XCTAssertFalse(response.requests[1].messagingOpen)
        XCTAssertEqual(response.requests[2].clubConsentStatus, .declined)
        XCTAssertNil(response.requests[3].participants.player.displayName)
        XCTAssertEqual(response.requests[4].routingMode, .clubNotified)
        XCTAssertTrue(response.requests[4].permissionAttestation)
        XCTAssertNotNil(response.requests[4].permissionAttestedAt)
        XCTAssertNil(response.requests[4].latestOutcome)
    }

    func testDecodesIncomingContactRequestsWithOnlySerializerIdentity() throws {
        let response: ContactRequestsResponse = try decodeFixture("contact_requests_inbox")

        XCTAssertEqual(response.box, .inbox)
        XCTAssertEqual(response.total, 2)
        XCTAssertEqual(response.limit, 50)
        XCTAssertEqual(response.offset, 0)
        XCTAssertEqual(response.requests.map(\.status), [.pending, .accepted])
        XCTAssertEqual(response.requests.first?.participants.scout.displayName, "Alex Morgan")
        XCTAssertEqual(response.requests.first?.participants.player.displayName, "Habeeb Amass")
        XCTAssertNil(response.requests.first?.respondedAt)
        XCTAssertEqual(response.requests.last?.latestOutcome?.stage, .contacted)
    }

    func testDecodesContactMessagesSerializerAndRouteEnvelope() throws {
        let response: ContactMessagesResponse = try decodeFixture("contact_messages")

        XCTAssertEqual(response.total, 3)
        XCTAssertEqual(response.limit, 50)
        XCTAssertEqual(response.offset, 0)
        XCTAssertEqual(response.messages.map(\.senderRole), [.scout, .club, .player])
        XCTAssertEqual(response.messages.first?.senderDisplayName, "Alex Morgan")
        XCTAssertEqual(
            response.messages.last?.contactRequestId,
            "01010101-1111-4111-8111-010101010101"
        )
        XCTAssertEqual(response.contactRequest.status, .accepted)
        XCTAssertEqual(response.contactRequest.participants.club?.displayName, "On Platform FC")
        XCTAssertTrue(response.contactRequest.messagingOpen)
        XCTAssertEqual(response.contactRequest.latestOutcome?.stage, .contacted)
    }

    func testClubMessageRenderingUsesProgramNameForBothParticipantViews() throws {
        let response: ContactMessagesResponse = try decodeFixture("contact_messages")
        let clubMessage = try XCTUnwrap(response.messages.first { $0.senderRole == .club })
        let programName = response.contactRequest.participants.club?.displayName

        let scoutRendering = ContactMessageRenderingModel(
            message: clubMessage,
            viewerRole: .scout,
            clubDisplayName: programName
        )
        let playerRendering = ContactMessageRenderingModel(
            message: clubMessage,
            viewerRole: .player,
            clubDisplayName: programName
        )

        XCTAssertEqual(scoutRendering.kind, .club)
        XCTAssertEqual(playerRendering.kind, .club)
        XCTAssertEqual(scoutRendering.displayLabel, "On Platform FC")
        XCTAssertEqual(playerRendering.displayLabel, "On Platform FC")
        XCTAssertNotEqual(scoutRendering.displayLabel, clubMessage.senderDisplayName)
    }

    func testLegacyContactRequestDefaultsToDirectRouting() throws {
        let payload = #"""
        {
          "id": "legacy-request",
          "player_api_id": 700001,
          "message": "Legacy request",
          "status": "accepted",
          "created_at": "2026-07-01T10:00:00",
          "responded_at": "2026-07-01T11:00:00",
          "expires_at": "2026-07-15T10:00:00",
          "participants": {
            "scout": {"display_name": "Scout"},
            "player": {"display_name": "Player"}
          },
          "latest_outcome": null
        }
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let request = try decoder.decode(ContactRequest.self, from: Data(payload.utf8))

        XCTAssertEqual(request.routingMode, .direct)
        XCTAssertFalse(request.permissionAttestation)
        XCTAssertTrue(request.messagingOpen)
        XCTAssertNil(request.participants.club)
    }

    func testDecodesOutcomeAndRefreshedContactRequestEnvelope() throws {
        let response: ContactOutcomeResponse = try decodeFixture("contact_outcome")

        XCTAssertEqual(response.outcome.stage, .signed)
        XCTAssertEqual(response.outcome.notes, "Scholarship agreement completed.")
        XCTAssertEqual(response.outcome.occurredAt, "2026-07-17T12:00:00")
        XCTAssertEqual(response.contactRequest.latestOutcome, response.outcome)
    }

    func testDecodesIdentityFreeInterestSignalsIncludingZeroPlayer() throws {
        let response: InterestSignalsResponse = try decodeFixture("interest_signals")

        XCTAssertEqual(response.weekStart, "2026-07-13T00:00:00+00:00")
        XCTAssertEqual(response.interestSignals.map(\.playerApiId), [7_001, 7_002])
        XCTAssertEqual(response.interestSignals[0].watchlists, .init(total: 2, addedThisWeek: 1))
        XCTAssertEqual(response.interestSignals[0].follows, .init(total: 3, addedThisWeek: 1))
        XCTAssertEqual(response.interestSignals[1], .zero(playerID: 7_002))
    }

    func testDecodesReporterFacingContentReportSerializer() throws {
        let response: ContentReportResponse = try decodeFixture("content_report")

        XCTAssertEqual(response.report.id, 41)
        XCTAssertEqual(response.report.subjectType, .contactMessage)
        XCTAssertEqual(response.report.reasonCode, "participant_safety")
        XCTAssertEqual(response.report.status, .open)
        XCTAssertEqual(response.report.details, "Please review this message.")
        XCTAssertNil(response.report.resolutionNotes)
        XCTAssertNil(response.report.resolvedAt)
    }

    func testRequestReportSubjectsUseOtherAndStatusAwareBlockGuidance() throws {
        let response: ContactRequestsResponse = try decodeFixture("contact_requests_inbox")
        let request = try XCTUnwrap(response.requests.first)

        let pending = ContentReportSubject.request(request)
        XCTAssertEqual(pending.subjectType, .other)
        XCTAssertEqual(pending.subjectID, request.id)
        XCTAssertTrue(pending.explanation.contains("decline the request separately"))
        XCTAssertTrue(pending.explanation.contains("cooldown window"))

        let accepted = ContentReportSubject.request(request.replacing(status: .accepted))
        XCTAssertTrue(accepted.explanation.contains("accepted introduction can no longer be declined"))
        XCTAssertFalse(accepted.explanation.contains("decline the request separately"))

        let declined = ContentReportSubject.request(request.replacing(status: .declined))
        XCTAssertTrue(declined.explanation.contains("already closed as declined"))

        let withdrawn = ContentReportSubject.request(request.replacing(status: .withdrawn))
        XCTAssertTrue(withdrawn.explanation.contains("was withdrawn"))

        let expired = ContentReportSubject.request(request.replacing(status: .expired))
        XCTAssertTrue(expired.explanation.contains("expired"))
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
            CreateContactRequestBody(
                playerApiId: 403_064,
                message: "Could we speak?",
                permissionAttestation: true
            )
        )
        XCTAssertEqual(introduction["player_api_id"] as? Int, 403_064)
        XCTAssertEqual(introduction["message"] as? String, "Could we speak?")
        XCTAssertEqual(introduction["permission_attestation"] as? Bool, true)

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

        let messageReport = try encodeObject(
            SubmitContentReportBody(
                subjectType: .contactMessage,
                subjectId: "11111111-aaaa-4111-8111-111111111111",
                reasonCode: "participant_safety",
                details: "Please review this message."
            )
        )
        XCTAssertEqual(messageReport["subject_type"] as? String, "contact_message")
        XCTAssertEqual(
            messageReport["subject_id"] as? String,
            "11111111-aaaa-4111-8111-111111111111"
        )
        XCTAssertEqual(messageReport["reason_code"] as? String, "participant_safety")

        let requestReport = try encodeObject(
            SubmitContentReportBody(
                subjectType: .other,
                subjectId: "02020202-2222-4222-8222-020202020202",
                reasonCode: "spam",
                details: nil
            )
        )
        XCTAssertEqual(requestReport["subject_type"] as? String, "other")
        XCTAssertNil(requestReport["details"])
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
