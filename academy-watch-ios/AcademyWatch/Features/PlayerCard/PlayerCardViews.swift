import SwiftUI

/// Club colours for a card or hero. No payload carries a club palette yet, so
/// every surface falls back to club green + gold, as the web does.
struct PlayerClubColors: Equatable {
    var primary: Color = AcademyColors.club
    var accent: Color = AcademyColors.gold

    static let standard = PlayerClubColors()

    init() {}

    /// `#RRGGBB` strings; anything else keeps the default for that slot.
    init(primaryHex: String?, accentHex: String?) {
        if let value = Self.hexValue(primaryHex) { primary = Color(hex: value) }
        if let value = Self.hexValue(accentHex) { accent = Color(hex: value) }
    }

    static func hexValue(_ text: String?) -> UInt32? {
        guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), text.hasPrefix("#"),
              text.count == 7
        else { return nil }
        return UInt32(text.dropFirst(), radix: 16)
    }
}

/// Display numerals are already far above the minimum sizes, so they grow
/// with Dynamic Type only a little; every label around them scales in full.
private struct DisplayNumeral: ViewModifier {
    @ScaledMetric(relativeTo: .title) private var scale: CGFloat = 1
    let size: CGFloat
    var italic = false

    func body(content: Content) -> some View {
        content.font(.custom(
            italic ? "InstrumentSerif-Italic" : "InstrumentSerif-Regular",
            fixedSize: size * min(scale, 1.25)
        ))
    }
}

private extension View {
    func displayNumeral(_ size: CGFloat) -> some View { modifier(DisplayNumeral(size: size)) }
}

/// The green club-confirmed tick. `.chalk` is the version used over a photo.
struct ConfirmedTick: View {
    enum Tone { case good, chalk, paper }
    var size: CGFloat = 18
    var tone: Tone = .good

    var body: some View {
        ZStack {
            Circle().fill(fill)
            TickShape()
                .stroke(stroke, style: StrokeStyle(lineWidth: size / 10, lineCap: .round, lineJoin: .round))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    private var fill: Color {
        switch tone {
        case .good: AcademyColors.good
        case .chalk: AcademyColors.chalk
        case .paper: AcademyColors.goodOnPaper
        }
    }

    private var stroke: Color {
        switch tone {
        case .good: AcademyColors.background
        case .chalk: AcademyColors.night
        case .paper: AcademyColors.chalk
        }
    }

    private struct TickShape: Shape {
        func path(in rect: CGRect) -> Path {
            // The web tick, on its 20 x 20 grid.
            let unit = rect.width / 20
            var path = Path()
            path.move(to: CGPoint(x: 5.5 * unit, y: 10.5 * unit))
            path.addLine(to: CGPoint(x: 8.7 * unit, y: 13.5 * unit))
            path.addLine(to: CGPoint(x: 14.5 * unit, y: 7 * unit))
            return path
        }
    }
}

/// State D — no approved photo yet: large initials in the club's colours.
/// `faceURL` is a small provider headshot; it is shown at its own size, never
/// stretched into a portrait.
struct PlayerNoPhotoTile: View {
    enum Style { case card, hero }

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let name: String
    var clubName: String?
    var role: String?
    var faceURL: URL?
    var colors = PlayerClubColors.standard
    var style: Style = .card

    private var mark: CGFloat { style == .hero ? 196 : 148 }

    var body: some View {
        ZStack(alignment: style == .hero ? .top : .center) {
            colors.primary
            centre.padding(.top, style == .hero ? 72 : 0)
        }
        .overlay(alignment: .topLeading) {
            if let clubName, !clubName.isEmpty {
                caption(clubName)
                    .padding(.leading, style == .hero ? 16 : 14)
                    .padding(.trailing, style == .hero ? 16 : 14)
                    .padding(.top, style == .hero ? 22 : 14)
            }
        }
        .overlay(alignment: .bottomTrailing) {
            if style == .card, let role, !role.isEmpty {
                caption(role).padding(.horizontal, 14).padding(.bottom, 12)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(name) — no photo yet")
        .accessibilityAddTraits(.isImage)
    }

    @ViewBuilder
    private var centre: some View {
        if let faceURL {
            AsyncImage(url: faceURL, transaction: Transaction(animation: reduceMotion ? nil : .easeInOut(duration: 0.2))) { phase in
                if case let .success(image) = phase {
                    image.resizable().scaledToFill()
                        .frame(width: mark, height: mark)
                        .background(AcademyColors.chalk)
                        .clipShape(Circle())
                        .overlay { Circle().stroke(colors.accent, lineWidth: 2) }
                } else {
                    initials
                }
            }
        } else {
            initials
        }
    }

    private var initials: some View {
        Text(PlayerCardText.initials(of: name))
            .font(.custom("InstrumentSerif-Regular", fixedSize: mark))
            .tracking(-mark * 0.02)
            .foregroundStyle(colors.accent)
            .lineLimit(1)
            .minimumScaleFactor(0.4)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 12)
    }

    private func caption(_ text: String) -> some View {
        Text(text.uppercased())
            .font(AcademyType.mono(10, relativeTo: .caption2))
            .tracking(1.6)
            .foregroundStyle(AcademyColors.onClub)
            .lineLimit(1)
            .truncationMode(.tail)
    }
}

/// An approved photo, or state D when there is none or it cannot be loaded.
struct PlayerPortraitMedia: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let name: String
    var photoURL: URL?
    var faceURL: URL?
    var clubName: String?
    var role: String?
    var colors = PlayerClubColors.standard
    var style: PlayerNoPhotoTile.Style = .card

    var body: some View {
        if let photoURL {
            AsyncImage(url: photoURL, transaction: Transaction(animation: reduceMotion ? nil : .easeInOut(duration: 0.2))) { phase in
                switch phase {
                case let .success(image):
                    photo(image)
                case .empty:
                    style == .hero ? AcademyColors.heroPhotoPlaceholder : AcademyColors.photoPlaceholder
                default:
                    noPhoto
                }
            }
        } else {
            noPhoto
        }
    }

    private func photo(_ image: Image) -> some View {
        Color.clear
            .overlay { image.resizable().scaledToFill() }
            .clipped()
            .overlay(alignment: style == .hero ? .topLeading : .topTrailing) {
                if let role, !role.isEmpty {
                    Text(role.uppercased())
                        .font(AcademyType.mono(style == .hero ? 11 : 10, relativeTo: .caption2))
                        .tracking(1.4)
                        .foregroundStyle(AcademyColors.chalk)
                        .lineLimit(1)
                        .padding(.horizontal, style == .hero ? 12 : 10)
                        .frame(minHeight: style == .hero ? 28 : 26)
                        .background(colors.primary, in: Capsule())
                        .padding(style == .hero ? 16 : 12)
                        .accessibilityHidden(true)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(name)
            .accessibilityAddTraits(.isImage)
            .accessibilityIdentifier("player-photo")
    }

    private var noPhoto: some View {
        PlayerNoPhotoTile(
            name: name, clubName: clubName, role: role, faceURL: faceURL, colors: colors, style: style
        )
        .accessibilityIdentifier("player-no-photo")
    }
}

/// The standard player card (A · portrait, or D when there is no photo): the
/// card for lists and the scout desk. It keeps its paper surface on night,
/// as the web's desk does. `trailingReserve` leaves room at the bottom right
/// for the host's own controls (watch, compare), which stay their own targets.
struct PlayerStandardCard: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let name: String
    var photoURL: URL?
    var faceURL: URL?
    var line: String?
    var clubName: String?
    var role: String?
    var confirmed = false
    var counters: [CardCounter] = []
    var colors = PlayerClubColors.standard
    var trailingReserve: CGFloat = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PlayerPortraitMedia(
                name: name, photoURL: photoURL, faceURL: faceURL,
                clubName: clubName, role: role, colors: colors, style: .card
            )
            .aspectRatio(256 / 300, contentMode: .fit)
            .frame(maxWidth: .infinity)
            .background(AcademyColors.photoPlaceholder)
            .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))

            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .center, spacing: 8) {
                    Text(name)
                        .font(AcademyType.serif(30, relativeTo: .title2))
                        .foregroundStyle(AcademyColors.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if confirmed {
                        ConfirmedTick(size: 18, tone: .paper)
                    }
                }
                if let line, !line.isEmpty {
                    Text(line)
                        .font(AcademyType.subheadline)
                        .foregroundStyle(AcademyColors.cardBody)
                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? 6 : 3)
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(alignment: .center, spacing: 16) {
                    ForEach(counters) { counter in
                        (Text(counter.value).fontWeight(.semibold).foregroundColor(AcademyColors.ink)
                            + Text(" \(counter.unit)").foregroundColor(AcademyColors.muted))
                            .font(AcademyType.ui(13, relativeTo: .footnote))
                            .monospacedDigit()
                    }
                    Spacer(minLength: trailingReserve)
                }
                .frame(minHeight: 44)
                .padding(.top, 6)
            }
            .padding(.top, 18)
            .padding(.horizontal, 14)
            .padding(.bottom, 12)
        }
        .padding(8)
        .frame(maxWidth: 360)
        .background(AcademyColors.paper, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
        .shadow(color: AcademyColors.ink.opacity(0.10), radius: 20, x: 0, y: 18)
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenLabel)
    }

    private var spokenLabel: String {
        var parts = [name]
        if confirmed { parts.append("Club-confirmed") }
        if let line, !line.isEmpty { parts.append(line) }
        if !counters.isEmpty {
            parts.append(counters.map { "\($0.value) \(Self.spokenUnit($0.unit))" }.joined(separator: ", "))
        }
        if photoURL == nil { parts.append("No photo yet") }
        return parts.joined(separator: ". ")
    }

    private static func spokenUnit(_ unit: String) -> String {
        switch unit {
        case "app": "appearance"
        case "apps": "appearances"
        case "min": "minutes"
        default: unit
        }
    }
}

/// Card C — the hero at the top of a player's page: the photo full-bleed with
/// the name over a night scrim. With no approved photo it becomes state D.
struct PlayerHeroCard: View {
    /// The scrim belongs to the copy block, so the text always sits on at
    /// least 90% night whatever the photo is and however many lines the name
    /// takes: clear at the top of the block, 90% by `ninety`, solid by `solid`,
    /// and the text starts below `ninety`.
    enum Scrim {
        static let textInset: CGFloat = 150
        static let ninety: CGFloat = 140
        static let solid: CGFloat = 230
        static let ninetyOpacity = 0.9
    }

    let name: String
    var photoURL: URL?
    var faceURL: URL?
    var clubName: String?
    var role: String?
    var confirmedBy: String?
    var eyebrow: String?
    var line: String?
    var colors = PlayerClubColors.standard

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Spacer(minLength: 0)
            copy
        }
        .frame(maxWidth: .infinity, minHeight: 520, alignment: .bottomLeading)
        .background {
            PlayerPortraitMedia(
                name: name, photoURL: photoURL, faceURL: faceURL,
                clubName: clubName, role: role, colors: colors, style: .hero
            )
        }
        .background(AcademyColors.night)
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("player-hero")
    }

    private var copy: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let confirmedBy, !confirmedBy.isEmpty {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    ConfirmedTick(size: 18, tone: .chalk)
                        .alignmentGuide(.firstTextBaseline) { $0[.bottom] - 4 }
                    Text("Confirmed by \(confirmedBy)".uppercased())
                        .font(AcademyType.mono(11, relativeTo: .caption))
                        .tracking(1.5)
                        .foregroundStyle(AcademyColors.onNight)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Confirmed by \(confirmedBy)")
                .accessibilityIdentifier("player-hero-confirmed")
            }
            if let eyebrow, !eyebrow.isEmpty {
                Text(eyebrow.uppercased())
                    .font(AcademyType.mono(11, relativeTo: .caption))
                    .tracking(1.5)
                    .foregroundStyle(AcademyColors.onNight)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityLabel(eyebrow)
            }
            Text(name)
                .font(AcademyType.serif(50, relativeTo: .largeTitle))
                .foregroundStyle(AcademyColors.chalk)
                .lineSpacing(-4)
                .fixedSize(horizontal: false, vertical: true)
                // A 50-point display name is already large; past this size it
                // would push the photo out of its own card.
                .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("player-hero-name")
            if let line, !line.isEmpty {
                Text(line)
                    .font(AcademyType.ui(15, relativeTo: .subheadline))
                    .foregroundStyle(AcademyColors.onNight)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("player-hero-line")
            }
        }
        .padding(.top, Scrim.textInset)
        .padding([.horizontal, .bottom], 20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            GeometryReader { proxy in
                let height = max(proxy.size.height, Scrim.solid)
                LinearGradient(
                    stops: [
                        .init(color: AcademyColors.night.opacity(0), location: 0),
                        .init(color: AcademyColors.night.opacity(Scrim.ninetyOpacity), location: Scrim.ninety / height),
                        .init(color: AcademyColors.night, location: Scrim.solid / height),
                        .init(color: AcademyColors.night, location: 1),
                    ],
                    startPoint: .top, endPoint: .bottom
                )
            }
            .accessibilityHidden(true)
        }
    }
}

/// The player's own words under the hero: four lines, then "Read more".
struct PlayerQuote: View {
    let text: String
    @State private var isOpen = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("“\(text)”")
                .font(AcademyType.serif(22, italic: true, relativeTo: .title3))
                .foregroundStyle(AcademyColors.text)
                .lineLimit(isOpen ? nil : 4)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("player-quote")
            if text.count > 170 {
                Button(isOpen ? "Show less" : "Read more") { isOpen.toggle() }
                    .font(AcademyType.subheadline.weight(.medium))
                    .underline()
                    .foregroundStyle(AcademyColors.text)
                    .frame(minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
            }
        }
    }
}

/// Facts strip: only fields with a value; two columns, one at the largest text sizes.
struct PlayerFactsStrip: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let facts: [PlayerFact]

    var body: some View {
        if !facts.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                VStack(spacing: 0) {
                    Rectangle().fill(AcademyColors.text).frame(height: 1)
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        HStack(alignment: .top, spacing: 0) {
                            ForEach(Array(row.enumerated()), id: \.element.id) { index, fact in
                                cell(fact, leading: index == 0)
                            }
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        .overlay(alignment: .bottom) { Rectangle().fill(AcademyColors.hairline).frame(height: 1) }
                    }
                }
                // These details are the player's own, not confirmed by anyone.
                Text("SELF-REPORTED BY THE PLAYER")
                    .font(AcademyType.mono(11, relativeTo: .caption))
                    .tracking(1.6)
                    .foregroundStyle(AcademyColors.secondaryText)
                    .accessibilityLabel("Self-reported by the player")
                    .accessibilityIdentifier("player-facts-note")
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("player-facts")
        }
    }

    private var rows: [[PlayerFact]] {
        let columns = dynamicTypeSize.isAccessibilitySize ? 1 : 2
        return stride(from: 0, to: facts.count, by: columns).map {
            Array(facts[$0 ..< min($0 + columns, facts.count)])
        }
    }

    private func cell(_ fact: PlayerFact, leading: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(fact.label.uppercased())
                .font(AcademyType.mono(11, relativeTo: .caption))
                .tracking(1.6)
                .foregroundStyle(AcademyColors.secondaryText)
            if fact.isEmail, let url = URL(string: "mailto:\(fact.value)") {
                Link(destination: url) {
                    Text(fact.value).underline()
                }
                .font(AcademyType.ui(17, weight: .medium, relativeTo: .body))
                .foregroundStyle(AcademyColors.text)
            } else {
                Text(fact.value)
                    .font(AcademyType.ui(17, weight: .medium, relativeTo: .body))
                    .foregroundStyle(AcademyColors.text)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .padding(.vertical, 14)
        .padding(.leading, leading ? 0 : 12)
        .padding(.trailing, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .overlay(alignment: .leading) {
            if !leading { Rectangle().fill(AcademyColors.hairline).frame(width: 1) }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(fact.label): \(fact.value)")
        .accessibilityAddTraits(fact.isEmail ? .isLink : [])
    }
}

/// The season block: tiles, then the sentence that says where they come from.
/// Totals are either the provider's (shown whole, labelled) or exactly the
/// merged match lines below — never both added together.
struct PlayerSeasonBlock<Control: View>: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let seasonLabel: String
    var kicker = "This season"
    let summary: SeasonSummary
    var playerName = "this player"
    var colors = PlayerClubColors.standard
    var loading = false
    /// A read behind this block failed: the sentence to show. While it is set
    /// the block never claims that nothing has been recorded.
    var problem: String?
    var onRetry: (() -> Void)?
    /// The server left the oldest seasons out (very long careers).
    var truncated = false
    @ViewBuilder var control: () -> Control

    private var failedEmpty: Bool { problem != nil && summary.source == .none }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            heading
            if let problem {
                notice(problem)
            }
            if failedEmpty {
                EmptyView()
            } else if summary.source == .none {
                empty
            } else {
                tiles
                sourceSentence
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("player-season")
    }

    private var heading: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .bottom, spacing: 12) {
                title
                Spacer(minLength: 12)
                control().frame(maxWidth: 170)
            }
            VStack(alignment: .leading, spacing: 12) {
                title
                control()
            }
        }
    }

    private var title: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(kicker.uppercased())
                .font(AcademyType.mono(11, relativeTo: .caption))
                .tracking(1.9)
                .foregroundStyle(AcademyColors.secondaryText)
            Text(seasonLabel)
                .font(AcademyType.serif(40, relativeTo: .title))
                .foregroundStyle(AcademyColors.text)
                .accessibilityIdentifier("player-season-title")
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(kicker), \(seasonLabel) totals")
        .accessibilityAddTraits(.isHeader)
    }

    private func notice(_ problem: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(problem)
                .font(AcademyType.ui(15, relativeTo: .callout))
                .foregroundStyle(AcademyColors.text)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("season-error-text")
            if let onRetry {
                Button("Try again", action: onRetry)
                    .buttonStyle(FloodlightPillStyle(variant: .outline))
                    .accessibilityIdentifier("season-retry")
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AcademyColors.cardSurface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(AcademyColors.warn, lineWidth: 1) }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("season-error")
    }

    private var empty: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(loading ? "Loading the season…" : truncated ? "This season is not shown here" : "No matches recorded yet")
                .font(AcademyType.serif(32, relativeTo: .title2))
                .foregroundStyle(AcademyColors.text)
                .fixedSize(horizontal: false, vertical: true)
            if !loading {
                Text(truncated
                    ? "Only the most recent seasons of a very long record are listed."
                    : "Nothing has been entered for \(seasonLabel). When the club confirms a match, or \(playerName) adds one, it appears here with where it came from.")
                    .font(AcademyType.ui(15, relativeTo: .callout))
                    .foregroundStyle(AcademyColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 32)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .top) { Rectangle().fill(AcademyColors.hairline).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(AcademyColors.hairline).frame(height: 1) }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(loading ? "season-loading" : "season-empty")
    }

    @ViewBuilder
    private var tiles: some View {
        if let lead = summary.tiles.first {
            let rest = Array(summary.tiles.dropFirst())
            VStack(spacing: 10) {
                leadTile(lead)
                if !rest.isEmpty {
                    if dynamicTypeSize.isAccessibilitySize {
                        ForEach(rest) { smallTile($0) }
                    } else {
                        HStack(alignment: .top, spacing: 10) {
                            ForEach(rest) { smallTile($0) }
                        }
                        .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    private func leadTile(_ tile: SeasonTile) -> some View {
        let main = VStack(alignment: .leading, spacing: 12) {
            tileLabel(tile.label, color: AcademyColors.onClub)
            Text(tile.value)
                .displayNumeral(tile.key == "minutes" ? 104 : 72)
                .monospacedDigit()
                .foregroundStyle(tile.quiet ? AcademyColors.onClub : AcademyColors.chalk)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
        }
        let meter = VStack(alignment: .leading, spacing: 8) {
            if let share = tile.share {
                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule().fill(AcademyColors.chalk.opacity(0.18))
                        Capsule().fill(colors.accent).frame(width: proxy.size.width * share)
                    }
                }
                .frame(height: 6)
            }
            if let note = tile.note {
                Text(note)
                    .font(AcademyType.ui(13, relativeTo: .footnote))
                    .foregroundStyle(AcademyColors.onClub)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        return Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 16) { main; meter }
            } else {
                HStack(alignment: .bottom, spacing: 16) {
                    main
                    Spacer(minLength: 0)
                    meter.frame(width: 150)
                }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(colors.primary, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken(tile))
        .accessibilityIdentifier("season-tile-\(tile.key)")
    }

    private func smallTile(_ tile: SeasonTile) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            tileLabel(tile.shortLabel, color: AcademyColors.secondaryText)
            Text(tile.value)
                .displayNumeral(tile.word ? 30 : 52)
                .monospacedDigit()
                .foregroundStyle(tile.quiet ? AcademyColors.quiet : AcademyColors.text)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
                .padding(.top, tile.word ? 14 : 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(AcademyColors.cardSurface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(AcademyColors.hairline, lineWidth: 1) }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken(tile))
        .accessibilityIdentifier("season-tile-\(tile.key)")
    }

    private func spoken(_ tile: SeasonTile) -> String {
        [tile.label, tile.spokenValue, tile.note].compactMap { $0 }.joined(separator: ", ")
    }

    private func tileLabel(_ text: String, color: Color) -> some View {
        Text(text.uppercased())
            .font(AcademyType.mono(10, relativeTo: .caption2))
            .tracking(1.4)
            .foregroundStyle(color)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
    }

    @ViewBuilder
    private var sourceSentence: some View {
        if let sentence = summary.sentence {
            let rating = summary.avgRating.map {
                " Average rating \($0.formatted(.number.precision(.fractionLength(0 ... 2))))."
            } ?? ""
            let full = sentence + rating + (truncated ? " Only the most recent seasons are listed." : "")
            HStack(alignment: .top, spacing: 10) {
                if summary.confirmed {
                    ConfirmedTick(size: 18).padding(.top, 1)
                }
                Text(full)
                    .font(AcademyType.ui(14, relativeTo: .subheadline))
                    .foregroundStyle(AcademyColors.strongSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(full)
            .accessibilityIdentifier("season-source")
        }
    }
}

extension PlayerSeasonBlock where Control == EmptyView {
    init(
        seasonLabel: String, kicker: String = "This season", summary: SeasonSummary,
        playerName: String = "this player", loading: Bool = false, problem: String? = nil,
        onRetry: (() -> Void)? = nil, truncated: Bool = false
    ) {
        self.init(
            seasonLabel: seasonLabel, kicker: kicker, summary: summary, playerName: playerName,
            loading: loading, problem: problem, onRetry: onRetry, truncated: truncated,
            control: { EmptyView() }
        )
    }
}

/// One card per match. Where the club has confirmed, the club's figures are shown.
struct PlayerMatchLinesSection: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let lines: [PlayerMatchLine]
    var goalkeeper = false
    var colors = PlayerClubColors.standard
    @State private var showAll = false

    private var canCollapse: Bool { lines.count > PlayerCardText.matchLinesPreview + 2 }

    private var visible: [PlayerMatchLine] {
        canCollapse && !showAll ? Array(lines.prefix(PlayerCardText.matchLinesPreview)) : lines
    }

    var body: some View {
        if !lines.isEmpty {
            VStack(alignment: .leading, spacing: 16) {
                Text("Match by match")
                    .font(AcademyType.serif(32, relativeTo: .title2))
                    .foregroundStyle(AcademyColors.text)
                    .accessibilityAddTraits(.isHeader)

                LazyVStack(spacing: 12) {
                    ForEach(visible) { line in
                        card(line)
                    }
                }

                if canCollapse {
                    Button(showAll
                        ? "Show the latest \(PlayerCardText.matchLinesPreview)"
                        : "Show all \(lines.count) matches") {
                        showAll.toggle()
                    }
                    .buttonStyle(FloodlightPillStyle(variant: .outline))
                    .frame(maxWidth: .infinity)
                    .accessibilityIdentifier("match-lines-more")
                }

                Text("One card per match. Where the club has confirmed, the club's figures are shown.")
                    .font(AcademyType.ui(13, relativeTo: .footnote))
                    .foregroundStyle(AcademyColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("match-lines")
        }
    }

    private func card(_ line: PlayerMatchLine) -> some View {
        let date = PlayerCardText.matchDateParts(line.matchDate)
        let venue = PlayerCardText.venueLabel(line.homeAway)
        let source = PlayerCardText.lineSource(line)
        let heading = VStack(alignment: .leading, spacing: 4) {
            Text(date.compact + (venue.map { " · \($0.uppercased())" } ?? ""))
                .font(AcademyType.mono(11, relativeTo: .caption))
                .tracking(1.4)
                .foregroundStyle(AcademyColors.secondaryText)
            Text(line.opponent ?? "Opponent not recorded")
                .font(AcademyType.ui(19, weight: .medium, relativeTo: .headline))
                .foregroundStyle(AcademyColors.text)
            if let competition = line.competition, !competition.isEmpty {
                Text(competition)
                    .font(AcademyType.ui(13, relativeTo: .footnote))
                    .foregroundStyle(AcademyColors.secondaryText)
            }
        }
        .fixedSize(horizontal: false, vertical: true)

        return VStack(alignment: .leading, spacing: 14) {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 10) { heading; result(line) }
            } else {
                HStack(alignment: .top, spacing: 12) {
                    heading
                    Spacer(minLength: 0)
                    result(line)
                }
            }
            minutes(line.minutes)
            VStack(alignment: .leading, spacing: 8) {
                Rectangle().fill(AcademyColors.hairline).frame(height: 1)
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .center, spacing: 12) {
                        summary(line)
                        Spacer(minLength: 0)
                        mark(source)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        summary(line)
                        mark(source)
                    }
                }
                .padding(.top, 4)
                if let detail = source.detail {
                    Text(detail)
                        .font(AcademyType.ui(13, relativeTo: .footnote))
                        .foregroundStyle(AcademyColors.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AcademyColors.cardSurface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(AcademyColors.hairline, lineWidth: 1) }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PlayerCardText.spokenLine(line, goalkeeper: goalkeeper))
        .accessibilityIdentifier("match-card")
        .accessibilityValue(line.selfReport?.rawValue ?? line.confirmation.rawValue)
    }

    private func summary(_ line: PlayerMatchLine) -> some View {
        Text(PlayerCardText.lineSummary(line, goalkeeper: goalkeeper))
            .font(AcademyType.ui(14, relativeTo: .subheadline))
            .foregroundStyle(AcademyColors.secondaryText)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func mark(_ source: MatchLineSource) -> some View {
        HStack(spacing: 6) {
            if source.confirmed {
                ConfirmedTick(size: 16)
            } else {
                Circle().stroke(AcademyColors.quietRule, lineWidth: 1.5).frame(width: 15, height: 15)
            }
            Text(source.mark)
                .font(AcademyType.ui(14, weight: .medium, relativeTo: .subheadline))
                .foregroundStyle(source.confirmed ? AcademyColors.good : AcademyColors.secondaryText)
                .lineLimit(1)
        }
        .fixedSize()
    }

    @ViewBuilder
    private func result(_ line: PlayerMatchLine) -> some View {
        if let result = PlayerCardText.matchResult(line) {
            HStack(spacing: 8) {
                Text(result.outcome)
                    .font(AcademyType.ui(13, weight: .semibold, relativeTo: .footnote))
                    .foregroundStyle(result.outcome == "D" ? AcademyColors.text : AcademyColors.background)
                    .frame(minWidth: 28, minHeight: 28)
                    .background {
                        switch result.outcome {
                        case "W": Circle().fill(AcademyColors.good)
                        case "L": Circle().fill(AcademyColors.text)
                        default: Circle().stroke(AcademyColors.quietRule, lineWidth: 1)
                        }
                    }
                Text(result.score)
                    .font(AcademyType.ui(17, weight: .medium, relativeTo: .body))
                    .monospacedDigit()
                    .foregroundStyle(AcademyColors.text)
            }
            .fixedSize()
        } else {
            Text("–")
                .font(AcademyType.ui(17, relativeTo: .body))
                .foregroundStyle(AcademyColors.quiet)
        }
    }

    private func minutes(_ value: Int?) -> some View {
        let played = max(0, value ?? 0)
        return HStack(spacing: 12) {
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(AcademyColors.adaptive(light: 0xECE8DD, dark: 0x27302C))
                    Capsule().fill(barFill)
                        .frame(width: proxy.size.width * PlayerCardText.minutesShare(played))
                }
            }
            .frame(height: 8)
            Text("\(played)′")
                .font(AcademyType.ui(16, weight: .medium, relativeTo: .callout))
                .monospacedDigit()
                .foregroundStyle(played == 0 ? AcademyColors.quiet : AcademyColors.text)
        }
    }

    /// Club green reads on chalk; on night the bar takes the accent so it stays visible.
    private var barFill: Color {
        colors == .standard ? AcademyColors.adaptive(light: 0x0F3D2E, dark: 0xCFAE62) : colors.primary
    }
}
