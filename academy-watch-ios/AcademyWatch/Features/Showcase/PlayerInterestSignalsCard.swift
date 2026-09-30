import SwiftUI

@MainActor
struct PlayerInterestSignalsCard: View {
    @ObservedObject var viewModel: PlayerInterestSignalsViewModel
    @ObservedObject private var availability: ContactFeatureAvailability

    init(viewModel: PlayerInterestSignalsViewModel) {
        self.viewModel = viewModel
        _availability = ObservedObject(wrappedValue: viewModel.availability)
    }

    var body: some View {
        Group {
            if !availability.isUnavailable, viewModel.isCardVisible {
                cardContent
            }
        }
        .task {
            await viewModel.loadIfNeeded()
        }
    }

    private var cardContent: some View {
        VStack(alignment: .leading, spacing: 13) {
            cardHeader

            if viewModel.isLoading, !viewModel.hasLoaded {
                loadingContent
            } else if let presentation = viewModel.presentation {
                presentationContent(presentation)
                if viewModel.errorMessage != nil {
                    refreshFailure
                }
            } else if viewModel.errorMessage != nil {
                initialFailure
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.75)
        }
        .accessibilityIdentifier("player-interest-signals-card")
    }

    private var cardHeader: some View {
        HStack(spacing: 8) {
            Label("PROFILE INTEREST", systemImage: "eye.fill")
                .font(AcademyType.caption.weight(.medium))
                .tracking(1.05)
                .foregroundStyle(AcademyColors.accent)

            Spacer(minLength: 4)

            if viewModel.isFixturePreview {
                BadgeView(
                    text: "Fixture preview",
                    foregroundColor: AcademyColors.warnText,
                    backgroundColor: AcademyColors.warnText.opacity(0.12)
                )
            }
        }
    }

    private var loadingContent: some View {
        HStack(spacing: 10) {
            ProgressView()
                .tint(AcademyColors.accent)
            Text("Checking your profile interest…")
                .font(AcademyType.subheadline)
                .foregroundStyle(AcademyColors.secondaryText)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Loading profile interest")
    }

    @ViewBuilder
    private func presentationContent(_ presentation: PlayerInterestSignalsPresentation) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(presentation.title)
                    .font(AcademyType.headline)
                Text(presentation.message)
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if presentation.isZeroState {
                Label("Keep telling your football story", systemImage: "sparkles")
                    .font(AcademyType.caption.weight(.medium))
                    .foregroundStyle(AcademyColors.accent)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(AcademyColors.accentSoft, in: Capsule())
                    .accessibilityIdentifier("player-interest-signals-zero-state")
            } else {
                metricLayout(presentation.metrics)
            }
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private func metricLayout(_ metrics: [PlayerInterestSignalsPresentation.Metric]) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: 10) {
                ForEach(metrics) { metric in
                    metricTile(metric)
                }
            }

            VStack(spacing: 10) {
                ForEach(metrics) { metric in
                    metricTile(metric)
                }
            }
        }
    }

    private func metricTile(_ metric: PlayerInterestSignalsPresentation.Metric) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Label(metric.title, systemImage: metric.systemImage)
                .font(AcademyType.caption.weight(.medium))
                .foregroundStyle(AcademyColors.accent)

            if metric.total > 0 {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(metric.total, format: .number)
                        .font(AcademyType.title2)
                        .fontDesign(.rounded)
                    Text(metric.totalUnit)
                        .font(AcademyType.caption)
                        .foregroundStyle(AcademyColors.secondaryText)
                }
            } else {
                Text(metric.emptyTotalText)
                    .font(AcademyType.subheadline.weight(.semibold))
                    .foregroundStyle(AcademyColors.secondaryText)
            }

            Label(
                metric.weeklyActivityText,
                systemImage: metric.addedThisWeek > 0 ? "arrow.up.right" : "calendar"
            )
            .font(AcademyType.caption2.weight(.medium))
            .foregroundStyle(metric.addedThisWeek > 0 ? AcademyColors.good : AcademyColors.secondaryText)
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel(for: metric))
    }

    private var initialFailure: some View {
        VStack(alignment: .leading, spacing: 9) {
            Label("Interest update unavailable", systemImage: "wifi.exclamationmark")
                .font(AcademyType.subheadline.weight(.semibold))
            Text(viewModel.errorMessage ?? "")
                .font(AcademyType.caption)
                .foregroundStyle(AcademyColors.secondaryText)
            retryButton
        }
    }

    private var refreshFailure: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text("Latest refresh didn’t complete.")
                .font(AcademyType.caption)
                .foregroundStyle(AcademyColors.secondaryText)
            Spacer(minLength: 4)
            retryButton
        }
    }

    private var retryButton: some View {
        Button("Try again") {
            Task { await viewModel.retry() }
        }
        .font(AcademyType.caption.weight(.medium))
        .buttonStyle(FloodlightPillStyle(variant: .outline))
        .tint(AcademyColors.accent)
        .disabled(viewModel.isLoading)
        .accessibilityIdentifier("player-interest-signals-retry")
    }

    private func accessibilityLabel(for metric: PlayerInterestSignalsPresentation.Metric) -> String {
        let total = metric.total > 0 ? "\(metric.total) \(metric.totalUnit)" : metric.emptyTotalText
        return "\(total), \(metric.weeklyActivityText)"
    }
}
