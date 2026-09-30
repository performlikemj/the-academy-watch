import SwiftUI

struct SeasonPicker: View {
    let seasons: [Season]
    let selectedSeason: Int?
    let onSelect: (Int) -> Void

    private var selected: Season? {
        seasons.first { $0.season == selectedSeason }
    }

    var body: some View {
        Menu {
            ForEach(seasons) { season in
                Button {
                    onSelect(season.season)
                } label: {
                    HStack {
                        Text(menuLabel(for: season))
                            .foregroundStyle(season.hasRollup ? AcademyColors.text : AcademyColors.secondaryText)
                        if season.season == selectedSeason {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 7) {
                Image(systemName: "calendar")
                    .foregroundStyle(AcademyColors.accent)
                Text(selected?.label ?? "Season")
                    .lineLimit(1)
                if selected?.isCurrent == true {
                    Text("CURRENT")
                        .font(AcademyType.ui( 8, weight: .semibold))
                        .foregroundStyle(AcademyColors.secondaryText)
                }
                Spacer(minLength: 2)
                Image(systemName: "chevron.down")
                    .font(AcademyType.caption2.weight(.medium))
                    .foregroundStyle(AcademyColors.secondaryText)
            }
            .font(AcademyType.caption.weight(.medium))
            .padding(.horizontal, 11)
            .frame(maxWidth: .infinity, minHeight: 42)
            .background(AcademyColors.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(AcademyColors.separator.opacity(0.35), lineWidth: 0.5)
            }
        }
        .buttonStyle(.plain)
        .disabled(seasons.isEmpty)
        .accessibilityLabel("Season, \(selected?.label ?? "unavailable")")
        .accessibilityIdentifier("season-picker")
    }

    private func menuLabel(for season: Season) -> String {
        var details: [String] = []
        if season.isCurrent { details.append("current") }
        if !season.hasRollup { details.append("limited data") }
        guard !details.isEmpty else { return season.label }
        return "\(season.label) · \(details.joined(separator: ", "))"
    }
}
