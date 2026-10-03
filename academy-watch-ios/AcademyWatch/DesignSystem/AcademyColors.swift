import SwiftUI

enum AcademyColors {
    static let night = Color(hex: 0x0B0E0D)
    static let ink = Color(hex: 0x0E1311)
    static let chalk = Color(hex: 0xF3F0E8)
    static let chalk2 = Color(hex: 0xECE8DD)
    static let muted = Color(hex: 0x5A6560)
    static let mutedDark = Color(hex: 0xA3ADA7)
    static let gold = Color(hex: 0xCFAE62)
    static let goldText = Color(hex: 0x84661F)
    static let club = Color(hex: 0x0F3D2E)
    static let good = adaptive(light: 0x1D5A40, dark: 0xF3F0E8)
    static let warn = Color(hex: 0xB7791F)
    static let warnText = adaptive(light: 0x0E1311, dark: 0xCFAE62)
    static let danger = adaptive(light: 0x9E3A31, dark: 0xF3F0E8)

    static let background = adaptive(light: 0xF3F0E8, dark: 0x0B0E0D)
    static let surface = background
    static let elevatedSurface = adaptive(light: 0xECE8DD, dark: 0x0E1311)
    static let text = adaptive(light: 0x0E1311, dark: 0xF3F0E8)
    static let secondaryText = adaptive(light: 0x5A6560, dark: 0xA3ADA7)
    // Shared BUS correction: gold-text meets small-text AA on chalk.
    static let accent = adaptive(light: 0x84661F, dark: 0xCFAE62)
    static let displayAccent = adaptive(light: 0x84661F, dark: 0xCFAE62)
    static let accentSoft = adaptive(light: 0xECE8DD, dark: 0x0E1311)
    static let primaryFill = text
    static let onPrimary = background
    static let hairline = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(hex: 0xF3F0E8).withAlphaComponent(0.16)
            : UIColor(hex: 0xD8D2C4)
    })
    static let separator = hairline

    // Player card. The web's card-only shades (`player-card.css`), once.
    /// Card surface, one step lighter than chalk. The standard card keeps it on night too.
    static let paper = Color(hex: 0xFBFAF6)
    static let cardSurface = adaptive(light: 0xFBFAF6, dark: 0x0E1311)
    /// Behind a photo while it loads.
    static let photoPlaceholder = Color(hex: 0xC8C2B3)
    static let heroPhotoPlaceholder = Color(hex: 0x8D877A)
    /// The one-liner on a (always light) card.
    static let cardBody = Color(hex: 0x4A544F)
    static let strongSecondary = adaptive(light: 0x3D4642, dark: 0xD6D2C7)
    /// Muted zero / en dash.
    static let quiet = adaptive(light: 0x8A8478, dark: 0x8A8F8B)
    static let quietRule = adaptive(light: 0xB9B2A2, dark: 0x5A6560)
    /// Secondary text on the club colour and over the hero scrim.
    static let onClub = Color(hex: 0xD9CFB4)
    static let onNight = Color(hex: 0xD6D2C7)
    /// The club-confirmed green on a light card, whatever the appearance.
    static let goodOnPaper = Color(hex: 0x1D5A40)

    // Compatibility for existing fixture/test clients. Production views use Floodlight names.
    static let claretForeground = accent
    static let claret = accent
    static let claretFill = primaryFill
    static let claretOnFill = onPrimary
    static let claretSoft = accentSoft
    static let academyBlue = secondaryText
    static let loanAmber = warn
    static let positiveGreen = good
    static let transitionPurple = secondaryText

    static func adaptive(light: UInt32, dark: UInt32) -> Color {
        Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light) })
    }
}

extension Color {
    init(hex: UInt32) { self.init(uiColor: UIColor(hex: hex)) }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(red: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255, blue: CGFloat(hex & 0xff) / 255, alpha: 1)
    }
}
