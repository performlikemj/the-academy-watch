import Foundation

struct GolSSEEvent: Equatable, Sendable {
    let type: String
    let data: String
    var json: GolJSON? { try? JSONDecoder().decode(GolJSON.self, from: Data(data.utf8)) }
}

/// Parses bytes, preserving UTF-8 across chunks and CR, LF, or split CRLF boundaries.
/// Only a blank line commits a frame; an unterminated frame at EOF is discarded.
struct GolSSEParser {
    private var line: [UInt8] = []
    private var type = ""
    private var data: [String] = []
    private var skipLF = false
    private var frameBytes = 0

    mutating func push(_ byte: UInt8) throws -> GolSSEEvent? {
        if skipLF {
            skipLF = false
            if byte == 10 { return nil }
        }
        frameBytes += 1
        guard frameBytes <= 2_000_000 else { throw GolFailure.interrupted }
        guard byte == 10 || byte == 13 else {
            line.append(byte)
            return nil
        }
        skipLF = byte == 13
        let text = String(decoding: line, as: UTF8.self)
        line.removeAll(keepingCapacity: true)
        if text.isEmpty {
            let event =
                data.isEmpty
                ? nil : GolSSEEvent(type: type.isEmpty ? "message" : type, data: data.joined(separator: "\n"))
            type = ""
            data = []
            frameBytes = 0
            return event
        }
        guard !text.hasPrefix(":") else { return nil }
        let parts = text.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        var value = parts.count == 2 ? String(parts[1]) : ""
        if value.hasPrefix(" ") { value.removeFirst() }
        if parts[0] == "event" { type = value }
        if parts[0] == "data" { data.append(value) }
        return nil
    }

    mutating func push(_ chunk: Data) throws -> [GolSSEEvent] {
        try chunk.compactMap { try push($0) }
    }
}
