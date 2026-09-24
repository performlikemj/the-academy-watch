import Combine
import Foundation

protocol GolAPIClientProtocol: Sendable {
    func golSuggestions() async throws -> [String]
    func streamGol(_ question: GolQuestion, onEvent: @escaping @MainActor @Sendable (GolSSEEvent) -> Void)
        async throws
}

@MainActor
final class GolChatViewModel: ObservableObject {
    @Published private(set) var messages: [GolMessage] = []
    @Published private(set) var suggestions: [String] = []
    @Published private(set) var isStreaming = false
    @Published private(set) var failure: GolFailure?
    @Published private(set) var freeQuestions: Int?
    @Published private(set) var credits: Int?
    @Published private(set) var isUsingTool = false
    private(set) var sessionID = UUID().uuidString
    private(set) var pendingQuestion: GolQuestion?
    private var task: Task<Void, Never>?
    private var generation = UUID()
    private var receivedDone = false
    private var receivedError = false
    private let client: any GolAPIClientProtocol

    var canRetry: Bool { !isStreaming && failure?.retryable == true && pendingQuestion != nil }
    var canSend: Bool { !isStreaming && failure?.blocksQuestions != true }

    init(client: any GolAPIClientProtocol) { self.client = client }
    deinit { task?.cancel() }

    func loadSuggestions() async {
        suggestions =
            (try? await client.golSuggestions()) ?? [
                "Which academy players should I watch?", "Explain academy pathways",
            ]
    }

    func send(_ text: String) {
        let content = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canSend, !content.isEmpty else { return }
        let question = GolQuestion(message: content, messages: messages, sessionID: sessionID)
        messages.append(GolMessage(role: "user", content: content))
        messages.append(GolMessage(role: "assistant"))
        run(question)
    }

    func retry() {
        guard canRetry, let question = pendingQuestion else { return }
        // Replace just the failed answer; the user message and original request stay identical.
        messages[messages.count - 1] = GolMessage(role: "assistant")
        run(question)
    }

    func stop() {
        guard isStreaming else { return }
        generation = UUID()
        task?.cancel()
        task = nil
        isStreaming = false
        isUsingTool = false
        if let last = messages.last, !last.content.isEmpty || !last.cards.isEmpty {
            messages[messages.count - 1].cutShort = true
            failure = nil
            pendingQuestion = nil
        } else {
            failure = .init(message: "Answer stopped.", retryable: true)
        }
    }

    func newChat() {
        stop()
        generation = UUID()
        messages = []
        pendingQuestion = nil
        failure = nil
        sessionID = UUID().uuidString
        // Balances belong to the account, not the conversation.
    }

    func resetAccount() {
        newChat()
        freeQuestions = nil
        credits = nil
        suggestions = []
    }

    private func run(_ question: GolQuestion) {
        let epoch = UUID()
        generation = epoch
        pendingQuestion = question
        failure = nil
        receivedDone = false
        receivedError = false
        isStreaming = true
        task = Task { [weak self, client] in
            do {
                try await client.streamGol(question) { [weak self] event in
                    guard let self, self.generation == epoch else { return }
                    self.receive(event)
                }
                guard let self, self.generation == epoch else { return }
                if !self.receivedDone && !self.receivedError { self.fail(.interrupted) }
            } catch {
                guard let self, self.generation == epoch else { return }
                if !self.receivedDone && !self.receivedError {
                    self.fail(error as? GolFailure ?? .interrupted)
                }
            }
            guard let self, self.generation == epoch else { return }
            self.isStreaming = false
            self.isUsingTool = false
            self.task = nil
        }
    }

    private func fail(_ error: GolFailure) {
        failure = error
        if !error.retryable { pendingQuestion = nil }
        if !messages.isEmpty, !messages[messages.count - 1].content.isEmpty {
            messages[messages.count - 1].cutShort = true
        }
    }

    private func receive(_ event: GolSSEEvent) {
        guard !receivedDone, let data = event.json, case .object = data, !messages.isEmpty else { return }
        let index = messages.count - 1
        switch event.type {
        case "usage":
            freeQuestions = data["free_questions_remaining"].integer ?? freeQuestions
            credits = data["credit_balance"].integer ?? credits
        case "error":
            receivedError = true
            isUsingTool = false
            // Server error prose is intentionally not displayed; use controlled native copy.
            fail(.streamError)
        case "done":
            receivedDone = true
            isUsingTool = false
            if data["partial"] == .bool(true) {
                messages[index].cutShort = true
                pendingQuestion = nil
                failure = nil
            } else if !receivedError {
                pendingQuestion = nil
            }
        default:
            guard !receivedError else { return }
            switch event.type {
            case "token", "message": messages[index].content += data["content"].string ?? ""
            case "replace": messages[index].content = data["content"].string ?? ""
            case "data_card": messages[index].cards.append(data)
            case "history_entries": messages[index].hiddenHistory += data["entries"].array
            case "tool_call": isUsingTool = true
            default: break
            }
        }
    }
}
