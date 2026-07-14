import SwiftUI

enum AcademyColors {
    static let claret = Color(red: 122 / 255, green: 38 / 255, blue: 58 / 255)
    static let claretSoft = Color(red: 122 / 255, green: 38 / 255, blue: 58 / 255).opacity(0.12)
    static let background = Color(uiColor: .systemGroupedBackground)
    static let surface = Color(uiColor: .secondarySystemGroupedBackground)
    static let separator = Color(uiColor: .separator)
}

struct BadgeView: View {
    let text: String
    var foregroundColor: Color = AcademyColors.claret
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
