# Floodlight fonts

Bundled locally and registered through `project.yml` → `Info.plist` → `UIAppFonts`.
No remote font request is needed. All `AcademyType` methods use `relativeTo:` for
Dynamic Type. Serif uses genuine regular/italic faces; UI and metadata use the
Geist and Geist Mono variable faces with SwiftUI weight selection.

Official source: [Google Fonts repository](https://github.com/google/fonts).

- [Instrument Serif](https://github.com/google/fonts/tree/main/ofl/instrumentserif): regular and italic TTFs, `InstrumentSerif/InstrumentSerif-OFL.txt`.
- [Geist](https://github.com/google/fonts/tree/main/ofl/geist): variable TTF, `Geist/Geist-OFL.txt`.
- [Geist Mono](https://github.com/google/fonts/tree/main/ofl/geistmono): variable TTF, `GeistMono/GeistMono-OFL.txt`.

Each family is licensed under SIL Open Font License 1.1; its unmodified licence
and copyright notice are next to the font files.
