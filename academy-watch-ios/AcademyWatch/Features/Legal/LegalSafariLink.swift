import SafariServices
import SwiftUI

enum LegalDestination: String, CaseIterable, Identifiable {
    case privacy
    case terms
    case communityRules
    case support

    var id: String { rawValue }

    var title: String {
        switch self {
        case .privacy: "Privacy Policy"
        case .terms: "Terms of Service"
        case .communityRules: "Community Rules"
        case .support: "Support"
        }
    }

    var url: URL {
        switch self {
        case .privacy: URL(string: "https://theacademywatch.com/privacy")!
        case .terms: URL(string: "https://theacademywatch.com/terms")!
        case .communityRules: URL(string: "https://theacademywatch.com/community-rules")!
        case .support: URL(string: "https://theacademywatch.com/support")!
        }
    }

    var systemImage: String {
        switch self {
        case .privacy: "hand.raised.fill"
        case .terms: "doc.text.fill"
        case .communityRules: "person.2.fill"
        case .support: "questionmark.circle.fill"
        }
    }
}

struct LegalSafariLink<Label: View>: View {
    let destination: LegalDestination

    @State private var isPresented = false
    private let label: Label

    init(destination: LegalDestination, @ViewBuilder label: () -> Label) {
        self.destination = destination
        self.label = label()
    }

    var body: some View {
        Button {
            isPresented = true
        } label: {
            label
        }
        .accessibilityAddTraits(.isLink)
        .sheet(isPresented: $isPresented) {
            LegalSafariView(url: destination.url)
                .ignoresSafeArea()
        }
    }
}

private struct LegalSafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context _: Context) -> SFSafariViewController {
        let controller = SFSafariViewController(url: url)
        controller.dismissButtonStyle = .close
        return controller
    }

    func updateUIViewController(_: SFSafariViewController, context _: Context) {}
}
