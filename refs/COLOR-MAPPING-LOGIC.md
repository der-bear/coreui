# Color Mapping Logic

How we map hardcoded codebase colors to Figma design tokens.

## Goal

Replace the scattered hardcoded colors in the LeadExec codebase with the closest matching Figma design token, respecting **where** the color is used (text, background, border) and **hue compatibility** to prevent cross-family mismatches.

## Input Files

| File | Description |
|------|-------------|
| `leadexec-colors-figma.json` | Figma design token export. Structure: `Colors.modes.{Light,Dark}` with semantic tokens (`accent/primary`, `background/main`, `text+icons/neutral/high`, `border/neutral/solid`, etc.). Each token has `$value` (hex), `$scopes` (where it can be applied), and `$type: "color"`. |
| `leadexec-colors-audit.json` | Full codebase color audit. Every hardcoded color found across CSS/SCSS/LESS/HTML/JS/TS/CSHTML files, with occurrence counts, usage contexts (text, background, border, shadow, icon, other), source groups (core, custom, devextreme), CSS properties, and file locations. |

## Output

| File | Description |
|------|-------------|
| `color-mapping-report.json` | Token-first JSON. Each Figma token lists all codebase colors it replaces, grouped by usage context. Plus a separate section for shadow/other/rgba colors with CSS properties. All Figma tokens listed even with 0 matches. |
| `color-mapping-report.html` | Visual report. Loads the JSON. Token rows with swatches. Separate collapsible table for shadow/other/rgba. Light/Dark toggle. |

## Pipeline (`map_colors.py`)

### Step 1: Extract Figma Tokens

- Parse `leadexec-colors-figma.json`, walk the nested tree
- Only process **Light** and **Dark** modes (skip `Dark 2`, `Mode`)
- Skip variable references (`$value` starting with `{`)
- **Skip component-level tokens** — anything under `components/*` (tooltip, input, scroll, toolbar)
- **Skip alt tokens** — anything under `alt/*` (e.g. `alt/bg-table-row`). These are component-specific, not core design system tokens
- **Skip gradient tokens** — anything under `gradient/*`
- **Skip AI tokens** — any path with `ai` as a segment or prefix (e.g. `text+icons/ai/high`, `accent/ai`, `background/ai-subtle`). AI-specific tokens are excluded from color migration
- We focus on the core color scheme: `accent/*`, `background/*`, `text+icons/*`, `border/*`, `container/*`
- Map each token's `$scopes` to a context category:

| Figma Scope | Context |
|-------------|---------|
| `FRAME_FILL` | background |
| `SHAPE_FILL` | background |
| `TEXT_FILL` | text |
| `STROKE_COLOR` | border |
| `ALL_SCOPES` | all |

Result: ~53 Light tokens, ~55 Dark tokens.

### Step 2: Extract Audit Colors (for main matching)

- Parse `leadexec-colors-audit.json` → `hardcoded_usage` section
- **All hex and named colors** — `#fff`, `#321fdb`, `black`, `gray`, `brown`, `cyan`, `gold`, `magenta`, `pink`, etc.
- **No occurrence threshold** — all colors included regardless of how many times they appear
- **Exclude all `rgba()`, `rgb()`, `hsl()` values** — these are functional and often opacity-dependent (collected separately in Step 6)
- **Exclude `var()` references**, `transparent`, `inherit`, `currentColor`, `none`, `initial`, `unset`
- **Exclude `#rrggbbaa` with alpha < 20** (nearly transparent)
- Extended named color support: 50+ CSS named colors mapped to hex
- Each color carries: raw value, normalized hex, occurrence count, usage contexts (`{text: N, background: N, border: N, ...}`), source groups (`{core: N, custom: N, devextreme: N}`)

Result: ~2,135 colors.

### Step 3: Color Distance — Two-Stage LCh + CIEDE2000

Every codebase color is matched to Figma tokens using a **two-stage approach**: hue compatibility gate first, then CIEDE2000 ranking.

#### Color Space Pipeline

All colors are converted through:
1. **sRGB → Linear RGB** — inverse gamma (IEC 61966-2-1)
2. **Linear RGB → CIE XYZ** — sRGB D65 matrix
3. **XYZ → CIE L\*a\*b\*** — D65 illuminant reference white (0.95047, 1.0, 1.08883)
4. **L\*a\*b\* → LCh** — polar form: L (lightness), C (chroma = √(a²+b²)), h (hue = atan2(b,a))
5. **L\*a\*b\* × L\*a\*b\* → dE2000** — full CIEDE2000 formula for perceptual distance

LCh is the **perceptually uniform version of HSL** — same conceptual axes (lightness, saturation, hue) but computed in a perceptually uniform space. We use it for hue classification, and CIEDE2000 for final ranking.

#### Stage 1: Graduated Hue Gate

Pure CIEDE2000 can match colors with similar lightness/chroma but wrong hue families (e.g., dark teal → gray token, cyan → green). The hue gate prevents this.

**Chroma classification** — LCh chroma (`C*`) determines achromatic vs chromatic:
- **Achromatic** (gray): C* < 18 — catches pure grays and blue-grays like `#3c4b64` (C≈16), `#4f5d73` (C≈12)
- **Chromatic**: C* ≥ 18 — any color with noticeable hue

**Hue compatibility rules** (for a given gate width):

| Audit Color | Token | Compatible? |
|-------------|-------|-------------|
| Achromatic | Achromatic | Yes (grays match grays) |
| Chromatic | Chromatic, hue diff ≤ gate° | Yes (same hue family) |
| Chromatic | Chromatic, hue diff > gate° | **No** (wrong family) |
| Achromatic | Chromatic | **No** (don't mix gray + chromatic) |

**Graduated fallback** — instead of jumping from strict gate to "all tokens", we widen progressively:

| Step | Hue gate | Purpose |
|------|----------|---------|
| 1 | 30° | Strict hue family match |
| 2 | 50° | Adjacent family (e.g., cyan → green) |
| 3 | 70° | Broader reach (e.g., cyan → blue) |
| 4 | 90° | Wide catch (quarter of color wheel) |
| 5 | Same chroma class | Last resort fallback (achromatic→achromatic, chromatic→chromatic) |

This handles the **cyan/teal gap** in the Figma palette: there are no dedicated cyan tokens (success = green h≈147°, info = blue h≈285°), so cyans (h≈196°) can still reach green or blue via wider gates while avoiding neutral-family collapse.

#### Stage 2: CIEDE2000 Ranking + Max Distance Guard

Among hue-compatible candidates, the token with the lowest CIEDE2000 distance wins.

**Max distance guard**: if the best dE2000 exceeds **40**, the color is dropped entirely — no forced match. This prevents very poor matches from inflating token clusters.

**dE2000 interpretation** (stored in output):

| dE2000 | Meaning |
|--------|---------|
| 0 | Exact match |
| < 1 | Not perceptible by human eyes |
| 1–5 | Slight, barely noticeable |
| 5–15 | Noticeable difference |
| > 15 | Significant difference |
| > 40 | Rejected (no match) |

### Step 4: Strict Context Matching (core contexts only)

**Key rule: a token can only absorb colors used in the same context.**

Only **four core contexts** participate in token matching: `text`, `background`, `border`, `icon`. The `shadow` and `other` contexts are **excluded** from main matching and listed separately (see Step 6).

For each codebase color, we look at every core context it appears in independently. A color used as both text and background will be matched to the best text token for its text usages and the best background token for its background usages.

Matching rules — which tokens are eligible for each audit context:

| Codebase Usage | Eligible Token Contexts |
|----------------|------------------------|
| `text` | `text`, `all` |
| `background` | `background`, `all` |
| `border` | `border`, `all` |
| `icon` | `text`, `all` |

- A `text`-scoped token like `text+icons/neutral/on-accent` will **never** receive background colors
- A `FRAME_FILL`-scoped token like `background/main` will **never** receive text colors
- `shadow` and `other` contexts are **not matched to any token** — they go to the separate section

For each (color, context) pair:
1. Filter tokens by context eligibility
2. Try graduated hue gates (30° → 50° → 70° → 90°) until compatible tokens found
3. If none match, fallback to same chroma class (achromatic/chromatic) within context-eligible tokens
4. Pick the token with lowest CIEDE2000 among candidates
5. If best dE2000 > 40, reject the match (no good token exists)

### Step 5: Build Token-First Clusters

After matching, we invert the structure: instead of "color → best token", we produce "token → all colors".

For each token:
- Group matched colors by their usage context
- **Deduplicate by hex** within each context (same hex from multiple raw values like `#fff` and `white` → keep highest-occurrence entry)
- Sort colors within each context by dE (closest first)
- Report: `unique_colors`, `total_occurrences`, `by_context: { text: [...], background: [...], border: [...] }`
- **All Figma tokens are included** in the output, even those with 0 matching audit colors

#### Token Sort Order — Semantic Color Grouping

Tokens in the output are sorted by **semantic color group**, not by occurrence count. This groups related tokens together for easier visual scanning.

**Group order** (applied across all scope sections):

| Order | Group | Example tokens |
|-------|-------|----------------|
| 1 | neutral | `text+icons/neutral/high`, `background/main`, `background/secondary`, `container/header` |
| 2 | primary | `accent/primary`, `text+icons/primary/high`, `background/primary-subtle` |
| 3 | info | `accent/info`, `text+icons/info/high`, `border/info/solid` |
| 4 | success | `accent/success`, `text+icons/success/high`, `border/success/solid` |
| 5 | warning | `accent/warning`, `text+icons/warning/high`, `border/warning/solid` |
| 6 | danger | `accent/danger`, `text+icons/danger/high`, `border/danger/solid` |

**Variant order** within each group:

| Order | Variant | Description |
|-------|---------|-------------|
| 1 | high | Strongest contrast |
| 2 | medium* | Medium contrast |
| 3 | low | Subtle / low contrast |
| 4 | on-accent | Text on colored backgrounds |
| 5 | solid | Full-strength border/accent |
| 6 | subtle | Light background tints |

**Group detection rules:**
- `accent/{group}` → extract group from second segment (`accent/info` → info)
- `background/{group}-subtle` → extract group from suffix (`background/info-subtle` → info)
- `text+icons/{group}/...` → extract group from second segment
- `border/{group}/...` → extract group from second segment
- `background/main`, `background/secondary`, `background/tertiary` → neutral
- `container/*` → neutral
- Fallback: neutral

### Step 6: Separate Section — Shadow, Other & Functional Colors

Colors that don't participate in main token matching are collected into a dedicated `separate` array:

1. **Functional colors** (`rgba()`, `rgb()`, `hsl()`) — any context, all occurrences
2. **Hex/named colors with shadow or other usages** — only the shadow/other portion of their occurrences

Each entry includes:
- `color`: raw value as found in code
- `type`: `"functional"` or `"hex"`
- `occurrences`: count (for hex, only shadow+other occurrences)
- `contexts`: `{shadow: N, other: N, ...}`
- `properties`: CSS properties where the color is used (`{box-shadow: 43, -webkit-box-shadow: 19, ...}`)
- `groups`: source groups (`{core: N, custom: N, devextreme: N}`)

This ensures nothing is lost — shadow colors, rgba values, and "other" usages are all visible with their CSS property context, just not force-mapped to a design token.

## JSON Output Structure

```json
{
  "summary": {
    "mapped_colors": 2135,
    "light_tokens": 53,
    "dark_tokens": 55,
    "separate_colors": 1194
  },
  "light": [
    {
      "token": "text+icons/neutral/high",
      "hex": "#3c4b64",
      "scopes": ["SHAPE_FILL", "TEXT_FILL"],
      "token_contexts": ["background", "text"],
      "unique_colors": 175,
      "total_occurrences": 4527,
      "by_context": {
        "text": [
          {
            "color": "#333",
            "hex": "#333333",
            "de": 7.23,
            "occurrences": 451,
            "groups": {"core": 713, "custom": 41}
          }
        ],
        "background": [...]
      }
    }
  ],
  "dark": [...],
  "separate": [
    {
      "color": "rgba(0,0,0,.075)",
      "type": "functional",
      "occurrences": 44,
      "contexts": {"shadow": 43, "other": 1},
      "properties": {"box-shadow": 19, "-webkit-box-shadow": 19, ...},
      "groups": {"core": 32, "custom": 12}
    }
  ],
  "figma_palette": {
    "Light": [{"path": "...", "hex": "...", "scopes": [...]}],
    "Dark": [...]
  }
}
```

## HTML Viewer

- Loads `color-mapping-report.json` via `fetch()`
- **Token clusters** (main section):
  - Tokens grouped by scope: Background (FRAME_FILL), Text & Icons (TEXT_FILL), Border/Stroke (STROKE_COLOR), All Scopes
  - **Within each scope section**, tokens appear in semantic color group order: neutral → primary → info → success → warning → danger (preserves JSON sort order from Step 5)
  - Each row: **token swatch + name** on left → **row of color swatches** on right → **count**
  - **Swatches sorted by dE** (closest visual match first) within each token row
  - Hover any swatch for tooltip: color value, hex, dE distance, occurrences, source groups
  - All tokens shown, including those with 0 matches
- **Separate section** (below main):
  - Collapsible table of shadow/other/rgba colors
  - Columns: color swatch + value, type, occurrences, contexts, CSS properties (as tags), source groups
- Light/Dark toggle switches the token clusters view
- White page default

## Running

```bash
# Create venv if needed
python3 -m venv .venv && source .venv/bin/activate && pip install numpy

# Generate the JSON report
python3 refs/map_colors.py

# Open the HTML viewer
open refs/color-mapping-report.html
```
