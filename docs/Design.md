# Design: Recon Investigator

Applies to the web UI and the HTML report. Both import the same tokens from
`recon/assets/tokens.css`. The report inlines the tokens so it stays a single
self-contained file. No external fonts, scripts, images or CDNs.

## 1. Principles

1. **Calm and trustworthy.** Finance users want clarity, not decoration.
2. **Facts and AI are visually separate.** Deterministic facts use neutral
   styling. AI-generated text always sits in the purple "AI" box with a
   verifier badge. A reader can always tell which is which.
3. **Evidence first.** Every finding shows its records and rule before the
   explanation.
4. **Numbers are easy to read.** Amounts are right-aligned with tabular
   numerals.
5. **Print-ready.** The report must print cleanly to A4.

## 2. Color tokens

```css
:root {
  --color-primary: #12355B;
  --color-primary-hover: #0E2A48;
  --color-accent: #0B7285;
  --color-bg: #F6F8FA;
  --color-surface: #FFFFFF;
  --color-border: #D8DEE6;
  --color-text: #1B2430;
  --color-text-muted: #5B6676;

  --color-success: #17694C;   --color-success-bg: #E5F4EE;
  --color-warning: #8A5300;   --color-warning-bg: #FFF3DC;
  --color-danger:  #B42318;   --color-danger-bg:  #FDECEA;
  --color-info:    #1D5FBF;   --color-info-bg:    #E8F0FC;
  --color-ai:      #5B3FB5;   --color-ai-bg:      #EFEAFB;
}
```

Contrast (WCAG ratios computed for these pairs): body text on background 14.7,
muted text on white 5.8, white on primary 12.5, accent on white 5.6, success on
its background 5.9, warning 5.8, danger 5.8, info 5.3, AI 6.3. All meet AA for
normal text.

Status mapping:

| Meaning | Color tokens |
|---|---|
| Matched (`match_*`) | success |
| Discrepancy, severity high | danger |
| Discrepancy, severity medium | warning |
| Discrepancy, severity low, `needs_review` | info |
| AI explanation, verified | ai |
| Deterministic fallback | neutral (muted text on `--color-bg`) |

## 3. Typography

System fonts only.

```css
--font-sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
--font-mono: ui-monospace, "SF Mono", Consolas, "Liberation Mono", monospace;
```

| Role | Size / line height | Weight |
|---|---|---|
| Page title | 28px / 36px | 700 |
| Section heading | 20px / 28px | 600 |
| Card heading | 16px / 24px | 600 |
| Body | 14px / 22px | 400 |
| Small, labels | 12px / 16px | 500, uppercase letter-spacing 0.04em for labels |
| Mono (IDs, JSON) | 13px / 20px | 400 |

Amounts and counts use `font-variant-numeric: tabular-nums` and are
right-aligned. IDs and references use the mono font.

## 4. Spacing, radius, elevation

- Spacing scale (4px base): 4, 8, 12, 16, 24, 32, 48.
- Radius: 6px (inputs, badges), 10px (cards).
- Elevation: cards use a 1px border and no shadow; modals and menus use
  `0 4px 16px rgba(18, 53, 91, 0.12)`.
- Layout: content max width 1120px in the UI and 960px in the report, centered.
  Report print margins 16mm. Page padding 24px (16px on narrow screens).

## 5. Components

| Component | Specification |
|---|---|
| Button | 40px high, 16px horizontal padding, radius 6px. Primary: primary background, white text. Secondary: white background, primary border and text. Disabled: 50% opacity, no pointer. Visible 2px focus ring in accent. |
| File drop zone | Dashed 2px border, radius 10px, 120px min height. States: idle, hover (accent border), file selected (success border, file name and size), error (danger border and message). Keyboard accessible. |
| Run stepper | Five steps: Parse, Normalize, Match, Investigate, Report. Current step in primary, done in success, pending in muted. |
| KPI card | Surface background, border, 16px padding. Large number (28px, 700), label (12px muted). Used for matched count, discrepancies, high severity, AI verified, fallbacks. |
| Status badge | Pill, 12px text, 4px vertical and 10px horizontal padding, color pair from the status mapping. |
| Data table | 40px rows, sticky header, bottom border only, row hover in background tint, amounts right-aligned, horizontal scroll container on small screens. |
| Finding card | Border, radius 10px. Header: finding ID (mono), type badge, severity badge. Body: two columns "Ledger" and "Bank" showing records; below, a rule line (rule id, version, plain-language description); then a facts grid (key and value pairs). Then the AI box. Then recommended action. Avoid page breaks inside a card when printing. |
| AI box | `--color-ai-bg` background, 3px left border in `--color-ai`, small label "AI explanation" with the verifier badge ("Verified" or "Deterministic fallback") and confidence. |
| Alert | Tinted background and matching text color from the status tokens, icon-free, 12px padding. |
| JSON or code block | Mono font, `--color-bg` background, border, horizontal scroll. |
| Empty state | Centered muted text and one primary action. |

## 6. Web UI layout

Single page. Header with the product name and a muted tagline ("Deterministic
matching. Verified AI explanations."). Below, in order: the two file drop
zones side by side (stacked on narrow screens), an optional collapsible
"Column mapping" section, the buttons "Run reconciliation" and "Load demo
data", the run stepper, then the results (KPI cards, findings table with
filters by type and severity, a link "Open audit report").

## 7. Report layout

1. Title block: product name, run id, generated timestamp, tool version.
2. Method statement (fixed text): "Matches and discrepancies in this report were
   decided by deterministic rules. AI-generated explanations were checked by an
   automated verifier; any explanation that failed verification was replaced by
   a deterministic fallback."
3. Summary: KPI cards and a table of counts by type.
4. Inputs: file names, SHA-256 hashes, row counts, validation issue counts.
5. Findings: grouped by severity, then type; one finding card each.
6. Matched items: compact table (collapsed by default in the UI, included in
   the printed report).
7. Appendix: configuration and config hash, rule versions, verifier statistics.

## 8. Accessibility and responsiveness

Semantic HTML (`header`, `main`, `section`, `table` with `th scope`), labels on
all inputs, visible focus, color never the only signal (badges always include
text), minimum touch target 40px, layouts reflow at 720px.

## 9. Print stylesheet

`@media print`: white background, hide buttons and filters, expand all
collapsed sections, `break-inside: avoid` on cards, 16mm margins, show link URLs
only for external links.
