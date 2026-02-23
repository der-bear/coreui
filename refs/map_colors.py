#!/usr/bin/env python3
"""
Map hardcoded codebase colors to Figma design tokens.

Token-first: each Figma token → all codebase hex/named colors it replaces.
Strict context: text tokens only match text colors, background → background, border → border.
Excludes: rgba() colors, component-level tokens (components/*, alt/*).
Shadow/other/rgba colors listed separately with CSS properties.
"""

import json
import math
import re
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

# ---------------------------------------------------------------------------
# Color parsing
# ---------------------------------------------------------------------------

NAMED_COLORS = {
    "white": "#ffffff", "black": "#000000", "red": "#ff0000",
    "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00",
    "orange": "#ffa500", "purple": "#800080", "gray": "#808080",
    "grey": "#808080", "silver": "#c0c0c0", "maroon": "#800000",
    "navy": "#000080", "teal": "#008080", "aqua": "#00ffff",
    "lime": "#00ff00", "olive": "#808000", "fuchsia": "#ff00ff",
    "brown": "#a52a2a", "cyan": "#00ffff", "gold": "#ffd700",
    "magenta": "#ff00ff", "pink": "#ffc0cb", "coral": "#ff7f50",
    "crimson": "#dc143c", "indigo": "#4b0082", "khaki": "#f0e68c",
    "plum": "#dda0dd", "salmon": "#fa8072", "tan": "#d2b48c",
    "tomato": "#ff6347", "turquoise": "#40e0d0", "violet": "#ee82ee",
    "wheat": "#f5deb3", "beige": "#f5f5dc", "ivory": "#fffff0",
    "lavender": "#e6e6fa", "linen": "#faf0e6", "orchid": "#da70d6",
    "peru": "#cd853f", "sienna": "#a0522d", "snow": "#fffafa",
    "chocolate": "#d2691e", "darkblue": "#00008b", "darkgray": "#a9a9a9",
    "darkgrey": "#a9a9a9", "darkgreen": "#006400", "darkred": "#8b0000",
    "lightblue": "#add8e6", "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3",
    "lightgreen": "#90ee90", "dimgray": "#696969", "dimgrey": "#696969",
    "transparent": None, "inherit": None, "currentcolor": None,
    "currentColor": None, "none": None, "initial": None, "unset": None,
}

def parse_hex(h: str):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        return (int(h[0]*2, 16), int(h[1]*2, 16), int(h[2]*2, 16), 255)
    if len(h) == 4:
        return (int(h[0]*2, 16), int(h[1]*2, 16), int(h[2]*2, 16), int(h[3]*2, 16))
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    if len(h) == 8:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
    return None

def parse_color_strict(raw: str):
    """Parse only #hex and named colors. Returns (r,g,b) or None."""
    s = raw.strip().lower()
    # Skip anything that's not hex or named
    if s.startswith("rgb") or s.startswith("hsl") or "var(" in s:
        return None
    if s in NAMED_COLORS:
        mapped = NAMED_COLORS[s]
        return parse_hex(mapped)[:3] if mapped else None
    if s.startswith("#"):
        parsed = parse_hex(s)
        if parsed and parsed[3] >= 20:  # skip nearly transparent
            return parsed[:3]
    return None


# ---------------------------------------------------------------------------
# Color math
# ---------------------------------------------------------------------------

def _srgb_to_linear(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def rgb_to_lab(r, g, b):
    lin = _srgb_to_linear(np.array([r, g, b], dtype=np.float64))
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = M @ lin
    xyz_n = xyz / np.array([0.95047, 1.00000, 1.08883])
    def f(t):
        d = 6.0 / 29.0
        return np.where(t > d**3, t ** (1.0/3.0), t / (3 * d**2) + 4.0/29.0)
    fxyz = f(xyz_n)
    return (float(116*fxyz[1]-16), float(500*(fxyz[0]-fxyz[1])), float(200*(fxyz[1]-fxyz[2])))

def delta_e_2000(lab1, lab2):
    L1, a1, b1 = lab1; L2, a2, b2 = lab2
    Lbar = (L1+L2)/2; C1 = math.sqrt(a1**2+b1**2); C2 = math.sqrt(a2**2+b2**2)
    Cbar = (C1+C2)/2; Cbar7 = Cbar**7
    G = 0.5*(1-math.sqrt(Cbar7/(Cbar7+25**7)))
    a1p = a1*(1+G); a2p = a2*(1+G)
    C1p = math.sqrt(a1p**2+b1**2); C2p = math.sqrt(a2p**2+b2**2); Cbarp = (C1p+C2p)/2
    h1p = math.degrees(math.atan2(b1,a1p))%360; h2p = math.degrees(math.atan2(b2,a2p))%360
    if abs(h1p-h2p)<=180: dhp=h2p-h1p
    elif h2p-h1p>180: dhp=h2p-h1p-360
    else: dhp=h2p-h1p+360
    dLp=L2-L1; dCp=C2p-C1p; dHp=2*math.sqrt(C1p*C2p)*math.sin(math.radians(dhp/2))
    if C1p*C2p==0: Hbarp=h1p+h2p
    elif abs(h1p-h2p)<=180: Hbarp=(h1p+h2p)/2
    elif h1p+h2p<360: Hbarp=(h1p+h2p+360)/2
    else: Hbarp=(h1p+h2p-360)/2
    T = (1-0.17*math.cos(math.radians(Hbarp-30))+0.24*math.cos(math.radians(2*Hbarp))
         +0.32*math.cos(math.radians(3*Hbarp+6))-0.20*math.cos(math.radians(4*Hbarp-63)))
    SL=1+0.015*(Lbar-50)**2/math.sqrt(20+(Lbar-50)**2); SC=1+0.045*Cbarp; SH=1+0.015*Cbarp*T
    Cbarp7=Cbarp**7
    RT=-2*math.sqrt(Cbarp7/(Cbarp7+25**7))*math.sin(math.radians(60*math.exp(-((Hbarp-275)/25)**2)))
    return math.sqrt((dLp/SL)**2+(dCp/SC)**2+(dHp/SH)**2+RT*(dCp/SC)*(dHp/SH))

# ---------------------------------------------------------------------------
# LCh (polar L*a*b*) and hue-gate matching
# ---------------------------------------------------------------------------

def lab_to_lch(lab):
    """Convert L*a*b* to LCh (Lightness, Chroma, Hue).
    L = lightness (0-100), C = chroma (saturation), h = hue angle (0-360°).
    """
    L, a, b = lab
    C = math.sqrt(a**2 + b**2)
    h = math.degrees(math.atan2(b, a)) % 360
    return (L, C, h)

# Chroma threshold below which a color is considered achromatic (gray).
# 18 catches blue-grays like #3c4b64 (C≈16) and #4f5d73 (C≈12) as achromatic.
ACHROMATIC_CHROMA = 18.0

# Maximum hue angle difference for two chromatic colors to be "compatible".
HUE_GATE_DEGREES = 30.0

def hue_angle_diff(h1, h2):
    """Smallest angle between two hue angles [0, 180]."""
    d = abs(h1 - h2) % 360
    return d if d <= 180 else 360 - d

def is_hue_compatible(lch_a, lch_b, gate_degrees=None):
    """Hue gate. Returns True if two colors can be matched.

    Rules:
    - Both achromatic (C < 18): always compatible (grays match grays)
    - Both chromatic (C >= 18): compatible if hue diff <= gate_degrees
    - Mixed achromatic/chromatic: NOT compatible
    """
    if gate_degrees is None:
        gate_degrees = HUE_GATE_DEGREES
    c_a, c_b = lch_a[1], lch_b[1]
    achro_a = c_a < ACHROMATIC_CHROMA
    achro_b = c_b < ACHROMATIC_CHROMA

    if achro_a and achro_b:
        return True  # both gray

    if not achro_a and not achro_b:
        # both chromatic — check hue angle
        return hue_angle_diff(lch_a[2], lch_b[2]) <= gate_degrees

    # one achromatic, one chromatic
    return False


def fallback_candidates_by_chroma(source_lch, ctx_eligible):
    """Fallback pool that preserves chroma class before relaxing.

    If hue-gated candidates are empty, avoid cross-family jumps by first trying
    tokens with the same achromatic/chromatic class as the source color.
    """
    source_is_chromatic = source_lch[1] >= ACHROMATIC_CHROMA
    if source_is_chromatic:
        same_class = [t for t in ctx_eligible if t["lch"][1] >= ACHROMATIC_CHROMA]
    else:
        same_class = [t for t in ctx_eligible if t["lch"][1] < ACHROMATIC_CHROMA]
    return same_class if same_class else ctx_eligible


# Graduated hue gate: try progressively wider gates before giving up
HUE_GATE_STEPS = (30, 50, 70, 90)

# Maximum dE2000 — anything above is "no good match"
MAX_DE = 40.0


def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# Figma token extraction
# ---------------------------------------------------------------------------

SCOPE_TO_CONTEXT = {
    "FRAME_FILL": "background", "SHAPE_FILL": "background",
    "TEXT_FILL": "text", "STROKE_COLOR": "border", "ALL_SCOPES": "all",
}

# Skip component-level, alt, gradient tokens
SKIP_TOKEN_PREFIXES = ("components/", "alt/", "gradient/")

# Skip any token with "ai" as a path segment (e.g. text+icons/ai/high, accent/ai, background/ai-subtle)
SKIP_TOKEN_AI = True  # filter out all AI-related tokens

def extract_figma_tokens(data):
    tokens = []
    root = data[0] if isinstance(data, list) else data
    for mode_name, mode_data in root.get("Colors", {}).get("modes", {}).items():
        _walk(mode_data, [], mode_name, tokens)
    return tokens

def _walk(node, parts, mode, tokens):
    if not isinstance(node, dict):
        return
    if "$type" in node and node.get("$type") == "color" and "$value" in node:
        val = node["$value"]
        if val.startswith("{"):
            return
        path = "/".join(parts)
        if any(path.startswith(p) for p in SKIP_TOKEN_PREFIXES):
            return
        # Skip AI tokens: any path with "ai" as a segment or prefix in a segment
        if SKIP_TOKEN_AI:
            segments = path.split("/")
            if any(s == "ai" or s.startswith("ai-") for s in segments):
                return
        rgb = parse_color_strict(val)
        if rgb is None:
            return
        scopes = node.get("$scopes", [])
        contexts = set()
        for s in scopes:
            c = SCOPE_TO_CONTEXT.get(s)
            if c:
                contexts.add(c)
        if not contexts:
            contexts = {"all"}
        lab = rgb_to_lab(*rgb)
        tokens.append({
            "path": path, "hex": rgb_to_hex(*rgb), "rgb": rgb,
            "lab": lab, "lch": lab_to_lch(lab), "scopes": scopes,
            "contexts": contexts, "mode": mode,
        })
    else:
        for k, v in node.items():
            if not k.startswith("$"):
                _walk(v, parts + [k], mode, tokens)


# ---------------------------------------------------------------------------
# Audit extraction (hex + named only, no rgba)
# ---------------------------------------------------------------------------

def extract_audit_colors(audit):
    results = []
    for raw, info in audit.get("hardcoded_usage", {}).items():
        rgb = parse_color_strict(raw)
        if rgb is None:
            continue
        lab = rgb_to_lab(*rgb)
        results.append({
            "raw": raw, "rgb": rgb, "lab": lab, "lch": lab_to_lch(lab),
            "hex": rgb_to_hex(*rgb),
            "occurrences": info.get("occurrences", 0),
            "contexts": info.get("contexts", {}),
            "groups": info.get("groups", {}),
        })
    return results


# ---------------------------------------------------------------------------
# Strict context matching
# ---------------------------------------------------------------------------

# Map audit context → which token contexts it can match
# Only core contexts go into token clusters; shadow/other collected separately
STRICT_CTX = {
    "text":       {"text", "all"},
    "background": {"background", "all"},
    "border":     {"border", "all"},
    "icon":       {"text", "all"},
}

# Contexts excluded from main matching — listed in separate section
SEPARATE_CONTEXTS = {"shadow", "other"}


def build_clusters(audit_colors, tokens, mode_name):
    """For each audit color+context, find best token (strict context). Invert to token-first."""
    clusters = {}
    for t in tokens:
        clusters[t["path"]] = {
            "hex": t["hex"], "scopes": t["scopes"],
            "contexts": sorted(t["contexts"]),
            "by_context": defaultdict(list),
        }

    total = len(audit_colors)
    for i, ac in enumerate(audit_colors):
        if (i+1) % 200 == 0:
            print(f"  [{mode_name}] {i+1}/{total}...", file=sys.stderr)
        lab = ac["lab"]

        for ctx, ctx_count in ac["contexts"].items():
            allowed = STRICT_CTX.get(ctx)
            if not allowed:
                continue

            # Graduated hue-gate matching:
            # Try progressively wider hue gates (30° → 50° → 70° → 90°)
            # before falling back to all context-eligible tokens.
            lch = ac["lch"]
            ctx_eligible = [t for t in tokens if (allowed & t["contexts"])]

            candidates = None
            for gate in HUE_GATE_STEPS:
                compat = [t for t in ctx_eligible
                          if is_hue_compatible(lch, t["lch"], gate)]
                if compat:
                    candidates = compat
                    break

            if candidates is None:
                # Last resort: prefer same chroma class first, then relax.
                candidates = fallback_candidates_by_chroma(lch, ctx_eligible)

            best_t, best_de = None, float("inf")
            for t in candidates:
                de = delta_e_2000(lab, t["lab"])
                if de < best_de:
                    best_de = de
                    best_t = t

            # Max-distance guard: skip if dE is too high (no good match)
            if best_t and best_de <= MAX_DE:
                color_lch = ac["lch"]
                clusters[best_t["path"]]["by_context"][ctx].append({
                    "color": ac["raw"], "hex": ac["hex"],
                    "de": round(best_de, 2),
                    "h": round(color_lch[2], 1),  # hue angle 0-360
                    "l": round(color_lch[0], 1),   # lightness 0-100
                    "c": round(color_lch[1], 1),   # chroma
                    "occurrences": ctx_count,
                    "groups": ac["groups"],
                })

    # Serialize, dedupe hex within each context, sort
    result = []
    for path in sorted(clusters):
        c = clusters[path]
        by_ctx = {}
        total_occ = 0
        unique_hexes = set()
        for ctx_name in sorted(c["by_context"]):
            items = c["by_context"][ctx_name]
            # Dedupe by hex — keep the one with highest occurrences
            seen = {}
            for it in items:
                h = it["hex"]
                if h not in seen or it["occurrences"] > seen[h]["occurrences"]:
                    seen[h] = it
            # Sort by visual similarity: hue → lightness (achromatic by lightness only)
            deduped = sorted(seen.values(),
                             key=lambda x: (x["h"], x["l"]) if x["c"] >= ACHROMATIC_CHROMA
                                           else (-1, x["l"]))
            by_ctx[ctx_name] = deduped
            total_occ += sum(it["occurrences"] for it in deduped)
            unique_hexes.update(it["hex"] for it in deduped)

        result.append({
            "token": path, "hex": c["hex"], "scopes": c["scopes"],
            "token_contexts": c["contexts"],
            "unique_colors": len(unique_hexes),
            "total_occurrences": total_occ,
            "by_context": by_ctx,
        })

    # Sort tokens: first by scope group (matching HTML viewer sections),
    # then by semantic color group, then by variant within group.
    # Scope order: Background → Text & Icons → Border → All
    # Color group order: neutral → primary → info → success → warning → danger
    # Variant order: high → medium* → low → on-accent → solid → subtle
    SCOPE_ORDER = {"background": 0, "text": 1, "border": 2, "all": 3}
    COLOR_GROUP_ORDER = {
        "neutral": 0, "primary": 1, "info": 2, "success": 3, "warning": 4, "danger": 5,
    }
    VARIANT_ORDER = {
        "high": 0, "medium*": 1, "low": 2, "on-accent": 3,
        "solid": 4, "accent": 5, "subtle": 6,
    }

    def _scope_key(item):
        """Determine scope group matching the HTML viewer logic."""
        scopes = item["scopes"]
        path = item["token"]
        if "TEXT_FILL" in scopes or ("SHAPE_FILL" in scopes and path.startswith("text")):
            return SCOPE_ORDER["text"]
        if "STROKE_COLOR" in scopes:
            return SCOPE_ORDER["border"]
        if "FRAME_FILL" in scopes or "SHAPE_FILL" in scopes:
            return SCOPE_ORDER["background"]
        return SCOPE_ORDER["all"]

    def _semantic_sort_key(item):
        path = item["token"]
        parts = path.split("/")
        # Extract color group from path (e.g. "text+icons/neutral/high" → "neutral")
        group = "neutral"
        variant = ""
        for p in parts:
            if p in COLOR_GROUP_ORDER:
                group = p
            for v in VARIANT_ORDER:
                if p == v or p.endswith("-" + v):
                    variant = v
        # accent/* tokens: accent/info → group=info, variant=accent (solid fill)
        if parts[0] == "accent" and len(parts) > 1:
            if parts[1] in COLOR_GROUP_ORDER:
                group = parts[1]
            variant = "accent"
        # background/*-subtle tokens: background/info-subtle → info
        for p in parts:
            for g in COLOR_GROUP_ORDER:
                if g in p and g != "neutral":
                    group = g
                    break
        # container/* → neutral
        if parts[0] == "container":
            group = "neutral"
        # background/main, secondary, tertiary → neutral, no variant override
        if parts[0] == "background" and len(parts) > 1 and parts[1] in ("main", "secondary", "tertiary"):
            group = "neutral"

        return (
            _scope_key(item),
            COLOR_GROUP_ORDER.get(group, 99),
            VARIANT_ORDER.get(variant, 99),
            path,
        )

    result.sort(key=_semantic_sort_key)
    return result


# ---------------------------------------------------------------------------
# Separate section: shadow, other, rgba colors with CSS properties
# ---------------------------------------------------------------------------

def extract_separate_colors(audit):
    """Extract colors that don't go into main token matching:
    - hex/named colors used only in shadow or other contexts
    - rgba/rgb/hsl functional colors (any context)
    All include their CSS properties from the audit.
    """
    results = []
    for raw, info in audit.get("hardcoded_usage", {}).items():
        occ = info.get("occurrences", 0)
        s = raw.strip().lower()
        contexts = info.get("contexts", {})
        properties = info.get("properties", {})
        groups = info.get("groups", {})

        is_functional = (s.startswith("rgb") or s.startswith("hsl"))
        is_var = "var(" in s
        is_keyword = s in ("transparent", "inherit", "currentcolor", "none", "initial", "unset")

        if is_var or is_keyword:
            continue

        if is_functional:
            # All rgba/rgb/hsl go into separate section
            results.append({
                "color": raw,
                "type": "functional",
                "occurrences": occ,
                "contexts": contexts,
                "properties": properties,
                "groups": groups,
            })
        else:
            # Hex/named: only include if they have shadow or other usages
            separate_ctxs = {k: v for k, v in contexts.items() if k in SEPARATE_CONTEXTS}
            if separate_ctxs:
                results.append({
                    "color": raw,
                    "type": "hex",
                    "hex": rgb_to_hex(*parse_color_strict(raw)) if parse_color_strict(raw) else raw,
                    "occurrences": sum(separate_ctxs.values()),
                    "contexts": separate_ctxs,
                    "properties": properties,
                    "groups": groups,
                })

    results.sort(key=lambda x: -x["occurrences"])
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    refs_dir = Path(__file__).parent

    print("Loading...", file=sys.stderr)
    with open(refs_dir / "leadexec-colors-figma.json") as f:
        figma_data = json.load(f)
    with open(refs_dir / "leadexec-colors-audit.json") as f:
        audit_data = json.load(f)

    figma_tokens = extract_figma_tokens(figma_data)
    by_mode = defaultdict(list)
    for t in figma_tokens:
        by_mode[t["mode"]].append(t)

    # Only Light and Dark
    for m in list(by_mode.keys()):
        if m not in ("Light", "Dark"):
            del by_mode[m]

    print(f"  Figma: {len(by_mode.get('Light',[]))} Light, {len(by_mode.get('Dark',[]))} Dark tokens (core only)", file=sys.stderr)

    audit_colors = extract_audit_colors(audit_data)
    audit_colors.sort(key=lambda x: -x["occurrences"])
    print(f"  Audit: {len(audit_colors)} colors (hex/named)", file=sys.stderr)

    # Separate section: shadow, other, rgba colors with CSS properties
    separate = extract_separate_colors(audit_data)
    print(f"  Separate: {len(separate)} colors (shadow/other/rgba)", file=sys.stderr)

    print("\nLight clusters...", file=sys.stderr)
    light = build_clusters(audit_colors, by_mode.get("Light", []), "Light")
    print(f"\nDark clusters...", file=sys.stderr)
    dark = build_clusters(audit_colors, by_mode.get("Dark", []), "Dark")

    # Figma palette for reference
    palette = {}
    for m, tlist in by_mode.items():
        palette[m] = [{"path": t["path"], "hex": t["hex"], "scopes": t["scopes"]}
                      for t in sorted(tlist, key=lambda x: x["path"])]

    output = {
        "summary": {
            "mapped_colors": len(audit_colors),
            "light_tokens": len(by_mode.get("Light", [])),
            "dark_tokens": len(by_mode.get("Dark", [])),
            "separate_colors": len(separate),
        },
        "light": light,
        "dark": dark,
        "separate": separate,
        "figma_palette": palette,
    }

    out = refs_dir / "color-mapping-report.json"
    with open(out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWritten: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
