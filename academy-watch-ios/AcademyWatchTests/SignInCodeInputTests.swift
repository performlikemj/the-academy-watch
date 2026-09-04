import XCTest
@testable import AcademyWatch

final class SignInCodeInputTests: XCTestCase {
    func testTwentyCharacterCodeIsAcceptedAndSubmittedIntact() throws {
        let code = String(repeating: "x", count: 20)

        let acceptedCode = SignInCodeInput.acceptedValue(code)
        let submittedCode = try XCTUnwrap(SignInCodeInput.submissionValue(acceptedCode))

        XCTAssertEqual(acceptedCode, code)
        XCTAssertEqual(submittedCode, code)
    }
}
