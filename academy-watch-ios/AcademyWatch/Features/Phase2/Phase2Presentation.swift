import SwiftUI

// Editorial treatments shared by the actual screens and review captures.
struct Phase2Eyebrow: View {
    let text: String
    var gold = false
    var body: some View {
        Text(text.uppercased()).font(AcademyType.mono(10)).tracking(1.4)
            .foregroundStyle(gold ? AcademyColors.accent : AcademyColors.secondaryText)
            .fixedSize(horizontal: false, vertical: true)
    }
}
struct Phase2Section: View {
    let title: String
    var trailing = ""
    var body: some View {
        VStack(spacing: 9) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(AcademyType.serif(26))
                Spacer(minLength: 8)
                Phase2Eyebrow(text: trailing)
            }
            Rectangle().fill(AcademyColors.text).frame(height: 1)
        }
    }
}
struct Phase2Chip: View {
    let title: String
    var selected = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(title).font(AcademyType.ui(14, weight: .medium))
                .padding(.horizontal, 16).frame(minHeight: 40)
                .background(selected ? AcademyColors.text : AcademyColors.background, in: Capsule())
                .foregroundStyle(selected ? AcademyColors.background : AcademyColors.text)
                .overlay(Capsule().stroke(selected ? .clear : AcademyColors.hairline, lineWidth: 1))
                .frame(minHeight: 44)
        }.buttonStyle(.plain).accessibilityAddTraits(selected ? .isSelected : [])
    }
}
struct Phase2Chips: View {
    let choices: [(String, String)]
    @Binding var selection: String
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(choices, id: \.0) { key, label in
                    Phase2Chip(title: label, selected: selection == key) { selection = key }
                }
            }
        }
    }
}
struct Phase2Avatar: View {
    let name: String
    var size: CGFloat = 44
    var body: some View {
        Text(name.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined())
            .font(AcademyType.serif(size * 0.42)).frame(width: size, height: size)
            .background(AcademyColors.elevatedSurface, in: Circle())
            .accessibilityHidden(true)
    }
}
struct Phase2FormCard<Content: View>: View {
    @ViewBuilder let content: () -> Content
    var body: some View {
        VStack(alignment: .leading, spacing: 10, content: content).padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(AcademyColors.hairline, lineWidth: 1))
    }
}
struct Phase2InputStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration.textFieldStyle(.plain).font(AcademyType.body).padding(13).frame(minHeight: 44)
            .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(AcademyColors.hairline, lineWidth: 1))
    }
}
struct Phase2DateControl: View {
    @Binding var date: Date
    let zone: TimeZone
    var timeOnly = false
    var range: ClosedRange<Date> = Phase2Time.now...Phase2Time.now.addingTimeInterval(90 * 86400)
    @State private var presented = false
    private var formatted: String {
        let formatter = DateFormatter()
        formatter.locale = .current
        formatter.timeZone = zone
        formatter.setLocalizedDateFormatFromTemplate(timeOnly ? "jmm" : "EEE d MMM yyyy")
        return formatter.string(from: date)
    }
    var body: some View {
        Button {
            presented = true
        } label: {
            Text(formatted).font(AcademyType.subheadline).frame(maxWidth: .infinity, alignment: .leading)
                .padding(13).frame(minHeight: 44)
                .background(AcademyColors.elevatedSurface, in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(AcademyColors.hairline, lineWidth: 1))
        }.buttonStyle(.plain).accessibilityLabel(timeOnly ? "Trial time" : "Trial date")
            .accessibilityValue(formatted)
            .sheet(isPresented: $presented) {
                NavigationStack {
                    VStack {
                        if timeOnly {
                            DatePicker(
                                "Trial time", selection: $date, in: range, displayedComponents: .hourAndMinute
                            )
                            .datePickerStyle(.wheel)
                        } else {
                            DatePicker(
                                "Trial date", selection: $date, in: range, displayedComponents: .date
                            ).datePickerStyle(.graphical)
                        }
                        Phase2Eyebrow(text: zone.identifier)
                    }.padding(16).environment(\.timeZone, zone)
                        .navigationTitle(timeOnly ? "Trial time" : "Trial date")
                        .toolbar {
                            ToolbarItem(placement: .confirmationAction) {
                                Button("Done") { presented = false }
                            }
                        }
                }.presentationDetents([.medium, .large])
            }
    }
}
/// Wraps squad chips without horizontal scrolling or shrinking their touch targets.
struct Phase2Flow: Layout {
    var spacing: CGFloat = 6
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(width: proposal.width ?? 390, subviews: subviews).size
    }
    func placeSubviews(
        in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()
    ) {
        let result = arrange(width: bounds.width, subviews: subviews)
        for (index, position) in result.points.enumerated() {
            subviews[index].place(
                at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y),
                proposal: .unspecified)
        }
    }
    private func arrange(width: CGFloat, subviews: Subviews) -> (size: CGSize, points: [CGPoint]) {
        var x: CGFloat = 0
        var y: CGFloat = 0
        var row: CGFloat = 0
        var points: [CGPoint] = []
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > width {
                x = 0
                y += row + spacing
                row = 0
            }
            points.append(CGPoint(x: x, y: y))
            x += size.width + spacing
            row = max(row, size.height)
        }
        return (CGSize(width: width, height: y + row), points)
    }
}
struct Phase2ChipToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            HStack(spacing: 5) {
                if configuration.isOn { Image(systemName: "checkmark").font(.system(size: 11)) }
                configuration.label.font(AcademyType.ui(13))
            }.padding(.horizontal, 12).frame(height: 34)
                .background(
                    configuration.isOn ? AcademyColors.text : AcademyColors.background, in: Capsule()
                )
                .foregroundStyle(configuration.isOn ? AcademyColors.background : AcademyColors.text)
                .overlay(
                    Capsule().stroke(configuration.isOn ? .clear : AcademyColors.hairline, lineWidth: 1)
                ).frame(
                    minHeight: 44)
        }.buttonStyle(.plain).accessibilityRepresentation {
            Toggle(isOn: configuration.$isOn) { configuration.label }
        }
    }
}
struct Phase2LocationToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            configuration.label.font(AcademyType.ui(13)).padding(.horizontal, 14).frame(height: 36)
                .foregroundStyle(configuration.isOn ? AcademyColors.background : AcademyColors.text)
                .background(configuration.isOn ? AcademyColors.text : .clear, in: Capsule())
                .overlay(
                    Capsule().stroke(configuration.isOn ? .clear : AcademyColors.hairline, lineWidth: 1)
                )
                .frame(minHeight: 44)
        }.buttonStyle(.plain).accessibilityRepresentation {
            Toggle(isOn: configuration.$isOn) { configuration.label }
        }
    }
}
struct Phase2CheckboxStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            HStack(alignment: .center, spacing: 10) {
                Image(systemName: configuration.isOn ? "checkmark.square.fill" : "square")
                    .font(.system(size: 22, weight: .light)).foregroundStyle(AcademyColors.text)
                configuration.label.font(AcademyType.subheadline).multilineTextAlignment(.leading)
            }.frame(minHeight: 44).frame(maxWidth: .infinity, alignment: .leading).contentShape(
                Rectangle())
        }.buttonStyle(.plain).accessibilityRepresentation {
            Toggle(isOn: configuration.$isOn) { configuration.label }
        }
    }
}
struct Phase2EmptyState: View {
    let title: String
    let detail: String
    let icon: String
    var eyebrow = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Image(systemName: icon).font(.system(size: 26, weight: .light))
                .foregroundStyle(AcademyColors.accent).frame(width: 64, height: 64)
                .background(AcademyColors.elevatedSurface, in: Circle())
            if !eyebrow.isEmpty { Phase2Eyebrow(text: eyebrow) }
            // The final word carries the approved gold italic accent.
            (Text(title.hasSuffix("yet.") ? String(title.dropLast(4)) : title)
                .font(AcademyType.serif(40))
                + Text(title.hasSuffix("yet.") ? "yet." : "")
                .font(AcademyType.serif(40, italic: true)).foregroundColor(AcademyColors.accent))
                .fixedSize(horizontal: false, vertical: true).accessibilityLabel(title)
            Text(detail).font(AcademyType.body).foregroundStyle(AcademyColors.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        }.padding(.vertical, 28).frame(maxWidth: .infinity, alignment: .leading)
    }
}
struct Phase2Status: View {
    let application: Phase2Application
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(application.statusLabel.uppercased()).font(AcademyType.mono(9)).tracking(1)
                .foregroundStyle(color)
        }.fixedSize(horizontal: false, vertical: true)
    }
    private var color: Color {
        application.status == "invited" || application.status == "offer"
            ? AcademyColors.accent
            : application.status == "signed" ? AcademyColors.good : AcademyColors.secondaryText
    }
}
struct Phase2Fact: View {
    let label: String
    let value: String
    var zone: String? = nil
    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                Phase2Eyebrow(text: label).frame(width: 66, alignment: .leading).padding(.top, 3)
                VStack(alignment: .leading, spacing: 5) {
                    Text(value).font(AcademyType.subheadline)
                    if let zone { Phase2Eyebrow(text: zone) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.padding(.vertical, 8)
            Divider().overlay(AcademyColors.hairline)
        }
    }
}
struct Phase2ClubCrest: View {
    let name: String
    let brand: ClubBrand?
    var size: CGFloat = 46
    var body: some View {
        ZStack {
            Shield().fill(phase2BrandColor(brand?.primaryColor, fallback: AcademyColors.club))
            Shield().stroke(
                phase2BrandColor(brand?.accentColor, fallback: AcademyColors.gold), lineWidth: 2)
            Text(name.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined())
                .font(AcademyType.serif(size * 0.38)).foregroundStyle(
                    phase2BrandColor(brand?.accentColor, fallback: AcademyColors.gold))
        }.frame(width: size, height: size * 1.12).accessibilityHidden(true)
    }
    private struct Shield: Shape {
        func path(in r: CGRect) -> Path {
            Path { p in
                p.move(to: CGPoint(x: r.midX, y: 0))
                p.addLine(to: CGPoint(x: r.maxX, y: r.height * 0.14))
                p.addLine(to: CGPoint(x: r.maxX, y: r.height * 0.53))
                p.addQuadCurve(
                    to: CGPoint(x: r.midX, y: r.maxY), control: CGPoint(x: r.maxX, y: r.height * 0.84))
                p.addQuadCurve(
                    to: CGPoint(x: 0, y: r.height * 0.53), control: CGPoint(x: 0, y: r.height * 0.84))
                p.addLine(to: CGPoint(x: 0, y: r.height * 0.14))
                p.closeSubpath()
            }
        }
    }
}
func phase2BrandColor(_ raw: String?, fallback: Color) -> Color {
    guard let raw, raw.hasPrefix("#"), raw.count == 7, let hex = UInt32(raw.dropFirst(), radix: 16)
    else {
        return fallback
    }
    return Color(hex: hex)
}
func phase2Count(_ count: Int, _ singular: String, plural: String? = nil) -> String {
    "\(count) \(count == 1 ? singular : plural ?? singular + "s")"
}
extension Phase2Time {
    static func calendarDate(_ raw: String) -> String {
        let parser = DateFormatter()
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.timeZone = TimeZone(secondsFromGMT: 0)
        parser.dateFormat = "yyyy-MM-dd"
        guard let date = parser.date(from: raw) else { return "Date unavailable" }
        let formatter = DateFormatter()
        formatter.locale = .current
        formatter.timeZone = parser.timeZone
        formatter.setLocalizedDateFormatFromTemplate("EEE d MMM yyyy")
        return formatter.string(from: date)
    }
    static func conversationDate(_ raw: String?, zone: TimeZone = .current, format: String = "EEE d MMM") -> String {
        shortDate(raw, zone: zone.identifier, format: format)
    }
    static func shortDate(_ raw: String?, zone value: String, format: String = "EEE d MMM") -> String {
        guard let date = date(raw) else { return "No fixed date" }
        let formatter = DateFormatter()
        formatter.locale = .current
        formatter.timeZone = zone(value)
        formatter.setLocalizedDateFormatFromTemplate(format)
        return formatter.string(from: date)
    }
}

enum Phase2ReviewCapture {
    static var isActive: Bool {
        #if DEBUG && targetEnvironment(simulator)
            return Phase2Fixtures.active && ProcessInfo.processInfo.arguments.contains("-reviewCapture")
        #else
            return false
        #endif
    }
}
