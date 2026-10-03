#if DEBUG && targetEnvironment(simulator)
import Foundation

/// Offline review states for the player card (`-floodlightPreview pc-<state>`).
///
/// The match lines in `player_card_states.json` are the server's own merge
/// output for the raw entries in `sim/build-player-card-fixtures.py`; nothing
/// here opens a socket. Every person and club is fictional.
enum PlayerCardReviewFixtures {
    static let playerID = 900_001
    static let deskStates = ["desk", "desk-next"]

    /// `pc-photo` -> `photo`; nil when the launch is not a player-card review.
    static var state: String? {
        guard let screen = FloodlightPreview.screen, screen.hasPrefix("pc-") else { return nil }
        return String(screen.dropFirst(3))
    }

    static var isDesk: Bool { state.map(deskStates.contains) ?? false }

    /// `-pcAnchor facts|season|matches|end|results`: where a review launch scrolls to.
    static var anchor: String? { argument(after: "-pcAnchor") }

    /// `-pcFailOnce`: a failing read fails only the first time, so "Try again" recovers.
    static var failsOnce: Bool { ProcessInfo.processInfo.arguments.contains("-pcFailOnce") }

    private static func argument(after flag: String) -> String? {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: flag), arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }

    private static let lock = NSLock()
    nonisolated(unsafe) private static var failures: [String: Int] = [:]

    private static let root: [String: Any] = {
        guard let data = try? FloodlightPreview.fixture("player_card_states"),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { preconditionFailure("Invalid player-card review fixture") }
        return object
    }()

    /// The fixture answer for a request, or nil to fall through to the shared review fixtures.
    static func data(for request: URLRequest, state: String) throws -> Data? {
        let path = request.url?.path ?? ""
        if deskStates.contains(state) {
            guard path.hasSuffix("/scout/players"), let payload = root[state] else { return nil }
            return try encode(payload)
        }
        guard let states = root["states"] as? [String: Any], let entry = states[state] as? [String: Any] else {
            throw ExperienceFixtureError.unmatchedRequest(method: "GET", path: path)
        }
        let prefix = "/api/players/\(playerID)/"
        guard path.hasPrefix(prefix) else { return nil }
        let resource = String(path.dropFirst(prefix.count))
        if (entry["fail"] as? [String])?.contains(resource) == true, shouldFail(resource) {
            throw APIClientError.server(statusCode: 503, message: "Synthetic review error. Please try again.")
        }
        guard let payload = entry[resource] else { return nil }
        return try encode(payload)
    }

    private static func shouldFail(_ resource: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        failures[resource, default: 0] += 1
        return !failsOnce || failures[resource] == 1
    }

    /// Photo tokens become bundled file URLs: review images never come from a network.
    private static func encode(_ payload: Any) throws -> Data {
        var text = String(decoding: try JSONSerialization.data(withJSONObject: payload), as: UTF8.self)
        for name in ["portrait", "second", "third", "white", "face"] {
            let url = Bundle.main.url(forResource: "pc-photo-\(name)", withExtension: "png")?.absoluteString ?? ""
            text = text.replacingOccurrences(
                of: "__PC_PHOTO_\(name)__",
                with: url.replacingOccurrences(of: "/", with: "\\/")
            )
        }
        return Data(text.utf8)
    }
}
#endif
