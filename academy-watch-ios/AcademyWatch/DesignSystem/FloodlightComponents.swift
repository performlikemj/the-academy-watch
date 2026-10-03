import SwiftUI

struct FloodlightPillStyle: ButtonStyle {
    enum Variant { case primary, outline, onDark }
    var variant: Variant = .primary
    @Environment(\.isFocused) private var isFocused
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .environment(\.logoLoadingSurface, variant == .primary ? .primaryButton : variant == .onDark ? .chalk : .page)
            .font(AcademyType.subheadline.weight(.medium))
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .frame(minHeight: 46)
            .foregroundStyle(foreground)
            .background(fill, in: Capsule())
            .overlay { Capsule().stroke(variant == .onDark ? AcademyColors.chalk.opacity(0.4) : AcademyColors.hairline, lineWidth: variant == .primary ? 0 : 1) }
            .opacity(!isEnabled ? 0.45 : configuration.isPressed ? 0.75 : 1)
            .animation(reduceMotion ? nil : .easeInOut(duration: 0.18), value: configuration.isPressed)
            .contentShape(Capsule())
            .overlay { if isFocused { Capsule().stroke(AcademyColors.accent, lineWidth: 2).padding(-3) } }
    }
    private var foreground: Color {
        switch variant {
        case .primary: AcademyColors.onPrimary
        case .outline: AcademyColors.text
        case .onDark: AcademyColors.night
        }
    }
    private var fill: Color {
        switch variant {
        case .primary: AcademyColors.primaryFill
        case .outline: .clear
        case .onDark: AcademyColors.chalk
        }
    }
}

struct FloodlightEyebrow: View {
    let text: String
    var body: some View {
        Text(text.uppercased()).font(AcademyType.caption).tracking(1.6)
            .foregroundStyle(AcademyColors.accent)
            .fixedSize(horizontal: false, vertical: true)
    }
}

struct FloodlightSectionHeader: View {
    let title: String
    var counter: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline) { titleText; Spacer(minLength: 8); countText }
                VStack(alignment: .leading, spacing: 8) { titleText; countText }
            }
            Rectangle().fill(AcademyColors.text).frame(height: 1)
        }
        .accessibilityElement(children: .combine)
    }
    private var titleText: some View { Text(title).font(AcademyType.title2).foregroundStyle(AcademyColors.text) }
    @ViewBuilder private var countText: some View {
        if let counter { Text(counter.uppercased()).font(AcademyType.caption).tracking(1.2).foregroundStyle(AcademyColors.secondaryText) }
    }
}

struct FloodlightStat: View {
    let value: String
    let label: String
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(value).font(AcademyType.serif(52, relativeTo: .title)).foregroundStyle(AcademyColors.text)
            FloodlightEyebrow(text: label)
        }.accessibilityElement(children: .combine)
    }
}

struct FloodlightRow: ViewModifier {
    func body(content: Content) -> some View {
        content.padding(.vertical, 16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(AcademyColors.hairline).frame(height: 1) }
    }
}

struct FloodlightTextFieldStyle: TextFieldStyle {
    @Environment(\.isFocused) private var isFocused
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration.font(AcademyType.body)
            .padding(.horizontal, 14).padding(.vertical, 12)
            .frame(minHeight: 46)
            .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
            .overlay { RoundedRectangle(cornerRadius: 10).stroke(isFocused ? AcademyColors.accent : AcademyColors.hairline, lineWidth: isFocused ? 2 : 1) }
    }
}

struct FloodlightEmptyState: View {
    let title: String
    let systemImage: String
    var description: String?
    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: systemImage).font(AcademyType.ui(32)).foregroundStyle(AcademyColors.accent).accessibilityHidden(true)
            Text(title).font(AcademyType.title2).foregroundStyle(AcademyColors.text)
            if let description { Text(description).font(AcademyType.body).foregroundStyle(AcademyColors.secondaryText) }
        }
        .multilineTextAlignment(.center).padding(24).frame(maxWidth: 430)
        .accessibilityElement(children: .combine)
    }
}

struct FloodlightAppearance: ViewModifier {
    func body(content: Content) -> some View {
        content.font(AcademyType.body)
            .foregroundStyle(AcademyColors.text)
            .tint(AcademyColors.accent)
            .textFieldStyle(FloodlightTextFieldStyle())
            .background(AcademyColors.background)
    }
}

extension View {
    func floodlightAppearance() -> some View { modifier(FloodlightAppearance()) }
    func floodlightRow() -> some View { modifier(FloodlightRow()) }
}

/// Native navigation and system sheets share the same adaptive palette.
enum FloodlightNativeAppearance {
    static func configure() {
        let background = UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: 0x0B0E0D) : UIColor(hex: 0xF3F0E8) }
        let foreground = UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: 0xF3F0E8) : UIColor(hex: 0x0E1311) }
        let navigation = UINavigationBarAppearance()
        navigation.configureWithOpaqueBackground()
        navigation.backgroundColor = background
        navigation.shadowColor = UIColor(hex: 0xD8D2C4).withAlphaComponent(0.25)
        let serif = UIFont(name: "InstrumentSerif-Regular", size: 23) ?? .systemFont(ofSize: 23)
        navigation.titleTextAttributes = [.font: UIFontMetrics(forTextStyle: .headline).scaledFont(for: serif), .foregroundColor: foreground]
        navigation.largeTitleTextAttributes = [.font: UIFontMetrics(forTextStyle: .largeTitle).scaledFont(for: UIFont(name: "InstrumentSerif-Regular", size: 44) ?? serif), .foregroundColor: foreground]
        UINavigationBar.appearance().standardAppearance = navigation
        UINavigationBar.appearance().scrollEdgeAppearance = navigation
        UINavigationBar.appearance().compactAppearance = navigation
        let tab = UITabBarAppearance()
        tab.configureWithOpaqueBackground()
        tab.backgroundColor = background
        UITabBar.appearance().standardAppearance = tab
        UITabBar.appearance().scrollEdgeAppearance = tab
        UITableView.appearance().backgroundColor = background
        UICollectionView.appearance().backgroundColor = background
        UITextView.appearance().backgroundColor = background
    }
}
