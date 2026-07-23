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
        .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.75)
        }
        .accessibilityIdentifier("player-interest-signals-card")
    }

    private var cardHeader: some View {
        HStack(spacing: 8) {
            Label("PROFILE INTEREST", systemImage: "eye.fill")
                .font(.caption.weight(.bold))
                .tracking(1.05)
                .foregroundStyle(AcademyColors.claret)

            Spacer(minLength: 4)

            if viewModel.isFixturePreview {
                BadgeView(
                    text: "Fixture preview",
                    foregroundColor: AcademyColors.loanAmber,
                    backgroundColor: AcademyColors.loanAmber.opacity(0.12)
                )
            }
        }
    }

    private var loadingContent: some View {
        HStack(spacing: 10) {
            ProgressView()
                .tint(AcademyColors.claret)
            Text("Checking your profile interest…")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Loading profile interest")
    }

    @ViewBuilder
    private func presentationContent(_ presentation: PlayerInterestSignalsPresentation) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(presentation.title)
                    .font(.headline)
                Text(presentation.message)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if presentation.isZeroState {
                Label("Keep telling your football story", systemImage: "sparkles")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AcademyColors.claret)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(AcademyColors.claretSoft, in: Capsule())
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
                .font(.caption.weight(.semibold))
                .foregroundStyle(AcademyColors.claret)

            if metric.total > 0 {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    Text(metric.total, format: .number)
                        .font(.title2.weight(.bold))
                        .fontDesign(.rounded)
                    Text(metric.totalUnit)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(metric.emptyTotalText)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            Label(
                metric.weeklyActivityText,
                systemImage: metric.addedThisWeek > 0 ? "arrow.up.right" : "calendar"
            )
            .font(.caption2.weight(.semibold))
            .foregroundStyle(metric.addedThisWeek > 0 ? AcademyColors.positiveGreen : Color.secondary)
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(uiColor: .tertiarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel(for: metric))
    }

    private var initialFailure: some View {
        VStack(alignment: .leading, spacing: 9) {
            Label("Interest update unavailable", systemImage: "wifi.exclamationmark")
                .font(.subheadline.weight(.semibold))
            Text(viewModel.errorMessage ?? "")
                .font(.caption)
                .foregroundStyle(.secondary)
            retryButton
        }
    }

    private var refreshFailure: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text("Latest refresh didn’t complete.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer(minLength: 4)
            retryButton
        }
    }

    private var retryButton: some View {
        Button("Try again") {
            Task { await viewModel.retry() }
        }
        .font(.caption.weight(.semibold))
        .buttonStyle(.bordered)
        .tint(AcademyColors.claret)
        .disabled(viewModel.isLoading)
        .accessibilityIdentifier("player-interest-signals-retry")
    }

    private func accessibilityLabel(for metric: PlayerInterestSignalsPresentation.Metric) -> String {
        let total = metric.total > 0 ? "\(metric.total) \(metric.totalUnit)" : metric.emptyTotalText
        return "\(total), \(metric.weeklyActivityText)"
    }
}
