import SwiftUI

struct PlayerIdentityHeader: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
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
                    .font(AcademyType.serif(26, relativeTo: .headline))
                    .foregroundStyle(AcademyColors.text)
                    .fixedSize(horizontal: false, vertical: true)

                if let metadata, !metadata.isEmpty {
                    Text(metadata)
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let club, !club.isEmpty {
                    Label(club, systemImage: "shield.fill")
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
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

            Spacer(minLength: reservesTrailingControlSpace ? 44 : 0)
        }
    }

    @ViewBuilder
    private var playerPhoto: some View {
        Group {
            if let photoURL {
                AsyncImage(url: photoURL, transaction: Transaction(animation: reduceMotion ? nil : .easeInOut(duration: 0.2))) { phase in
                    switch phase {
                    case let .success(image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .empty:
                        ProgressView()
                            .tint(AcademyColors.accent)
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
        .background(AcademyColors.elevatedSurface)
        .clipShape(Circle())
        .overlay {
            Circle().stroke(AcademyColors.accent.opacity(0.18), lineWidth: 1)
        }
        .accessibilityLabel("Photo of \(name)")
    }

    private var photoPlaceholder: some View {
        Image(systemName: "person.crop.circle.fill")
            .resizable()
            .scaledToFit()
            .foregroundStyle(AcademyColors.secondaryText)
    }

    private static func displayStatus(_ status: String) -> String {
        status
            .split(separator: "_")
            .map { $0.capitalized }
            .joined(separator: " ")
    }

    private static func statusColor(_ status: String) -> Color {
        switch status {
        case "academy": AcademyColors.secondaryText
        case "on_loan": AcademyColors.warnText
        case "first_team": AcademyColors.good
        case "sold": AcademyColors.secondaryText
        case "released", "left": .secondary
        default: AcademyColors.accent
        }
    }
}
