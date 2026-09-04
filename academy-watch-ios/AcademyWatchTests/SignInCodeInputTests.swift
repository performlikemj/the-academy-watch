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

    func testSixtyFiveCharacterCodeIsCappedAtSixtyFour() {
        let code = String(repeating: "x", count: 65)

        XCTAssertEqual(SignInCodeInput.acceptedValue(code), String(repeating: "x", count: 64))
    }

    func testWhitespaceOnlyCodeHasNoSubmissionValue() {
        XCTAssertNil(SignInCodeInput.submissionValue(" \t\n\r "))
    }

    func testSixtyFourCharacterCodeIsUnchanged() {
        let code = String(repeating: "x", count: 64)

        XCTAssertEqual(SignInCodeInput.acceptedValue(code), code)
        XCTAssertEqual(SignInCodeInput.submissionValue(code), code)
    }
}
