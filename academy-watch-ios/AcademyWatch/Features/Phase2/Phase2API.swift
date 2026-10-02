import Foundation

protocol Phase2API: Sendable {
    func phase2Data(path: String, method: String, query: [URLQueryItem], body: Data?) async throws
        -> Data
}
extension Phase2API {
    func read<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try decode(await phase2Data(path: path, method: "GET", query: query, body: nil))
    }
    func write<T: Decodable, Body: Encodable>(_ path: String, method: String = "POST", body: Body)
        async throws -> T
    {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return try decode(
            await phase2Data(path: path, method: method, query: [], body: encoder.encode(body)))
    }
    private func decode<T: Decodable>(_ data: Data) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do { return try decoder.decode(T.self, from: data) } catch {
            throw APIClientError.decoding(error)
        }
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
    case "invalid_trial_at":
        return
            "Choose a future trial inside this post’s invitation window and within 90 days of this application. Nothing was sent."
    case "invalid_email": return "Enter a valid email address. Nothing was sent."
    case "invalid_position":
        return "Enter a position of no more than 80 characters. Nothing was sent."
    case "contact_consent_required": return "Please agree to share your contact details before applying."
    case "scope_required": return "Choose at least one squad or select All squads."
    case "invalid_scope": return "Choose squads that belong to this club."
    case "separate_enrollment_required":
        return "Confirm that enrollment was completed separately before marking Signed."
    case "already_has_access":
        return "This person already has club access. Edit their access under People."
    case "cannot_change_own_access": return "You cannot change your own access."
    case "invalid_transition":
        return "This application cannot move to that stage. Refresh to see the available actions."
    case "invitation_unavailable", "invite_not_pending":
        return "This invitation is no longer pending. Refresh the invites."
    case "request_conflict":
        return "This request was already used with different details. Refresh before sending again."
    case "grant_version_conflict":
        return "This person’s access changed. Refresh before editing it. Your draft is still here."
    case "version_conflict":
        return "This application changed. Refresh before trying again. Your draft is still here."
    case "trial_full": return "The trial is full. Nothing was sent; your draft is still here."
    case "confirmed_completed_trial_required":
        return "The player must confirm and the trial must have passed before recording attendance."
    case "already_applied", "duplicate_application":
        return "You have already applied. Check My applications. Nothing new was sent."
    case "outside_age_band", "age_ineligible", "adult_self_claim_required",
        "approved_adult_self_claim_required",
        "ineligible_claim":
        return "An approved adult self-profile within the age band is required. Nothing was sent."
    case "opportunity_closed": return "This opportunity has closed. Nothing was sent."
    default:
        if [400, 422].contains(phase2Status(error) ?? 0) {
            return "Check the details and try again. Nothing was sent; your draft is still here."
        }
        if phase2Status(error) == 401 { return "Sign in again from Account to continue." }
        if phase2Status(error) == 403 {
            return "You no longer have access, or your profile is not eligible. Nothing was sent."
        }
        if phase2Status(error) == 404 { return "This feature or record is no longer available." }
        if phase2Status(error) == 409 {
            return
                "The record changed or the action is unavailable. Refresh and try again. Nothing was sent."
        }
        if phase2Status(error) == 429 {
            return "Too many attempts. Wait a moment before trying again. Nothing was sent."
        }
        if phase2Status(error) == 413 {
            return "This request is too large. Shorten the details and try again."
        }
        if error is URLError { return "Could not connect. Please try again. Your draft is still here." }
        return
            "The service could not complete this request. Please try again later. Your draft is still here."
    }
}

func phase2ReadError(_ error: Error) -> String {
    if error is URLError { return "Could not connect. Please try again." }
    if phase2Status(error).map({ $0 >= 500 }) == true {
        return "The service could not load this information. Please try again later."
    }
    return phase2Error(error)
}
