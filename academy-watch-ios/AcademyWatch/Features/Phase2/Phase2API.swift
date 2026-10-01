import Foundation

protocol Phase2API: Sendable {
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws -> Data
}
extension Phase2API {
    func read<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try decode(await phase2Data(path: path, method: "GET", query: query, body: nil))
    }
    func write<T: Decodable, Body: Encodable>(_ path: String, method: String = "POST", body: Body) async throws -> T {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return try decode(await phase2Data(path: path, method: method, query: [], body: encoder.encode(body)))
    }
    private func decode<T: Decodable>(_ data: Data) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do { return try decoder.decode(T.self, from: data) } catch { throw APIClientError.decoding(error) }
    }
}
func phase2Status(_ error: Error) -> Int? {
    switch error {
    case APIClientError.httpStatus(let code): return code
    case APIClientError.server(let code, _): return code
    case APIClientError.codedServer(let code, _, _, _): return code
    default: return nil
    }
}
func phase2Error(_ error: Error) -> String {
    let code: String
    switch error {
    case APIClientError.server(_, let message): code = message
    case APIClientError.codedServer(_, _, let value, _): code = value
    default: code = ""
    }
    switch code {
    case "version_conflict": return "This application changed. Refresh before trying again. Your draft is still here."
    case "trial_full": return "The trial is full. Nothing was sent; your draft is still here."
    case "confirmed_completed_trial_required":
        return "The player must confirm and the trial must have passed before recording attendance."
    case "already_applied", "duplicate_application":
        return "You have already applied. Check My applications. Nothing new was sent."
    case "outside_age_band", "age_ineligible", "adult_self_claim_required", "approved_adult_self_claim_required",
        "ineligible_claim":
        return "An approved adult self-profile within the age band is required. Nothing was sent."
    case "opportunity_closed": return "This opportunity has closed. Nothing was sent."
    default:
        if phase2Status(error) == 400 {
            return "Check the details and try again. Nothing was sent; your draft is still here."
        }
        if phase2Status(error) == 401 { return "Sign in again from Account to continue." }
        if phase2Status(error) == 403 {
            return "You no longer have access, or your profile is not eligible. Nothing was sent."
        }
        if phase2Status(error) == 404 { return "This feature or record is no longer available." }
        if phase2Status(error) == 409 {
            return "The record changed or the action is unavailable. Refresh and try again. Nothing was sent."
        }
        return "Could not connect. Please try again. Your draft is still here."
    }
}
