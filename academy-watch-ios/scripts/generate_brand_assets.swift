#!/usr/bin/env swift

import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

private let sourceCrop = CGRect(x: 98, y: 104, width: 304, height: 304)
private let launchBackground = (red: 28, green: 28, blue: 28)
private let launchPointSize = 200
private let extractionDeadband = 8

private let scriptURL = URL(fileURLWithPath: #filePath)
private let projectRoot = scriptURL.deletingLastPathComponent().deletingLastPathComponent()
private let workspaceRoot = projectRoot.deletingLastPathComponent()
private let sourceURL = workspaceRoot
    .appendingPathComponent("academy-watch-frontend/public/assets/loan_army_assets/favicon-512x512.png")
private let assetCatalogURL = projectRoot.appendingPathComponent("AcademyWatch/Assets.xcassets")
private let appIconURL = assetCatalogURL
    .appendingPathComponent("AppIcon.appiconset/AppIcon-1024.png")
private let launchAssetURL = assetCatalogURL.appendingPathComponent("LaunchBoot.imageset")

private enum AssetError: Error, CustomStringConvertible {
    case unableToLoadSource(String)
    case invalidSourceSize(Int, Int)
    case unableToCrop
    case unableToCreateContext
    case unableToCreateImage
    case unableToCreateDestination(String)
    case unableToWrite(String)
    case missingPreviewPath

    var description: String {
        switch self {
        case let .unableToLoadSource(path):
            return "Unable to load brand source at \(path)"
        case let .invalidSourceSize(width, height):
            return "Expected a 512x512 brand source, got \(width)x\(height)"
        case .unableToCrop:
            return "Unable to crop the brand source"
        case .unableToCreateContext:
            return "Unable to create an sRGB bitmap context"
        case .unableToCreateImage:
            return "Unable to create a rendered image"
        case let .unableToCreateDestination(path):
            return "Unable to create a PNG destination at \(path)"
        case let .unableToWrite(path):
            return "Unable to write PNG data to \(path)"
        case .missingPreviewPath:
            return "--preview requires an output path"
        }
    }
}

private func loadSource() throws -> CGImage {
    guard
        let source = CGImageSourceCreateWithURL(sourceURL as CFURL, nil),
        let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
    else {
        throw AssetError.unableToLoadSource(sourceURL.path)
    }

    guard image.width == 512, image.height == 512 else {
        throw AssetError.invalidSourceSize(image.width, image.height)
    }
    return image
}

private func makeContext(size: Int, alphaInfo: CGImageAlphaInfo) throws -> CGContext {
    guard
        let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
        let context = CGContext(
            data: nil,
            width: size,
            height: size,
            bitsPerComponent: 8,
            bytesPerRow: size * 4,
            space: colorSpace,
            bitmapInfo: CGBitmapInfo.byteOrder32Big.rawValue | alphaInfo.rawValue
        )
    else {
        throw AssetError.unableToCreateContext
    }
    return context
}

private func renderOpaqueCrop(_ crop: CGImage, size: Int) throws -> CGImage {
    let context = try makeContext(size: size, alphaInfo: .noneSkipLast)
    context.interpolationQuality = .high
    context.draw(crop, in: CGRect(x: 0, y: 0, width: size, height: size))
    guard let image = context.makeImage() else {
        throw AssetError.unableToCreateImage
    }
    return image
}

private func renderTransparentLaunchMark(_ crop: CGImage, size: Int) throws -> CGImage {
    let sourceContext = try makeContext(size: size, alphaInfo: .premultipliedLast)
    sourceContext.interpolationQuality = .high
    sourceContext.draw(crop, in: CGRect(x: 0, y: 0, width: size, height: size))

    let outputContext = try makeContext(size: size, alphaInfo: .premultipliedLast)
    guard
        let sourceData = sourceContext.data?.assumingMemoryBound(to: UInt8.self),
        let outputData = outputContext.data?.assumingMemoryBound(to: UInt8.self)
    else {
        throw AssetError.unableToCreateContext
    }

    let backgroundLuma = (launchBackground.red + launchBackground.green + launchBackground.blue) / 3
    let lightFloor = backgroundLuma + extractionDeadband
    let darkCeiling = backgroundLuma - extractionDeadband

    for index in 0..<(size * size) {
        let offset = index * 4
        let red = Int(sourceData[offset])
        let green = Int(sourceData[offset + 1])
        let blue = Int(sourceData[offset + 2])
        let luma = (54 * red + 183 * green + 19 * blue) >> 8

        if luma > lightFloor {
            let alpha = UInt8(clamping: (luma - lightFloor) * 255 / (255 - lightFloor))
            outputData[offset] = alpha
            outputData[offset + 1] = alpha
            outputData[offset + 2] = alpha
            outputData[offset + 3] = alpha
        } else if luma < darkCeiling {
            let alpha = UInt8(clamping: (darkCeiling - luma) * 255 / darkCeiling)
            outputData[offset] = 0
            outputData[offset + 1] = 0
            outputData[offset + 2] = 0
            outputData[offset + 3] = alpha
        } else {
            outputData[offset] = 0
            outputData[offset + 1] = 0
            outputData[offset + 2] = 0
            outputData[offset + 3] = 0
        }
    }

    guard let image = outputContext.makeImage() else {
        throw AssetError.unableToCreateImage
    }
    return image
}

private func writePNG(_ image: CGImage, to url: URL) throws {
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    guard
        let destination = CGImageDestinationCreateWithURL(
            url as CFURL,
            UTType.png.identifier as CFString,
            1,
            nil
        )
    else {
        throw AssetError.unableToCreateDestination(url.path)
    }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else {
        throw AssetError.unableToWrite(url.path)
    }
}

private func previewURL() throws -> URL? {
    guard let flagIndex = CommandLine.arguments.firstIndex(of: "--preview") else {
        return nil
    }
    let pathIndex = CommandLine.arguments.index(after: flagIndex)
    guard CommandLine.arguments.indices.contains(pathIndex) else {
        throw AssetError.missingPreviewPath
    }
    let path = CommandLine.arguments[pathIndex]
    return URL(
        fileURLWithPath: path,
        relativeTo: URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    ).standardizedFileURL
}

do {
    let source = try loadSource()
    guard let crop = source.cropping(to: sourceCrop) else {
        throw AssetError.unableToCrop
    }

    let appIcon = try renderOpaqueCrop(crop, size: 1024)
    try writePNG(appIcon, to: appIconURL)

    for scale in 1...3 {
        let size = launchPointSize * scale
        let launchMark = try renderTransparentLaunchMark(crop, size: size)
        let suffix = scale == 1 ? "" : "@\(scale)x"
        try writePNG(launchMark, to: launchAssetURL.appendingPathComponent("LaunchBoot\(suffix).png"))
    }

    if let preview = try previewURL() {
        try writePNG(appIcon, to: preview)
        print("Wrote preview \(preview.path)")
    }

    print("Crop: left=98 top=104 width=304 height=304")
    print("Launch background: #1C1C1C")
    print("Wrote app icon \(appIconURL.path)")
    print("Wrote launch images \(launchAssetURL.path)")
} catch {
    FileHandle.standardError.write(Data("Brand asset generation failed: \(error)\n".utf8))
    exit(1)
}
