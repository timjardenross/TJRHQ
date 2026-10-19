# Font licences

Checked 2026-10-18 by reading the licence file shipped in each package (`@fontsource/<name>`, which
packages the upstream fonts with their original `LICENSE`).

| Font | Where it is used | Licence | Licence text read |
|---|---|---|---|
| Inter | Interface text (`font-sans`), loaded from Google Fonts in `globals.css`; also the source of the HQ wordmark outlines (weights 500 and 600) | SIL Open Font License 1.1 | Yes, `@fontsource/inter` 5.3.0 |
| JetBrains Mono | Code and numbers (`font-mono`), loaded from Google Fonts in `globals.css` | SIL OFL 1.1 | Yes, `@fontsource/jetbrains-mono` 5.3.0 |
| Source Serif 4 | Headings (`font-serif`), via `next/font/google` in `layout.tsx` | SIL OFL 1.1 | Yes, `@fontsource/source-serif-4` 5.3.1 |
| Montserrat | Source of the TJR wordmark outlines (weight 800) used in the shared brand family, not loaded by the HQ app | SIL OFL 1.1 | Yes, `@fontsource/montserrat` 5.3.0 |

## What OFL 1.1 allows, in plain terms
- Free to use, including commercially, in apps and websites, and to embed or bundle with software.
- Free to convert into other forms and to draw logo or wordmark artwork from the glyphs. HQ's marks
  are outlined paths generated from Inter and Montserrat (see `public/brand/README.md`).
- The font files themselves may not be sold on their own. If the files are redistributed
  (for example, committed to the repo for self-hosting), the copyright notice and the licence text
  must travel with them.
- Modified versions may not use a Reserved Font Name. HQ does not modify the fonts.

## How the fonts are served

All three app fonts are self-hosted: variable `.woff2` files (latin subset) from `@fontsource-variable/inter`
5.3.0, `@fontsource-variable/jetbrains-mono` 5.3.0 and `@fontsource-variable/source-serif-4` 5.3.1 are
committed in `src/app/fonts/` with each package's licence text beside them (`LICENSE-*.txt`), and
`src/app/layout.tsx` loads them through `next/font/local`. The browser makes no request to Google, and
neither does the build. (Until 2026-10-19 they came from `next/font/google`, which downloads at build time;
Vercel builds started failing in that loader. Until 2026-10-18 Inter and JetBrains Mono came from a Google
Fonts CSS `@import`.)

Nothing here needs a purchase or a separate agreement. This is a licence reading, not legal advice.
