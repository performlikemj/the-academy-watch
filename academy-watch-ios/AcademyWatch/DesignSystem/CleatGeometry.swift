import CoreGraphics
import Foundation

/// Verbatim N5F1 SVG paths. Shared with the static launch-vector generator.
enum CleatGeometry {
  static let upper =
    "M20 47 Q20 43 25 44 L29 46 Q38 52 45 44 L50 41 Q54 39 58 43 L67 50 Q82 57 112 57 Q125 58 129 64 Q132 69 125 71 Q96 75 70 73 L20 72 Q17 62 20 47 Z"
  static let accent = "M22 58 L33 58 L39 66 L21 65 Z"
  static let details = "M23 47 Q34 56 46 46 M49 48 L59 45 M55 52 L65 49 M63 55 L72 52 M71 58 L80 55"
  static let outline =
    "M20 47 Q20 43 25 44 L29 46 Q38 52 45 44 L50 41 Q54 39 58 43 L67 50 Q82 57 112 57 Q125 58 129 64 Q132 69 125 71 Q96 75 70 73 L20 72 Q17 62 20 47 Z M20 67 Q61 71 89 70 Q113 70 130 66 M20 72 L20 76 Q74 80 104 77 L127 73 L129 69 M25 77 L25 84 L32 84 L34 77 M47 78 L48 85 L55 85 L57 78 M72 79 L73 85 L80 85 L82 79 M97 78 L98 84 L105 84 L107 77 M118 75 L119 81 L125 81 L126 74"
  static let paths = [upper, outline, accent, details].map(makePath)
  static func makePath(_ source: String) -> CGPath {
    let tokens = source.replacingOccurrences(
      of: "([MLQZ])", with: " $1 ", options: .regularExpression
    )
    .split(whereSeparator: { $0.isWhitespace }).map(String.init)
    let path = CGMutablePath()
    var index = 0
    func number() -> Double {
      defer { index += 1 }
      return Double(tokens[index])!
    }
    while index < tokens.count {
      let command = tokens[index]
      index += 1
      switch command {
      case "M": path.move(to: CGPoint(x: number(), y: number()))
      case "L": path.addLine(to: CGPoint(x: number(), y: number()))
      case "Q":
        let control = CGPoint(x: number(), y: number())
        path.addQuadCurve(to: CGPoint(x: number(), y: number()), control: control)
      case "Z": path.closeSubpath()
      default: preconditionFailure("Unsupported checked-in cleat path command")
      }
    }
    return path
  }
}
