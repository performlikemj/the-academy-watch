import SafariServices
import SwiftUI

struct ShowcaseSectionView: View {
    @ObservedObject var viewModel: ShowcaseViewModel
    @State private var selectedVideo: ShowcaseVideoDestination?

    var body: some View {
        if let showcase = viewModel.visibleShowcase {
            VStack(alignment: .leading, spacing: 12) {
                sectionHeader

                if !showcase.approvedReel.isEmpty {
                    highlightReel(showcase.approvedReel)
                }

                if let profile = showcase.selfReportedProfile {
                    selfReportedProfile(profile)
                }

                if !showcase.clubVerifiedFootage.isEmpty {
                    verifiedAppearances(showcase.clubVerifiedFootage)
                }
            }
            .sheet(item: $selectedVideo) { destination in
                ShowcaseSafariView(url: destination.url)
                    .ignoresSafeArea()
            }
        }
    }

    private var sectionHeader: some View {
        HStack(spacing: 8) {
            Label("SHOWCASE", systemImage: "sparkles")
                .font(.caption.weight(.bold))
                .tracking(1.05)
                .foregroundStyle(AcademyColors.claret)

            Spacer()

            if viewModel.isFixturePreview {
                BadgeView(
                    text: "Fixture preview",
                    foregroundColor: Color(red: 0.68, green: 0.35, blue: 0.03),
                    backgroundColor: Color.orange.opacity(0.14)
                )
            }
        }
        .padding(.horizontal, 2)
    }

    private func highlightReel(_ reel: [ShowcaseReelItem]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Highlight reel", systemImage: "play.rectangle.fill")
                .font(.subheadline.weight(.semibold))

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 12) {
                    ForEach(reel) { item in
                        HighlightReelCard(item: item) {
                            guard let videoURL = item.videoURL else { return }
                            selectedVideo = ShowcaseVideoDestination(url: videoURL)
                        }
                    }
                }
                .padding(.horizontal, 1)
            }
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16))
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .stroke(AcademyColors.separator.opacity(0.22), lineWidth: 0.5)
        }
    }

    private func selfReportedProfile(_ profile: ShowcaseProfile) -> some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 8) {
                Image(systemName: "person.text.rectangle")
                    .foregroundStyle(.secondary)
                Text("Player profile")
                    .font(.subheadline.weight(.semibold))
                Spacer(minLength: 4)
                BadgeView(
                    text: "Self-reported",
                    foregroundColor: .secondary,
                    backgroundColor: Color(uiColor: .tertiarySystemFill)
                )
            }

            if let bio = clean(profile.bio) {
                Text(bio)
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            VStack(alignment: .leading, spacing: 7) {
                if let positions = clean(profile.positions) {
                    showcaseAttribute(label: "Positions", value: positions)
                }
                if let foot = clean(profile.preferredFoot) {
                    showcaseAttribute(label: "Preferred foot", value: foot.capitalized)
                }
                if let height = profile.heightCm {
                    showcaseAttribute(label: "Height", value: "\(height) cm")
                }
            }
        }
        .padding(14)
        .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.75)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Self-reported player profile")
    }

    private func verifiedAppearances(_ appearances: [ShowcaseVerifiedFootage]) -> some View {
        let verifiedGreen = Color(red: 0.03, green: 0.45, blue: 0.24)

        return VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.shield.fill")
                    .foregroundStyle(verifiedGreen)
                Text("Verified appearances")
                    .font(.subheadline.weight(.semibold))
                Spacer(minLength: 4)
                BadgeView(
                    text: "Club-verified",
                    foregroundColor: verifiedGreen,
                    backgroundColor: verifiedGreen.opacity(0.13)
                )
            }

            Text("Verified from club match footage with a human-confirmed identity.")
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(Array(appearances.enumerated()), id: \.element.id) { index, appearance in
                if index > 0 {
                    Divider().overlay(verifiedGreen.opacity(0.15))
                }
                VerifiedAppearanceRow(appearance: appearance)
            }
        }
        .padding(14)
        .background(verifiedGreen.opacity(0.07), in: RoundedRectangle(cornerRadius: 16))
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .stroke(verifiedGreen.opacity(0.32), lineWidth: 0.75)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Club-verified appearance evidence")
    }

    private func showcaseAttribute(label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(label + ":")
                .foregroundStyle(.secondary)
            Text(value)
                .fontWeight(.medium)
        }
        .font(.caption)
    }

    private func clean(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty
        else { return nil }
        return value
    }
}

private struct HighlightReelCard: View {
    let item: ShowcaseReelItem
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 8) {
                ZStack {
                    AsyncImage(url: item.thumbnailURL) { phase in
                        switch phase {
                        case let .success(image):
                            image
                                .resizable()
                                .scaledToFill()
                        case .empty:
                            ZStack {
                                Color(uiColor: .tertiarySystemFill)
                                ProgressView().tint(AcademyColors.claret)
                            }
                        case .failure:
                            reelPlaceholder
                        @unknown default:
                            reelPlaceholder
                        }
                    }

                    Circle()
                        .fill(.black.opacity(0.68))
                        .frame(width: 46, height: 46)
                        .overlay {
                            Image(systemName: "play.fill")
                                .font(.headline)
                                .foregroundStyle(.white)
                                .offset(x: 1)
                        }
                }
                .frame(width: 250, height: 140)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Text(item.displayTitle)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(2)

                Label(item.sourceLabel, systemImage: "safari")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(width: 250, alignment: .leading)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Open \(item.displayTitle) on YouTube in app")
        .accessibilityHint("Opens an in-app browser")
    }

    private var reelPlaceholder: some View {
        ZStack {
            LinearGradient(
                colors: [AcademyColors.claretSoft, Color(uiColor: .tertiarySystemFill)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Image(systemName: "play.rectangle.fill")
                .font(.largeTitle)
                .foregroundStyle(AcademyColors.claret.opacity(0.55))
        }
    }
}

private struct VerifiedAppearanceRow: View {
    let appearance: ShowcaseVerifiedFootage

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(appearance.opponentName.map { "vs \($0)" } ?? appearance.teamName ?? "Match")
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)

                let detail = [appearance.teamName, formattedDate(appearance.matchDate)]
                    .compactMap { $0 }
                    .joined(separator: " · ")
                if !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 4)

            if let minutes = appearance.minutesOnCamera {
                evidenceMetric(
                    value: minutes.formatted(.number.precision(.fractionLength(0 ... 1))) + "′",
                    label: "on camera"
                )
            }
            if let coverage = appearance.coveragePercent {
                evidenceMetric(value: "\(coverage)%", label: "of match")
            }
        }
        .padding(.vertical, 2)
    }

    private func evidenceMetric(value: String, label: String) -> some View {
        VStack(alignment: .trailing, spacing: 1) {
            Text(value)
                .font(.subheadline.weight(.bold))
                .monospacedDigit()
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private func formattedDate(_ value: String?) -> String? {
        guard let value else { return nil }
        let input = DateFormatter()
        input.locale = Locale(identifier: "en_US_POSIX")
        input.dateFormat = "yyyy-MM-dd"
        guard let date = input.date(from: String(value.prefix(10))) else { return nil }

        let output = DateFormatter()
        output.locale = .autoupdatingCurrent
        output.setLocalizedDateFormatFromTemplate("d MMM yyyy")
        return output.string(from: date)
    }
}

private struct ShowcaseVideoDestination: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

private struct ShowcaseSafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context _: Context) -> SFSafariViewController {
        let controller = SFSafariViewController(url: url)
        controller.dismissButtonStyle = .close
        return controller
    }

    func updateUIViewController(_: SFSafariViewController, context _: Context) {}
}
