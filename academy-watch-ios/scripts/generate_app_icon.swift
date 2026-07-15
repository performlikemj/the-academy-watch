#!/usr/bin/env swift

import AppKit
import Foundation

let canvasSize = 1024
let scriptURL = URL(fileURLWithPath: #filePath)
let projectRoot = scriptURL.deletingLastPathComponent().deletingLastPathComponent()
let outputURL = projectRoot
    .appendingPathComponent("AcademyWatch/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png")

guard let context = CGContext(
    data: nil,
    width: canvasSize,
    height: canvasSize,
    bitsPerComponent: 8,
    bytesPerRow: canvasSize * 4,
    space: CGColorSpace(name: CGColorSpace.sRGB)!,
    bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
) else {
    fatalError("Unable to create the app-icon canvas")
}

context.setShouldAntialias(true)
context.setFillColor(
    red: 122 / 255,
    green: 38 / 255,
    blue: 58 / 255,
    alpha: 1
)
context.fill(CGRect(x: 0, y: 0, width: canvasSize, height: canvasSize))

context.setStrokeColor(red: 1, green: 1, blue: 1, alpha: 1)
context.setLineCap(.round)
context.setLineJoin(.round)

// Shield outline.
context.setLineWidth(30)
context.move(to: CGPoint(x: 206, y: 786))
context.addLine(to: CGPoint(x: 512, y: 892))
context.addLine(to: CGPoint(x: 818, y: 786))
context.addLine(to: CGPoint(x: 770, y: 342))
context.addLine(to: CGPoint(x: 512, y: 132))
context.addLine(to: CGPoint(x: 254, y: 342))
context.closePath()
context.strokePath()

// Geometric AW monogram avoids font dependencies and renders deterministically.
context.setLineWidth(54)
context.move(to: CGPoint(x: 286, y: 342))
context.addLine(to: CGPoint(x: 402, y: 674))
context.addLine(to: CGPoint(x: 518, y: 342))
context.move(to: CGPoint(x: 334, y: 478))
context.addLine(to: CGPoint(x: 470, y: 478))

context.move(to: CGPoint(x: 528, y: 674))
context.addLine(to: CGPoint(x: 588, y: 342))
context.addLine(to: CGPoint(x: 650, y: 520))
context.addLine(to: CGPoint(x: 714, y: 342))
context.addLine(to: CGPoint(x: 776, y: 674))
context.strokePath()

try FileManager.default.createDirectory(
    at: outputURL.deletingLastPathComponent(),
    withIntermediateDirectories: true
)
guard let image = context.makeImage() else {
    fatalError("Unable to render the app icon")
}
let bitmap = NSBitmapImageRep(cgImage: image)
guard let png = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("Unable to encode the app icon as PNG")
}
try png.write(to: outputURL, options: .atomic)
print("Wrote \(outputURL.path)")
