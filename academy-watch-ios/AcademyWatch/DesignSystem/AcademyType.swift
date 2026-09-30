import SwiftUI

/// All custom fonts scale with the user's preferred content size.
enum AcademyType {
    static let largeTitle = serif(44, relativeTo: .largeTitle)
    static let title = serif(34, relativeTo: .title)
    static let title2 = serif(30, relativeTo: .title2)
    static let title3 = serif(26, relativeTo: .title3)
    static let headline = ui(16, weight: .semibold, relativeTo: .headline)
    static let body = ui(16, relativeTo: .body)
    static let callout = ui(15, relativeTo: .callout)
    static let subheadline = ui(14, relativeTo: .subheadline)
    static let footnote = ui(12, relativeTo: .footnote)
    static let caption = mono(11, relativeTo: .caption)
    static let caption2 = mono(10, relativeTo: .caption2)

    static func serif(_ size: CGFloat, italic: Bool = false, relativeTo style: Font.TextStyle = .title) -> Font {
        .custom(italic ? "InstrumentSerif-Italic" : "InstrumentSerif-Regular", size: size, relativeTo: style)
    }
    static func ui(_ size: CGFloat, weight: Font.Weight = .regular, relativeTo style: Font.TextStyle = .body) -> Font {
        .custom("Geist-Regular", size: size, relativeTo: style).weight(weight)
    }
    static func mono(_ size: CGFloat = 11, weight: Font.Weight = .regular, relativeTo style: Font.TextStyle = .caption) -> Font {
        .custom("GeistMono-Regular", size: size, relativeTo: style).weight(weight)
    }
}
