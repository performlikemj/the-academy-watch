import Foundation

/// Every real transport uses this policy, including startup and streaming.
struct APIEndpointPolicy {
    static let production = URL(string: "https://api.theacademywatch.com/api")!
    static let staging = URL(string: "https://basecamp.tail37b60.ts.net:15443/api")!
    static let offline = URL(string: "http://offline.invalid/api")!

    struct Context {
        let debug: Bool
        let simulator: Bool
        let testHost: Bool
        var permitsProduction: Bool { !debug && !simulator && !testHost }
        static var current: Context {
            #if DEBUG
            let debug = true
            #else
            let debug = false
            #endif
            #if targetEnvironment(simulator)
            let simulator = true
            #else
            let simulator = false
            #endif
            return Context(debug: debug, simulator: simulator,
                           testHost: ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
                            || NSClassFromString("XCTestCase") != nil)
        }
    }

    struct ConfigurationError: LocalizedError {
        var errorDescription: String? {
            "Developer API configuration error: use an offline fixture, HTTP(S) loopback /api, or https://basecamp.tail37b60.ts.net:15443/api. Production requires a Release device build."
        }
    }

    static func resolve(override: String?, context: Context, offlineFixture: Bool) throws -> URL {
        // An invalid explicit override is never masked by a fixture or a default.
        if let override {
            guard let url = URL(string: override) else { throw ConfigurationError() }
            try validate(url, context: context)
            return url
        }
        if offlineFixture && context.debug && context.simulator { return offline }
        guard context.permitsProduction else { throw ConfigurationError() }
        return production
    }

    static func validate(_ url: URL, context: Context, stubTransport: Bool = false,
                         offlineFixture: Bool = false) throws {
        guard url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path == "/api" else { throw ConfigurationError() }
        if url == staging { return }
        if ["http", "https"].contains(url.scheme ?? ""), ["localhost", "127.0.0.1", "[::1]", "::1"].contains(url.host ?? "") { return }
        if url == production && context.permitsProduction { return }
        if url == offline && offlineFixture && context.debug && context.simulator { return }
        // Unit tests may use reserved .test names with an injected URLProtocol.
        // Production is refused even with a stub; ordinary sessions cannot use this escape.
        if context.testHost && stubTransport && url.host?.hasSuffix(".test") == true,
           ["http", "https"].contains(url.scheme ?? "") { return }
        throw ConfigurationError()
    }
}

/// Refuse redirects outside the configured origin. Redirects must not bypass the base policy.
final class APIOriginRedirectGuard: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        guard let original = task.originalRequest?.url, let target = request.url,
              original.scheme == target.scheme, original.host == target.host,
              original.port == target.port else { completionHandler(nil); return }
        completionHandler(request)
    }
}
