import SwiftUI
import UIKit

/// A native UITabBar with the approved outline symbols and editorial pill treatment.
/// Keeping UITabBar semantics also preserves VoiceOver and XCTest tab navigation.
struct Phase2TabBar: UIViewRepresentable {
    let tabs: [RootTab]
    let role: ExperienceRole?
    @Binding var selection: RootTab
    @Environment(\.colorScheme) private var scheme
    func makeUIView(context: Context) -> EditorialTabBar { EditorialTabBar() }
    static func dismantleUIView(_ view: EditorialTabBar, coordinator: ()) { view.restoreSystemTabBar() }
    func updateUIView(_ view: EditorialTabBar, context: Context) {
        view.configure(tabs: tabs, role: role, selected: selection) { selection = $0 }
    }
}
final class EditorialTabBar: UITabBar {
    private var choices: [UIButton] = []
    private let pill = UIView()
    private var tabs: [RootTab] = []
    private var selected: RootTab = .home
    private var onSelect: ((RootTab) -> Void)?
    private weak var systemTabBar: UITabBar?
    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundImage = UIImage()
        shadowImage = UIImage()
        addSubview(pill)
        layer.cornerRadius = 36
        layer.borderWidth = 1
        accessibilityIdentifier = "phase2-tab-bar"
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    func configure(tabs: [RootTab], role: ExperienceRole?, selected: RootTab, onSelect: @escaping (RootTab) -> Void) {
        self.tabs = tabs
        self.selected = selected
        self.onSelect = onSelect
        choices.forEach { $0.removeFromSuperview() }
        choices = []
        backgroundColor = UIColor(AcademyColors.background)
        layer.borderColor = UIColor(AcademyColors.hairline).resolvedColor(with: traitCollection).cgColor
        pill.backgroundColor = UIColor(AcademyColors.elevatedSurface)
        pill.layer.cornerRadius = 30
        for (index, tab) in tabs.enumerated() {
            let button = UIButton(type: .custom)
            button.tag = index
            button.addTarget(self, action: #selector(tapped(_:)), for: .touchUpInside)
            button.accessibilityLabel = tab.editorialTitle(role: role)
            button.accessibilityIdentifier = "tab-bar-" + tab.rawValue
            button.accessibilityTraits = tab == selected ? [.button, .selected] : .button
            var config = UIButton.Configuration.plain()
            config.image = UIImage(
                systemName: tab.editorialIcon,
                withConfiguration: UIImage.SymbolConfiguration(pointSize: 21, weight: .light))
            config.imagePlacement = .top
            config.imagePadding = 5
            config.contentInsets = .zero
            var title = AttributedString(tab.editorialTitle(role: role))
            title.font = UIFont(name: "Geist-Regular", size: 11) ?? .systemFont(ofSize: 11)
            config.attributedTitle = title
            config.baseForegroundColor = UIColor(tab == selected ? AcademyColors.accent : AcademyColors.text)
            button.configuration = config
            button.configurationUpdateHandler = { button in
                button.configuration?.baseForegroundColor = UIColor(
                    tab == selected ? AcademyColors.accent : AcademyColors.text)
            }
            addSubview(button)
            choices.append(button)
        }
        setNeedsLayout()
    }
    @objc private func tapped(_ sender: UIButton) { onSelect?(tabs[sender.tag]) }
    override func didMoveToWindow() {
        super.didMoveToWindow()
        suppressSystemTabBar()
    }
    private func suppressSystemTabBar() {
        guard let window else { return }
        func find(in view: UIView) -> UITabBar? {
            if let bar = view as? UITabBar, !(bar is EditorialTabBar) { return bar }
            for child in view.subviews { if let bar = find(in: child) { return bar } }
            return nil
        }
        if let bar = find(in: window) {
            systemTabBar = bar
            bar.isHidden = true
            bar.accessibilityElementsHidden = true
        }
    }
    func restoreSystemTabBar() {
        systemTabBar?.accessibilityElementsHidden = false
        systemTabBar?.isHidden = false
    }
    override func layoutSubviews() {
        super.layoutSubviews()
        suppressSystemTabBar()
        for view in subviews where view !== pill && !choices.contains(where: { $0 === view }) { view.isHidden = true }
        let width = (bounds.width - 12) / CGFloat(max(choices.count, 1))
        for (index, button) in choices.enumerated() {
            button.frame = CGRect(x: 6 + CGFloat(index) * width, y: 5, width: width, height: bounds.height - 10)
            if tabs[index] == selected { pill.frame = button.frame.insetBy(dx: 2, dy: 0) }
        }
    }
}
extension RootTab {
    func editorialTitle(role: ExperienceRole?) -> String {
        switch self {
        case .home: role == .club ? "Today" : "Home"
        case .scoutDesk: "Scout Desk"
        case .watchlist: "Watchlist"
        case .lists: "Lists"
        case .account: "Account"
        case .clubs: "Clubs"
        case .trials: "Trials"
        case .applied: "Applied"
        case .squads: "Squads"
        case .matches: "Matches"
        case .recruiting: "Recruiting"
        }
    }
    var editorialIcon: String {
        switch self {
        case .home: "house"
        case .scoutDesk: "binoculars"
        case .watchlist: "star"
        case .lists: "list.bullet"
        case .account: "person"
        case .clubs: "mappin.and.ellipse"
        case .trials: "flag"
        case .applied: "tray"
        case .squads: "person.3"
        case .matches: "play.rectangle"
        case .recruiting: "person.badge.plus"
        }
    }
}
