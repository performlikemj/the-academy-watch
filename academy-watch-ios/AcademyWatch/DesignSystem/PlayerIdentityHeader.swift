import SwiftUI

struct PlayerIdentityHeader: View {
    let name: String
    let photoURL: URL?
    let position: String?
    let metadata: String?
    let club: String?
    let status: String?
    var reservesTrailingControlSpace = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            playerPhoto

            VStack(alignment: .leading, spacing: 5) {
                Text(name)
                    .font(.headline)
                    .foregroundStyle(.primary)
                    .lineLimit(1)

                if let metadata, !metadata.isEmpty {
                    Text(metadata)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                if let club, !club.isEmpty {
                    Label(club, systemImage: "shield.fill")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                if position != nil || status != nil {
                    HStack(spacing: 6) {
                        if let position, !position.isEmpty {
                            BadgeView(text: position)
                        }
                        if let status, !status.isEmpty {
                            BadgeView(
                                text: Self.displayStatus(status),
                                foregroundColor: Self.statusColor(status),
                                backgroundColor: Self.statusColor(status).opacity(0.12)
                            )
                        }
                    }
                }
            }

            Spacer(minLength: reservesTrailingControlSpace ? 34 : 0)
        }
    }

    @ViewBuilder
    private var playerPhoto: some View {
        Group {
            if let photoURL {
                AsyncImage(url: photoURL, transaction: Transaction(animation: .easeInOut(duration: 0.2))) { phase in
                    switch phase {
                    case let .success(image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .empty:
                        ProgressView()
                            .tint(AcademyColors.claret)
                    case .failure:
                        photoPlaceholder
                    @unknown default:
                        photoPlaceholder
                    }
                }
            } else {
                photoPlaceholder
            }
        }
        .frame(width: 60, height: 60)
        .background(Color(uiColor: .tertiarySystemFill))
        .clipShape(Circle())
        .overlay {
            Circle().stroke(AcademyColors.claret.opacity(0.18), lineWidth: 1)
        }
        .accessibilityLabel("Photo of \(name)")
    }

    private var photoPlaceholder: some View {
        Image(systemName: "person.crop.circle.fill")
            .resizable()
            .scaledToFit()
            .foregroundStyle(.tertiary)
    }

    private static func displayStatus(_ status: String) -> String {
        status
            .split(separator: "_")
            .map { $0.capitalized }
            .joined(separator: " ")
    }

    private static func statusColor(_ status: String) -> Color {
        switch status {
        case "academy": AcademyColors.academyBlue
        case "on_loan": AcademyColors.loanAmber
        case "first_team": AcademyColors.positiveGreen
        case "sold": AcademyColors.transitionPurple
        case "released", "left": .secondary
        default: AcademyColors.claret
        }
    }
}
