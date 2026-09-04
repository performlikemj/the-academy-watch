import Foundation
import XCTest
@testable import AcademyWatch

final class APIClientBaseURLTests: XCTestCase {
    func testLoopbackIPv4BaseURLIsAccepted() throws {
        let url = try XCTUnwrap(URL(string: "http://127.0.0.1:5001/api"))

        XCTAssertEqual(
            APIClient.resolveDefaultBaseURL(arguments: ["AcademyWatch", "-apiBaseURL", url.absoluteString]),
            url
        )
    }

    func testLocalhostBaseURLIsAccepted() throws {
        let url = try XCTUnwrap(URL(string: "http://localhost:5001/api"))

        XCTAssertEqual(
            APIClient.resolveDefaultBaseURL(arguments: ["AcademyWatch", "-apiBaseURL", url.absoluteString]),
            url
        )
    }

    func testHTTPSNonLoopbackBaseURLIsRejected() {
        XCTAssertEqual(
            APIClient.resolveDefaultBaseURL(arguments: ["AcademyWatch", "-apiBaseURL", "https://example.com"]),
            APIClient.productionBaseURL
        )
    }

    func testPrivateNetworkBaseURLIsRejected() {
        XCTAssertEqual(
            APIClient.resolveDefaultBaseURL(arguments: ["AcademyWatch", "-apiBaseURL", "http://10.0.0.5"]),
            APIClient.productionBaseURL
        )
    }

    func testMalformedBaseURLIsRejected() {
        XCTAssertEqual(
            APIClient.resolveDefaultBaseURL(arguments: ["AcademyWatch", "-apiBaseURL", "://not-a-url"]),
            APIClient.productionBaseURL
        )
    }

    func testAbsentBaseURLUsesProduction() {
        XCTAssertEqual(
            APIClient.resolveDefaultBaseURL(arguments: ["AcademyWatch"]),
            APIClient.productionBaseURL
        )
    }
}
