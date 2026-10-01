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
                .font(AcademyType.caption.weight(.medium))
                .tracking(1.05)
                .foregroundStyle(AcademyColors.accent)

            Spacer()

            if viewModel.isFixturePreview {
                BadgeView(
                    text: "Fixture preview",
                    foregroundColor: AcademyColors.warnText,
                    backgroundColor: AcademyColors.warnText.opacity(0.12)
                )
            }
        }
        .padding(.horizontal, 2)
    }

    private func highlightReel(_ reel: [ShowcaseReelItem]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Highlight reel", systemImage: "play.rectangle.fill")
                .font(AcademyType.subheadline.weight(.semibold))

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
            }.background(AcademyColors.background)
        }
        .padding(14)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(AcademyColors.separator.opacity(0.22), lineWidth: 0.5)
        }
    }

    private func selfReportedProfile(_ profile: ShowcaseProfile) -> some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 8) {
                Image(systemName: "person.text.rectangle")
                    .foregroundStyle(AcademyColors.secondaryText)
                Text("Player profile")
                    .font(AcademyType.subheadline.weight(.semibold))
                Spacer(minLength: 4)
                BadgeView(
                    text: "Self-reported",
                    foregroundColor: AcademyColors.secondaryText,
                    backgroundColor: AcademyColors.elevatedSurface
                )
            }

            if let bio = clean(profile.bio) {
                Text(bio)
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.text)
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
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.75)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Self-reported player profile")
    }

    private func verifiedAppearances(_ appearances: [ShowcaseVerifiedFootage]) -> some View {
        let verifiedGreen = AcademyColors.good

        return VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.shield.fill")
                    .foregroundStyle(verifiedGreen)
                Text("Verified appearances")
                    .font(AcademyType.subheadline.weight(.semibold))
                Spacer(minLength: 4)
                BadgeView(
                    text: "Club-verified",
                    foregroundColor: verifiedGreen,
                    backgroundColor: verifiedGreen.opacity(0.12)
                )
            }

            Text("Verified from club match footage with a human-confirmed identity.")
                .font(AcademyType.caption)
                .foregroundStyle(AcademyColors.secondaryText)

            ForEach(Array(appearances.enumerated()), id: \.element.id) { index, appearance in
                if index > 0 {
                    Divider().overlay(verifiedGreen.opacity(0.15))
                }
                VerifiedAppearanceRow(appearance: appearance)
            }
        }
        .padding(14)
        .background(verifiedGreen.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(verifiedGreen.opacity(0.32), lineWidth: 0.75)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Club-verified appearance evidence")
    }

    private func showcaseAttribute(label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(label + ":")
                .foregroundStyle(AcademyColors.secondaryText)
            Text(value)
                .fontWeight(.medium)
        }
        .font(AcademyType.caption)
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
                                AcademyColors.elevatedSurface
                                CleatLoader().tint(AcademyColors.accent)
                            }
                        case .failure:
                            reelPlaceholder
                        @unknown default:
                            reelPlaceholder
                        }
                    }

                    Circle()
                        .fill(AcademyColors.night.opacity(0.68))
                        .frame(width: 46, height: 46)
                        .overlay {
                            Image(systemName: "play.fill")
                                .font(AcademyType.headline)
                                .foregroundStyle(AcademyColors.chalk)
                                .offset(x: 1)
                        }
                }
                .frame(width: 250, height: 140)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 10))

                Text(item.displayTitle)
                    .font(AcademyType.subheadline.weight(.semibold))
                    .foregroundStyle(AcademyColors.text)
                    .lineLimit(2)

                Label(item.sourceLabel, systemImage: "safari")
                    .font(AcademyType.caption2)
                    .foregroundStyle(AcademyColors.secondaryText)
            }
            .frame(width: 250, alignment: .leading)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Open \(item.displayTitle) on YouTube in app")
        .accessibilityHint("Opens an in-app browser")
    }

    private var reelPlaceholder: some View {
        ZStack {
            AcademyColors.elevatedSurface
            Image(systemName: "play.rectangle.fill")
                .font(AcademyType.largeTitle)
                .foregroundStyle(AcademyColors.accent.opacity(0.55))
        }
    }
}

private struct VerifiedAppearanceRow: View {
    let appearance: ShowcaseVerifiedFootage

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(appearance.opponentName.map { "vs \($0)" } ?? appearance.teamName ?? "Match")
                    .font(AcademyType.subheadline.weight(.semibold))
                    .lineLimit(1)

                let detail = [appearance.teamName, formattedDate(appearance.matchDate)]
                    .compactMap { $0 }
                    .joined(separator: " · ")
                if !detail.isEmpty {
                    Text(detail)
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
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
                .font(AcademyType.subheadline.weight(.semibold))
                .monospacedDigit()
            Text(label)
                .font(AcademyType.caption2)
                .foregroundStyle(AcademyColors.secondaryText)
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
        controller.preferredBarTintColor = UIColor(AcademyColors.background)
        controller.preferredControlTintColor = UIColor(AcademyColors.accent)
        controller.dismissButtonStyle = .close
        return controller
    }

    func updateUIViewController(_: SFSafariViewController, context _: Context) {}
}
