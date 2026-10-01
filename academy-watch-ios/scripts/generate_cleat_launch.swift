import Foundation
import CoreGraphics

// Compile with DesignSystem/CleatGeometry.swift. The app logo assets stay unchanged.
@main struct GenerateCleatLaunch {
    static func main() {
        let target = URL(fileURLWithPath: CommandLine.arguments[1])
        var bounds = CGRect(x: 0, y: 0, width: 144, height: 96)
        let ctx = CGContext(target as CFURL, mediaBox: &bounds, nil)!
        ctx.beginPDFPage(nil)
        ctx.translateBy(x: 0, y: 96); ctx.scaleBy(x: 1, y: -1)
        ctx.setLineWidth(2); ctx.setLineCap(.round); ctx.setLineJoin(.round)
        let green = CGColor(red: 15/255, green: 61/255, blue: 46/255, alpha: 1)
        let chalk = CGColor(red: 243/255, green: 240/255, blue: 232/255, alpha: 1)
        ctx.setFillColor(green)
        ctx.addPath(CleatGeometry.paths[0]); ctx.fillPath()
        ctx.addPath(CleatGeometry.paths[2]); ctx.fillPath()
        ctx.setStrokeColor(chalk)
        ctx.addPath(CleatGeometry.paths[3]); ctx.strokePath()
        let dark = CommandLine.arguments.contains("dark")
        ctx.setStrokeColor(dark ? chalk : CGColor(red:14/255,green:19/255,blue:17/255,alpha:1))
        ctx.addPath(CleatGeometry.paths[1]); ctx.strokePath()
        ctx.endPDFPage(); ctx.closePDF()
    }
}
