import ImageIO
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class ProfileEditorViewModel: ObservableObject {
    @Published var bio = ""
    @Published var positions = ""
    @Published var preferredFoot = ""
    @Published var height = ""
    @Published var highlightURL = ""
    @Published var highlightTitle = ""
    @Published private(set) var showcase: OwnerShowcase?
    @Published private(set) var busy = false
    @Published private(set) var error: String?
    @Published private(set) var notice: String?
    @Published private(set) var loaded = false
    let playerID: Int
    private let client: any PlayerClubAPIClientProtocol
    init(playerID: Int, client: any PlayerClubAPIClientProtocol) {
        self.playerID = playerID
        self.client = client
    }
    func load() async {
        guard !busy else { return }
        busy = true
        error = nil
        defer { busy = false }
        do {
            let value = try await client.fetchOwnerShowcase(playerID: playerID)
            guard !Task.isCancelled else { return }
            showcase = value
            bio = value.profile?.bio ?? ""
            positions = value.profile?.positions ?? ""
            preferredFoot = value.profile?.preferredFoot ?? ""
            height = value.profile?.heightCm.map(String.init) ?? ""
            loaded = true
        } catch {
            loaded = false
            showcase = nil
            self.error = playerClubError(error)
        }
    }
    func refreshMedia() async {
        do {
            let value = try await client.fetchOwnerShowcase(playerID: playerID)
            guard !Task.isCancelled else { return }
            showcase = value
        } catch {
            self.error = "Saved, but the latest media list couldn't be loaded. Reopen this editor to refresh it."
        }
    }
    func save() async {
        guard loaded, !busy else { return }
        notice = nil
        let cleanHeight = height.trimmingCharacters(in: .whitespacesAndNewlines)
        guard bio.count <= 2_000, positions.count <= 100 else {
            error = "Use up to 2,000 characters for your bio and 100 for positions."
            return
        }
        guard cleanHeight.isEmpty || Int(cleanHeight).map({ (100...260).contains($0) }) == true else {
            error = "Enter a height between 100 and 260 cm, or leave it blank."
            return
        }
        busy = true
        error = nil
        defer { busy = false }
        do {
            try await client.saveBasicProfile(
                playerID: playerID,
                update: BasicProfileUpdate(
                    bio: bio, positions: positions, preferredFoot: preferredFoot.isEmpty ? nil : preferredFoot,
                    heightCm: Int(cleanHeight)))
            notice = "Profile saved. Changes appear publicly when approved."
        } catch { self.error = playerClubError(error) }
    }
    func addHighlight() async {
        guard loaded, !busy else { return }
        notice = nil
        let url = highlightURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsed = URL(string: url), parsed.scheme == "https",
            ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].contains(parsed.host?.lowercased() ?? ""),
            parsed.user == nil, parsed.password == nil, url.count <= 2_000, highlightTitle.count <= 200
        else {
            error = "Add an HTTPS YouTube link and a title of up to 200 characters."
            return
        }
        busy = true
        error = nil
        defer { busy = false }
        do {
            try await client.addHighlight(playerID: playerID, url: url, title: highlightTitle)
            highlightURL = ""
            highlightTitle = ""
            notice = "Highlight submitted for review. It stays private until approved."
            await refreshMedia()
        } catch { self.error = playerClubError(error) }
    }
}

struct ProfileEditorView: View {
    let playerID: Int
    let apiClient: APIClient
    @StateObject private var model: ProfileEditorViewModel
    @State private var photoItem: PhotosPickerItem?
    @State private var photoData: Data?
    @State private var photoBusy = false
    @State private var photoError: String?
    @State private var photoNotice: String?
    @State private var deletePhoto: ProfilePhoto?
    init(playerID: Int, apiClient: APIClient) {
        self.playerID = playerID
        self.apiClient = apiClient
        _model = StateObject(wrappedValue: ProfileEditorViewModel(playerID: playerID, client: apiClient))
    }
    var body: some View {
        Form {
            Section {
                Text("Make this profile yours. Photos and highlights are reviewed before they appear publicly.")
                    .foregroundStyle(.secondary)
                if model.busy { ProgressView("Updating your profile…") }
                if let error = model.error {
                    Text(error).foregroundStyle(.red)
                    if !model.loaded { Button("Try again") { Task { await model.load() } } }
                }
                if let notice = model.notice {
                    Label(notice, systemImage: "checkmark.circle").foregroundStyle(AcademyColors.positiveGreen)
                }
            }
            Section("Your story") {
                LabeledContent("Position") {
                    TextField("e.g. Central midfielder", text: $model.positions)
                        .multilineTextAlignment(.trailing)
                        .accessibilityLabel("Position")
                        .accessibilityIdentifier("profile-editor-position")
                }
                TextField("Short bio — how you play and what you're working toward", text: $model.bio, axis: .vertical)
                    .lineLimit(4...9).accessibilityIdentifier("profile-editor-bio")
                Text("\(model.bio.count)/2,000 characters").font(.caption).foregroundStyle(.secondary)
                Picker("Preferred foot", selection: $model.preferredFoot) {
                    Text("Not set").tag("")
                    Text("Left").tag("left")
                    Text("Right").tag("right")
                    Text("Both").tag("both")
                }
                LabeledContent("Height (cm)") {
                    TextField("Optional", text: $model.height).keyboardType(.numberPad)
                        .multilineTextAlignment(.trailing).accessibilityLabel("Height in centimetres")
                }
                Button("Save profile") { Task { await model.save() } }.accessibilityIdentifier("profile-editor-save")
            }.disabled(!model.loaded || model.busy || photoBusy)
            photoSection
            Section("Your highlights") {
                TextField("YouTube link", text: $model.highlightURL).keyboardType(.URL).textInputAutocapitalization(
                    .never
                ).autocorrectionDisabled().accessibilityIdentifier("profile-highlight-url")
                TextField("Title (optional)", text: $model.highlightTitle)
                Button("Submit highlight for review") { Task { await model.addHighlight() } }.accessibilityIdentifier(
                    "profile-highlight-submit")
                ForEach(model.showcase?.reel ?? []) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.title ?? "Highlight").font(.subheadline)
                        Text(item.status.capitalized).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }.disabled(!model.loaded || model.busy || photoBusy)
            Section {
                WebDestinationLink(
                    url: URL(
                        string:
                            "https://theacademywatch.com/\(playerID < 0 ? "local-players/\(-playerID)" : "players/\(playerID)")"
                    )!, title: "More profile tools on the web")
                Text(
                    "Manage reel order, contract details, and additional profile information on the web with the same email."
                ).font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Edit profile").navigationBarTitleDisplayMode(.inline)
        .task { await model.load() }
        .task(id: photoItem) {
            photoData = nil
            photoError = nil
            guard let item = photoItem else { return }
            photoBusy = true
            defer { photoBusy = false }
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else {
                    throw ProfilePhotoError.invalidImage
                }
                let jpeg = try await Task.detached { try ProfilePhotoPreparation.jpeg(data) }.value
                guard !Task.isCancelled, photoItem == item else { return }
                photoData = jpeg
            } catch {
                if !Task.isCancelled {
                    photoError = "This photo couldn't be loaded. Try another image or check your iCloud connection."
                }
            }
        }
        .confirmationDialog(
            "Delete this photo?",
            isPresented: Binding(get: { deletePhoto != nil }, set: { if !$0 { deletePhoto = nil } }),
            presenting: deletePhoto
        ) { photo in
            Button("Delete photo", role: .destructive) { Task { await mutatePhoto(photo, delete: true) } }
        } message: { _ in
            Text("The photo will be removed from this profile.")
        }
    }
    private var photoSection: some View {
        Section("Your photos") {
            PhotosPicker(selection: $photoItem, matching: .images, preferredItemEncoding: .compatible) {
                Label("Choose a photo", systemImage: "photo.badge.plus")
            }
            .disabled(!model.loaded || model.busy || photoBusy)
            if let photoData, let image = UIImage(data: photoData) {
                Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 220)
                Text("Choose a clear photo of this player that you have permission to share.").font(.caption)
                    .foregroundStyle(.secondary)
                Button("Submit photo for review") { Task { await uploadPhoto(photoData) } }.disabled(
                    photoBusy || model.busy
                ).accessibilityIdentifier("profile-photo-submit")
                Button("Remove selection", role: .cancel) {
                    self.photoData = nil
                    photoItem = nil
                }.disabled(photoBusy)
            }
            if photoBusy { ProgressView("Preparing your photo…") }
            if let photoError { Text(photoError).foregroundStyle(.red) }
            if let photoNotice { Text(photoNotice).foregroundStyle(AcademyColors.positiveGreen) }
            ForEach(model.showcase?.photos ?? []) { photo in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(photo.isPrimary ? "Profile photo" : "Photo").font(.subheadline.bold())
                        Text(photo.status == "pending_upload" ? "Upload incomplete" : photo.status.capitalized).font(
                            .caption
                        ).foregroundStyle(.secondary)
                        if let note = photo.reviewNote { Text(note).font(.caption).foregroundStyle(.secondary) }
                    }
                    Spacer()
                    Menu {
                        if photo.status == "approved", !photo.isPrimary {
                            Button("Use as profile photo") { Task { await mutatePhoto(photo, delete: false) } }
                        }
                        Button("Delete photo", role: .destructive) { deletePhoto = photo }
                    } label: {
                        Image(systemName: "ellipsis.circle").accessibilityLabel("Photo actions")
                    }.disabled(model.busy || photoBusy)
                }
            }
        }
    }
    private func uploadPhoto(_ data: Data) async {
        guard !photoBusy, !model.busy else { return }
        photoBusy = true
        photoError = nil
        photoNotice = nil
        defer { photoBusy = false }
        var mediaID: Int?
        var uploadClient: APIClient?
        do {
            let client = try await apiClient.boundToCurrentAccount()
            uploadClient = client
            let upload = try await client.createProfilePhoto(playerID: playerID, sizeBytes: data.count)
            mediaID = upload.media.id
            try await ProfilePhotoTransfer.upload(data, destination: upload.upload)
            _ = try await client.completeProfilePhoto(playerID: playerID, mediaID: upload.media.id)
            photoData = nil
            photoItem = nil
            photoNotice = "Photo submitted. It stays private until approved."
            await model.refreshMedia()
        } catch {
            // Only clean up the slot this attempt created, so failed transfers
            // don't consume the owner's photo quota indefinitely.
            if let mediaID, let uploadClient {
                try? await uploadClient.deleteProfilePhoto(playerID: playerID, mediaID: mediaID)
            }
            photoError = playerClubError(error)
        }
    }
    private func mutatePhoto(_ photo: ProfilePhoto, delete: Bool) async {
        guard !photoBusy, !model.busy else { return }
        photoBusy = true
        photoError = nil
        defer { photoBusy = false }
        do {
            if delete {
                try await apiClient.deleteProfilePhoto(playerID: playerID, mediaID: photo.id)
            } else {
                try await apiClient.makeProfilePhotoPrimary(playerID: playerID, mediaID: photo.id)
            }
            await model.refreshMedia()
            photoNotice = delete ? "Photo removed." : "Profile photo updated."
        } catch { photoError = playerClubError(error) }
    }
}

enum ProfilePhotoError: LocalizedError {
    case invalidImage, invalidDestination, uploadFailed
    var errorDescription: String? {
        switch self {
        case .invalidImage: "Choose a smaller JPEG, PNG, or HEIC photo."
        case .invalidDestination: "Photo uploads aren't available right now. Please try again later."
        case .uploadFailed: "The photo upload didn't finish. Please try again."
        }
    }
}
enum ProfilePhotoPreparation {
    static func jpeg(_ data: Data) throws -> Data {
        guard data.count <= 40 * 1_024 * 1_024,
            let source = CGImageSourceCreateWithData(
                data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
            let image = CGImageSourceCreateThumbnailAtIndex(
                source, 0,
                [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: 1_600,
                ] as CFDictionary)
        else { throw ProfilePhotoError.invalidImage }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, UTType.jpeg.identifier as CFString, 1, nil)
        else { throw ProfilePhotoError.invalidImage }
        CGImageDestinationAddImage(
            destination, image, [kCGImageDestinationLossyCompressionQuality: 0.85] as CFDictionary)
        guard CGImageDestinationFinalize(destination), output.length <= 5 * 1_024 * 1_024 else {
            throw ProfilePhotoError.invalidImage
        }
        return output as Data
    }
}
private final class NoPhotoRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(
        _ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void
    ) { completionHandler(nil) }
}
enum ProfilePhotoTransfer {
    static func request(destination: ProfilePhotoUpload.Upload) throws -> URLRequest {
        let url = destination.url
        guard url.scheme == "https", url.host?.hasSuffix(".blob.core.windows.net") == true,
            url.user == nil, url.password == nil, url.port == nil, destination.method == "PUT"
        else { throw ProfilePhotoError.invalidDestination }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.timeoutInterval = 60
        request.cachePolicy = .reloadIgnoringLocalCacheData
        for (key, value) in destination.headers where ["content-type", "x-ms-blob-type"].contains(key.lowercased()) {
            request.setValue(value, forHTTPHeaderField: key)
        }
        return request
    }
    static func upload(_ data: Data, destination: ProfilePhotoUpload.Upload) async throws {
        let request = try request(destination: destination)
        let config = URLSessionConfiguration.ephemeral
        config.httpShouldSetCookies = false
        config.urlCache = nil
        let session = URLSession(configuration: config, delegate: NoPhotoRedirects(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        let (_, response) = try await session.upload(for: request, from: data)
        guard let response = response as? HTTPURLResponse, (200...299).contains(response.statusCode) else {
            throw ProfilePhotoError.uploadFailed
        }
    }
}
