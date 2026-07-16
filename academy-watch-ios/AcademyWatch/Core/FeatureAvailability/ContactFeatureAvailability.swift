import Combine
import Foundation

enum ContactFeatureAvailabilityState: Equatable, Sendable {
    case unknown
    case available
    case unavailable
}

/// App-wide knowledge of whether the server has enabled the contact rail.
///
/// The backend deliberately responds with 404 for every `/api/contact/*`
/// endpoint while the feature flag is off. Keeping that observation in one
/// shared object prevents individual screens from leaving behind dead entry
/// points after any contact request discovers the disabled rail.
@MainActor
final class ContactFeatureAvailability: ObservableObject {
    static let shared = ContactFeatureAvailability()

    @Published private(set) var state: ContactFeatureAvailabilityState

    init(state: ContactFeatureAvailabilityState = .unknown) {
        self.state = state
    }

    var isUnavailable: Bool {
        state == .unavailable
    }

    func recordSuccess() {
        // Once any route has disclosed the server-side flag as off, keep the
        // rail hidden. An older in-flight success must not win that race.
        guard state != .unavailable else { return }
        state = .available
    }

    @discardableResult
    func recordFailure(_ error: Error) -> Bool {
        guard (error as? APIClientError)?.statusCode == 404 else { return false }
        state = .unavailable
        return true
    }

    func reset() {
        state = .unknown
    }
}
