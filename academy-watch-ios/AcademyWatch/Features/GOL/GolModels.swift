import Foundation

/// Lossless JSON keeps assistant tool_calls and tool_call_id entries intact.
indirect enum GolJSON: Codable, Equatable, Sendable {
    case object([String: GolJSON])
    case array([GolJSON])
    case string(String)
    case number(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() {
            self = .null
        } else if let v = try? c.decode(Bool.self) {
            self = .bool(v)
        } else if let v = try? c.decode(String.self) {
            self = .string(v)
        } else if let v = try? c.decode(Double.self) {
            self = .number(v)
        } else if let v = try? c.decode([String: GolJSON].self) {
            self = .object(v)
        } else {
            self = .array(try c.decode([GolJSON].self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .object(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .null: try c.encodeNil()
        }
    }

    subscript(_ key: String) -> GolJSON {
        if case .object(let v) = self { return v[key] ?? .null }
        return .null
    }
    var string: String? {
        if case .string(let v) = self { return v }
        return nil
    }
    var array: [GolJSON] {
        if case .array(let v) = self { return v }
        return []
    }
    var integer: Int? {
        if case .number(let v) = self, v >= 0, v < Double(Int.max), v.rounded() == v { return Int(v) }
        return nil
    }

    /// Bounded plain text, deliberately never interpreted as links or HTML.
    func summary(depth: Int = 0) -> String {
        guard depth < 4 else { return "…" }
        switch self {
        case .object(let v):
            return v.keys.sorted().prefix(12).map {
                "\($0.replacingOccurrences(of: "_", with: " ").capitalized): \(v[$0]!.summary(depth: depth + 1))"
            }.joined(separator: "\n")
        case .array(let v): return v.prefix(8).map { $0.summary(depth: depth + 1) }.joined(separator: "\n\n")
        case .string(let v): return String(v.prefix(2000))
        case .number(let v): return v.formatted()
        case .bool(let v): return v ? "Yes" : "No"
        case .null: return "—"
        }
    }
}

/// Maps tabular analytics to labelled fields, including chart results, without exposing transport metadata.
struct GolCardSummary {
    let card: GolJSON

    var text: String {
        let payload = card["payload"]
        guard card["type"].string == "analysis_result" else { return payload.summary() }
        if payload["result_type"].string == "error" { return "No data available." }
        let columns = payload["columns"].array.compactMap(\.string)
        let rows = payload["rows"].array
        if !columns.isEmpty {
            guard !rows.isEmpty else { return "No data found." }
            var result = rows.prefix(8).map { row in
                columns.prefix(12).enumerated().map { index, column in
                    let value: GolJSON
                    if case .array(let cells) = row {
                        value = cells.indices.contains(index) ? cells[index] : .null
                    } else {
                        value = row[column]
                    }
                    return
                        "\(column.replacingOccurrences(of: "_", with: " ").capitalized): \(value.summary())"
                }.joined(separator: "\n")
            }.joined(separator: "\n\n")
            if rows.count > 8 || payload["truncated"] == .bool(true) {
                result += "\n\nShowing the first \(min(rows.count, 8)) results."
            }
            return result
        }
        for key in ["value", "items", "data"] where payload[key] != .null {
            return payload[key].summary()
        }
        return payload.summary()
    }
}

struct GolMessage: Identifiable, Equatable {
    let id = UUID()
    let role: String
    var content = ""
    var cards: [GolJSON] = []
    var hiddenHistory: [GolJSON] = []
    var cutShort = false
}

struct GolQuestion: Codable, Equatable, Sendable {
    let message: String
    let clientMsgID: String
    let history: [GolJSON]
    let sessionID: String

    enum CodingKeys: String, CodingKey {
        case message, history
        case clientMsgID = "client_msg_id"
        case sessionID = "session_id"
    }

    init(message: String, messages: [GolMessage], sessionID: String) {
        self.message = message
        self.clientMsgID = UUID().uuidString.replacingOccurrences(of: "-", with: "")
        self.sessionID = sessionID
        self.history = Array(
            messages.flatMap {
                $0.hiddenHistory + ($0.role == "assistant" && $0.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    ? [] : [.object(["role": .string($0.role), "content": .string($0.content)])])
            }.suffix(20))
    }
}

struct GolFailure: Error, Equatable {
    let message: String
    let retryable: Bool
    var blocksQuestions = false
    var removesUnansweredQuestion = false
    var exhausted = false

    static let interrupted = GolFailure(
        message: "The answer was interrupted. Please try again.", retryable: true)
    static let streamError = GolFailure(
        message: "GOL couldn't finish this answer. Please try again.", retryable: true)

    static func http(_ status: Int, code: String?) -> GolFailure {
        switch status {
        case 401:
            return .init(
                message: "Sign in to use GOL.", retryable: false,
                blocksQuestions: true, removesUnansweredQuestion: true)
        case 402:
            return .init(
                message: "You've used all your GOL questions.", retryable: false,
                blocksQuestions: true, removesUnansweredQuestion: true, exhausted: true)
        case 403:
            return .init(
                message: "GOL isn't available on your account.", retryable: false,
                blocksQuestions: true, removesUnansweredQuestion: true)
        case 409 where code == "in_flight":
            return .init(
                message: "Still working on your previous question. Give it a moment and try again.",
                retryable: true)
        case 409 where code == "client_msg_id_reused":
            return .init(message: "Please ask that as a new question.", retryable: false)
        case 409 where code == "recovery_exhausted":
            return .init(
                message: "That question could not be completed; your question allowance was restored.", retryable: false)
        case 400:
            return .init(
                message: "GOL couldn't accept this question. Start a new chat and try again.",
                retryable: false)
        case 429:
            return .init(
                message: "GOL is receiving too many questions. Wait a moment and try again.", retryable: true)
        default: return .init(message: "GOL is temporarily unavailable. Please try again.", retryable: true)
        }
    }
}

/// Inline parsing keeps line breaks and list markers readable while styling emphasis.
enum GolMarkdown {
    static func render(_ source: String) -> AttributedString {
        var rendered = (try? AttributedString(
            markdown: source,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(source)
        // Answer formatting must not introduce external navigation actions.
        rendered.link = nil
        return rendered
    }
}
