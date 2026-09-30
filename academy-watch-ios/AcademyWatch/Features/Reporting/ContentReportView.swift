import SwiftUI

struct ContentReportSheet: View {
    @StateObject private var viewModel: ContentReportViewModel
    @Environment(\.dismiss) private var dismiss

    private let onSubmitted: () -> Void

    init(
        subject: ContentReportSubject,
        apiClient: any ContentReportAPIClientProtocol = APIClient(),
        onSubmitted: @escaping () -> Void = {}
    ) {
        _viewModel = StateObject(
            wrappedValue: ContentReportViewModel(subject: subject, apiClient: apiClient)
        )
        self.onSubmitted = onSubmitted
    }

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.submittedReport != nil {
                    submittedState
                } else {
                    reportForm
                }
            }
            .navigationTitle(viewModel.submittedReport == nil ? viewModel.subject.title : "Report Submitted")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: viewModel.submittedReport == nil ? .cancellationAction : .confirmationAction) {
                    Button(viewModel.submittedReport == nil ? "Cancel" : "Done") { dismiss() }
                }

                #if DEBUG
                if FullCircleFixtureDestination.fromLaunchArguments(
                    ProcessInfo.processInfo.arguments
                ) == .messageReport {
                    ToolbarItem(placement: .topBarTrailing) {
                        BadgeView(
                            text: "Fixture",
                            foregroundColor: AcademyColors.warnText,
                            backgroundColor: AcademyColors.warnText.opacity(0.12)
                        )
                    }
                }
                #endif
            }
        }
        .interactiveDismissDisabled(viewModel.isSubmitting)
    }

    private var reportForm: some View {
        Form {
            Section {
                Label(viewModel.subject.explanation, systemImage: "info.circle.fill")
                    .font(AcademyType.subheadline)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }.listRowBackground(AcademyColors.background)

            Section("Reason") {
                Picker("Reason", selection: $viewModel.selectedReason) {
                    ForEach(ContentReportReason.allCases, id: \.self) { reason in
                        Text(reason.displayName).tag(reason)
                    }
                }
                .pickerStyle(.inline)
                .labelsHidden()
                .accessibilityIdentifier("content-report-reason")
            }.listRowBackground(AcademyColors.background)

            Section {
                TextEditor(text: $viewModel.details)
                    .frame(minHeight: 105)
                    .accessibilityIdentifier("content-report-details")
            } header: {
                HStack {
                    Text("Details (optional)")
                    Spacer()
                    Text("\(viewModel.details.count)/2,000")
                        .monospacedDigit()
                }
            } footer: {
                Text("Share only what helps the moderation team understand the concern.")
            }.listRowBackground(AcademyColors.background)

            if let error = viewModel.errorMessage {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(AcademyType.footnote)
                        .foregroundStyle(AcademyColors.danger)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("content-report-error")
                }.listRowBackground(AcademyColors.background)
            }

            Section {
                Button {
                    Task {
                        if await viewModel.submit() {
                            onSubmitted()
                        }
                    }
                } label: {
                    HStack {
                        Spacer()
                        if viewModel.isSubmitting {
                            ProgressView()
                        }
                        Text(viewModel.isSubmitting ? "Submitting…" : "Submit report")
                            .fontWeight(.semibold)
                        Spacer()
                    }
                }
                .disabled(!viewModel.canSubmit)
                .accessibilityIdentifier("submit-content-report")
            }.listRowBackground(AcademyColors.background)
        }
        .scrollContentBackground(.hidden)
        .background(AcademyColors.background)
    }

    private var submittedState: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.circle.fill")
                .font(AcademyType.ui( 58))
                .foregroundStyle(AcademyColors.good)
            Text("Report submitted")
                .font(AcademyType.title2)
            Text("Thanks for letting us know. Academy Watch will review it.")
                .font(AcademyType.subheadline)
                .foregroundStyle(AcademyColors.secondaryText)
                .multilineTextAlignment(.center)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AcademyColors.background)
        .accessibilityIdentifier("content-report-submitted")
    }
}
