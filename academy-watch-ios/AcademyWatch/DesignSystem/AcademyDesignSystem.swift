import SwiftUI

struct BadgeView: View {
    let text: String
    var foregroundColor: Color = AcademyColors.secondaryText
    var backgroundColor: Color = AcademyColors.accentSoft

    var body: some View {
        Text(text)
            .font(AcademyType.caption2.weight(.medium))
            .lineLimit(1)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .foregroundStyle(foregroundColor)
            .background(backgroundColor, in: Capsule())
            .accessibilityLabel(text)
    }
}
