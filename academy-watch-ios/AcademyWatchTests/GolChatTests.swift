import SwiftUI
import XCTest

@testable import AcademyWatch

final class GolParserTests: XCTestCase {
    func testEveryPossibleChunkBoundaryWithUnicodeAndCRLF() throws {
        let bytes = Data(": comment\r\nevent: token\r\ndata: {\"content\":\"Gól ⚽\"}\r\n\r\n".utf8)
        for split in 0...bytes.count {
            var parser = GolSSEParser()
            let first = try parser.push(bytes.prefix(split))
            let second = try parser.push(bytes.dropFirst(split))
            XCTAssertEqual(first + second, [GolSSEEvent(type: "token", data: "{\"content\":\"Gól ⚽\"}")])
        }
    }

    func testMultilineDefaultUnknownEventsAndUnterminatedFrame() throws {
        var parser = GolSSEParser()
        let events = try parser.push(
            Data("data: one\ndata: two\n\nevent: future\rdata: {}\r\rdata: unfinished\n".utf8))
        XCTAssertEqual(events, [.init(type: "message", data: "one\ntwo"), .init(type: "future", data: "{}")])
    }

    func testFrameLimit() throws {
        var parser = GolSSEParser()
        XCTAssertThrowsError(try parser.push(Data(repeating: 65, count: 2_000_001)))
    }
}

@MainActor
final class GolChatTests: XCTestCase {
    func testRetryPreservesIDSessionAndHistoryAndReplacesFailedAnswer() async throws {
        let client = GolTestClient(scripts: [
            [.event("token", "{\"content\":\"Half\"}"), .fail],
            [.event("replace", "{\"content\":\"Complete\"}"), .done],
        ])
        let model = GolChatViewModel(client: client)
        model.send("A question")
        await settle(model)
        XCTAssertTrue(model.canRetry)
        let original = try XCTUnwrap(model.pendingQuestion)
        model.retry()
        await settle(model)
        let requests = await client.requests
        XCTAssertEqual(requests, [original, original])
        XCTAssertEqual(model.messages.count, 2)
        XCTAssertEqual(model.messages.last?.content, "Complete")
        XCTAssertFalse(model.canRetry)
        let nextSession = model.sessionID
        model.newChat()
        XCTAssertNotEqual(model.sessionID, nextSession)
        model.send("A question")
        await settle(model)
        let nextID = await client.lastRequestID()
        XCTAssertNotEqual(nextID, original.clientMsgID)
    }

    func testHistoryIncludesToolCallsBeforeVisibleAssistantAndLastTwentyEntries() async throws {
        let hidden =
            "{\"entries\":[{\"role\":\"assistant\",\"content\":null,\"tool_calls\":[{\"id\":\"call-1\",\"type\":\"function\",\"function\":{\"name\":\"search\",\"arguments\":\"{}\"}}]},{\"role\":\"tool\",\"tool_call_id\":\"call-1\",\"content\":\"result\"}]}"
        let client = GolTestClient(scripts: [
            [.event("history_entries", hidden), .event("token", "{\"content\":\"Answer\"}"), .done], [.done],
        ])
        let model = GolChatViewModel(client: client)
        model.send("First")
        await settle(model)
        model.send("Next")
        await settle(model)
        let history = await client.requests.last!.history
        XCTAssertEqual(history.map { $0["role"].string }, ["user", "assistant", "tool", "assistant"])
        XCTAssertEqual(history[1]["tool_calls"].array.first?["id"].string, "call-1")
        XCTAssertEqual(history[2]["tool_call_id"].string, "call-1")
        XCTAssertEqual(history[3]["content"].string, "Answer")
        let many = (0..<25).map { GolMessage(role: "user", content: String($0)) }
        let question = GolQuestion(message: "Next", messages: many, sessionID: "session")
        XCTAssertEqual(question.history.count, 20)
        XCTAssertEqual(question.history.first?["content"].string, "5")
    }

    func testReplacePartialUnknownCardAndUnknownEvent() async {
        let client = GolTestClient(scripts: [
            [
                .event("token", "{\"content\":\"Draft\"}"),
                .event("replace", "{\"content\":\"Revised\"}"),
                .event("token", "{\"content\":\" answer\"}"),
                .event(
                    "data_card",
                    "{\"type\":\"future\",\"payload\":{\"name\":\"Synthetic Player\",\"goals\":2}}"),
                .event("future", "{}"), .event("done", "{\"partial\":true}"),
            ]
        ])
        let model = GolChatViewModel(client: client)
        model.send("Test")
        await settle(model)
        XCTAssertEqual(model.messages.last?.content, "Revised answer")
        XCTAssertEqual(model.messages.last?.cards.count, 1)
        XCTAssertEqual(model.messages.last?.cutShort, true)
        XCTAssertFalse(model.canRetry)
        XCTAssertTrue(model.messages.last!.cards[0]["payload"].summary().contains("Goals: 2"))
    }

    func testErrorThenRefundUsageIgnoresLaterText() async {
        let client = GolTestClient(scripts: [
            [
                .event("error", "{\"message\":\"untrusted server text\"}"),
                .event("usage", "{\"free_questions_remaining\":3,\"credit_balance\":2,\"refunded\":true}"),
                .event("token", "{\"content\":\"ignore\"}"),
            ]
        ])
        let model = GolChatViewModel(client: client)
        model.send("Test")
        await settle(model)
        XCTAssertEqual(model.freeQuestions, 3)
        XCTAssertEqual(model.credits, 2)
        XCTAssertEqual(model.messages.last?.content, "")
        XCTAssertEqual(model.failure, .streamError)
        XCTAssertTrue(model.canRetry)
    }

    func testEOFWithoutDoneIsRetryable() async {
        let client = GolTestClient(scripts: [[.event("usage", "{}")]])
        let model = GolChatViewModel(client: client)
        model.send("Test")
        await settle(model)
        XCTAssertEqual(model.failure, .interrupted)
        XCTAssertTrue(model.canRetry)
    }

    func testStopAndNewChatDiscardLateEvents() async {
        let client = GolTestClient(scripts: [
            [
                .event("token", "{\"content\":\"Started\"}"), .delay,
                .event("token", "{\"content\":\"Late\"}"), .done,
            ]
        ])
        let model = GolChatViewModel(client: client)
        model.send("Test")
        for _ in 0..<100 where model.messages.last?.content.isEmpty == true {
            try? await Task.sleep(for: .milliseconds(5))
        }
        model.stop()
        XCTAssertEqual(model.messages.last?.cutShort, true)
        XCTAssertFalse(model.canRetry)
        model.newChat()
        try? await Task.sleep(for: .milliseconds(150))
        XCTAssertTrue(model.messages.isEmpty)
        XCTAssertFalse(model.isStreaming)
    }

    func testCardsMapTableColumnsToValuesAndHandleRaggedRows() throws {
        let card = try JSONDecoder().decode(
            GolJSON.self,
            from: Data(
                #"{"type":"analysis_result","payload":{"columns":["player_name","goals"],"rows":[["Test Player",3],["Unknown"]],"display":"bar_chart","result_type":"table"}}"#
                    .utf8))
        let text = GolCardSummary(card: card).text
        XCTAssertEqual(text, "Player Name: Test Player\nGoals: 3\n\nPlayer Name: Unknown\nGoals: —")
        XCTAssertFalse(text.contains("bar_chart"))
    }

    func testStopBeforeAnswerRetainsIDAndAccountResetClearsUsage() async throws {
        let client = GolTestClient(scripts: [
            [
                .event("usage", "{\"free_questions_remaining\":1,\"credit_balance\":4}"), .delay, .done,
            ]
        ])
        let model = GolChatViewModel(client: client)
        model.send("Test")
        for _ in 0..<100 where model.freeQuestions == nil { try? await Task.sleep(for: .milliseconds(2)) }
        let id = model.pendingQuestion?.clientMsgID
        model.stop()
        XCTAssertTrue(model.canRetry)
        XCTAssertEqual(model.pendingQuestion?.clientMsgID, id)
        model.resetAccount()
        XCTAssertNil(model.freeQuestions)
        XCTAssertNil(model.credits)
        XCTAssertNil(model.pendingQuestion)
        XCTAssertTrue(model.messages.isEmpty)
    }

    func testHTTPFailures() async {
        let cases: [(Int, String, Bool, Bool)] = [
            (401, "unauthorized", false, true), (402, "credits_exhausted", false, true), (403, "scout_pro_required", false, true),
            (409, "in_flight", true, false), (409, "client_msg_id_reused", false, false),
            (409, "recovery_exhausted", false, false), (429, "", true, false), (503, "", true, false),
        ]
        for (status, code, retry, blocked) in cases {
            let expected = GolFailure.http(status, code: code)
            let model = GolChatViewModel(client: GolTestClient(scripts: [[.http(status, code)]]))
            model.send("Question")
            await settle(model)
            XCTAssertEqual(model.failure, expected)
            XCTAssertEqual(model.canRetry, retry)
            XCTAssertEqual(model.canSend, !blocked)
        }
        XCTAssertEqual(GolFailure.http(402, code: nil).message, "You've used all your GOL questions.")
        XCTAssertEqual(GolFailure.http(403, code: nil).message, "GOL isn't available on your account.")
    }

    func testRequestEncodingAndNoPurchaseSurface() throws {
        let question = GolQuestion(message: "Question", messages: [], sessionID: "session")
        let request = try APIClient.golRequest(
            baseURL: URL(string: "http://localhost:5011/api")!, token: "test-token", question: question)
        XCTAssertEqual(request.url?.path, "/api/gol/chat")
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.timeoutInterval, 300)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "text/event-stream")
        XCTAssertEqual(try JSONDecoder().decode(GolQuestion.self, from: request.httpBody!), question)
        XCTAssertNotNil(question.clientMsgID.range(of: "^[A-Za-z0-9_-]{8,64}$", options: .regularExpression))
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let feature = root.appendingPathComponent("AcademyWatch/Features/GOL")
        let sources = try FileManager.default.contentsOfDirectory(
            at: feature, includingPropertiesForKeys: nil
        )
        .filter { $0.pathExtension == "swift" }.map { try String(contentsOf: $0) }.joined(separator: "\n")
        // Scan string literals, allowing only the wire key (never displayed).
        let literals = try NSRegularExpression(pattern: #""(?:\\.|[^"\\])*""#)
        let range = NSRange(sources.startIndex..., in: sources)
        for match in literals.matches(in: sources, range: range) {
            let literal = (sources as NSString).substring(with: match.range)
            if literal == "\"credit_balance\"" { continue }
            for forbidden in ["credit", "buy", "purchase", "price", "top up", "billing", "subscribe"] {
                XCTAssertFalse(literal.localizedCaseInsensitiveContains(forbidden), literal)
            }
        }
        for forbidden in [
            "/account/billing", "top_up_path", "top up", "buy credits", "purchase", "openURL", "Link(",
        ] {
            XCTAssertFalse(sources.localizedCaseInsensitiveContains(forbidden), forbidden)
        }
    }

    func testStopRetainsPartialAnswerAndAccountResetClearsIt() async {
        let client = GolTestClient(scripts: [[
            .event("token", "{\"content\":\"Retained answer\"}"), .delay, .done,
        ]])
        let model = GolChatViewModel(client: client)
        model.send("Keep this question")
        for _ in 0..<100 where model.messages.last?.content.isEmpty == true {
            try? await Task.sleep(for: .milliseconds(2))
        }
        let session = model.sessionID
        model.stop()
        XCTAssertEqual(model.messages.last?.content, "Retained answer")
        XCTAssertEqual(model.sessionID, session)
        XCTAssertEqual(model.messages.last?.cutShort, true)
        model.resetAccount()
        XCTAssertTrue(model.messages.isEmpty)
        XCTAssertNotEqual(model.sessionID, session)
        try? await Task.sleep(for: .milliseconds(150))
        XCTAssertTrue(model.messages.isEmpty)
    }

    func testModelCompletesDelayedStream() async {
        let model = GolChatViewModel(client: GolTestClient(scripts: [[.delay, .event("token", "{\"content\":\"Finished\"}"), .done]]))
        model.send("Question")
        await settle(model)
        XCTAssertEqual(model.messages.last?.content, "Finished")
        XCTAssertEqual(model.messages.last?.cutShort, false)
    }

    func testRejectedQuestionRemovesOnlyOrphanPairAndKeepsNeutralFailure() async {
        for status in [401, 402, 403] {
            let model = GolChatViewModel(client: GolTestClient(scripts: [
                [.event("token", "{\"content\":\"Earlier answer\"}"), .done], [.http(status, "")],
            ]))
            model.send("Earlier question")
            await settle(model)
            let previous = model.messages
            model.send("Rejected question")
            await settle(model)
            XCTAssertEqual(model.messages, previous)
            XCTAssertEqual(model.failure, .http(status, code: ""))
            XCTAssertNil(model.pendingQuestion)
            if status == 402 { XCTAssertEqual(model.questionsLeft, 0) }
        }
    }

    func testHistoryOmitsEmptyVisibleAssistantButPreservesHiddenToolEntries() {
        let tool: GolJSON = .object(["role": .string("assistant"), "tool_calls": .array([])])
        let messages = [GolMessage(role: "user", content: "Question"),
                        GolMessage(role: "assistant", hiddenHistory: [tool]),
                        GolMessage(role: "assistant", content: " \n")]
        XCTAssertEqual(GolQuestion(message: "Next", messages: messages, sessionID: "s").history,
                       [.object(["role": .string("user"), "content": .string("Question")]), tool])
    }

    func testQuotaCombinesBothAllowancesAndResetClearsIt() async {
        for (payload, total) in [("{\"free_questions_remaining\":3,\"credit_balance\":7}", 10),
                                 ("{\"credit_balance\":4}", 4),
                                 ("{\"free_questions_remaining\":0,\"credit_balance\":0}", 0)] {
            let model = GolChatViewModel(client: GolTestClient(scripts: [[.event("usage", payload), .done]]))
            XCTAssertNil(model.questionsLeft)
            model.send("Question")
            await settle(model)
            XCTAssertEqual(model.questionsLeft, total)
            model.resetAccount()
            XCTAssertNil(model.questionsLeft)
        }
    }

    func testMarkdownPreservesListsAndLineBreaksAndStylesEmphasis() {
        let rendered = GolMarkdown.render("**Progress**\n\n- Watch minutes.\n- Track *development*.")
        XCTAssertEqual(String(rendered.characters), "Progress\n\n- Watch minutes.\n- Track development.")
        XCTAssertTrue(rendered.runs.contains { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true })
        XCTAssertTrue(rendered.runs.contains { $0.inlinePresentationIntent?.contains(.emphasized) == true })
        XCTAssertEqual(String(GolMarkdown.render("unfinished **text").characters), "unfinished **text")
        let linked = GolMarkdown.render("[Reference](https://example.test/account/billing)")
        XCTAssertEqual(String(linked.characters), "Reference")
        XCTAssertTrue(linked.runs.allSatisfy { $0.link == nil })
    }

    private func settle(_ model: GolChatViewModel) async {
        for _ in 0..<200 {
            if !model.isStreaming { return }
            try? await Task.sleep(for: .milliseconds(5))
        }
        XCTFail("Stream did not finish")
    }
}

private actor GolTestClient: GolAPIClientProtocol {
    enum Action: Sendable {
        case event(String, String)
        case done, fail, delay
        case http(Int, String)
    }
    var scripts: [[Action]]
    var requests: [GolQuestion] = []
    init(scripts: [[Action]]) { self.scripts = scripts }
    func golSuggestions() async throws -> [String] { ["Test suggestion"] }
    func lastRequestID() -> String? { requests.last?.clientMsgID }
    func streamGol(_ question: GolQuestion, onEvent: @escaping @MainActor @Sendable (GolSSEEvent) -> Void)
        async throws
    {
        requests.append(question)
        let actions = scripts.isEmpty ? [.done] : scripts.removeFirst()
        for action in actions {
            switch action {
            case .event(let type, let data): await onEvent(.init(type: type, data: data))
            case .done: await onEvent(.init(type: "done", data: "{}"))
            case .fail: throw URLError(.networkConnectionLost)
            case .delay: try? await Task.sleep(for: .milliseconds(100))  // Deliberately deliver after cancellation.
            case .http(let status, let code): throw GolFailure.http(status, code: code)
            }
        }
    }
}
