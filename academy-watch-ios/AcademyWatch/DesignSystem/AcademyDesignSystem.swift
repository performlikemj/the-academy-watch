import SwiftUI

enum AcademyColors {
    /// Claret used as text, icon, and unfilled-control foreground.
    /// The dark variant stays legible on all grouped-background elevations.
    static let claretForeground = adaptive(
        light: UIColor(red: 122 / 255, green: 38 / 255, blue: 58 / 255, alpha: 1),
        dark: UIColor(red: 255 / 255, green: 157 / 255, blue: 176 / 255, alpha: 1)
    )

    /// Deep brand claret for solid controls whose foreground is `claretOnFill`.
    static let claretFill = Color(red: 122 / 255, green: 38 / 255, blue: 58 / 255)
    static let claretOnFill = Color.white

    /// Low-emphasis surface paired with `claretForeground` for badges and winning values.
    static let claretSoft = adaptive(
        light: UIColor(red: 241 / 255, green: 229 / 255, blue: 232 / 255, alpha: 1),
        dark: UIColor(red: 59 / 255, green: 36 / 255, blue: 43 / 255, alpha: 1)
    )

    /// Semantic badge foregrounds remain legible over their own 12%-tinted grouped surfaces.
    static let academyBlue = adaptive(
        light: UIColor(red: 0 / 255, green: 87 / 255, blue: 184 / 255, alpha: 1),
        dark: UIColor(red: 121 / 255, green: 191 / 255, blue: 255 / 255, alpha: 1)
    )
    static let loanAmber = adaptive(
        light: UIColor(red: 138 / 255, green: 70 / 255, blue: 0 / 255, alpha: 1),
        dark: UIColor(red: 255 / 255, green: 182 / 255, blue: 110 / 255, alpha: 1)
    )
    static let positiveGreen = adaptive(
        light: UIColor(red: 0 / 255, green: 107 / 255, blue: 41 / 255, alpha: 1),
        dark: UIColor(red: 96 / 255, green: 217 / 255, blue: 138 / 255, alpha: 1)
    )
    static let transitionPurple = adaptive(
        light: UIColor(red: 118 / 255, green: 42 / 255, blue: 150 / 255, alpha: 1),
        dark: UIColor(red: 217 / 255, green: 164 / 255, blue: 245 / 255, alpha: 1)
    )

    // Existing foreground call sites inherit the accessible semantic variant.
    static let claret = claretForeground
    static let background = Color(uiColor: .systemGroupedBackground)
    static let surface = Color(uiColor: .secondarySystemGroupedBackground)
    static let separator = Color(uiColor: .separator)

    private static func adaptive(light: UIColor, dark: UIColor) -> Color {
        Color(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? dark : light
        })
    }
}

struct BadgeView: View {
    let text: String
    var foregroundColor: Color = AcademyColors.claretForeground
    var backgroundColor: Color = AcademyColors.claretSoft

    var body: some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .lineLimit(1)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .foregroundStyle(foregroundColor)
            .background(backgroundColor, in: Capsule())
            .accessibilityLabel(text)
    }
}
