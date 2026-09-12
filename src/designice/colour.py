"""Colour roles, contrast, and the override layer.

A palette is a list of hexes in role order; a *role map* is what the scaffolds
actually consume: ground, surface, ink, muted, accent, accent2. This module
owns the translation between the two, and the rules for letting a user's own
brand colours replace a template's without breaking legibility.

The override rules are deliberately narrow. A user names a primary and a
secondary; those become accent and accent2. Neutrals - ground, ink, and the two
derived from them - are only touched when explicitly asked, because the fastest
way to wreck a re-skin is to let "make it teal" also repaint the background.
"""

from __future__ import annotations

from typing import Any

ROLE_ORDER = ("ground", "surface", "ink", "muted", "accent", "accent2")

DARK_FALLBACK = {"ground": "#0B0B0C", "surface": "#17181B", "ink": "#E7E7EA",
                 "muted": "#8A8A93", "accent": "#7A5CFF", "accent2": "#22D3EE"}
LIGHT_FALLBACK = {"ground": "#FFFFFF", "surface": "#F5F5F7", "ink": "#111113",
                  "muted": "#6B7280", "accent": "#3D5AFE", "accent2": "#F59E0B"}

# WCAG thresholds. Body text needs 4.5:1; large text and UI components need 3:1.
MIN_INK_CONTRAST = 4.5
MIN_ACCENT_CONTRAST = 3.0


def normalise(hexstr: str) -> str | None:
    """'#abc' / 'abc' / '#AABBCC' -> '#AABBCC', or None if it isn't a hex colour."""
    if not hexstr:
        return None
    h = str(hexstr).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        int(h, 16)
    except ValueError:
        return None
    return "#" + h.upper()


def _rgb(hexstr: str) -> tuple[int, int, int]:
    h = (normalise(hexstr) or "#000000").lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(hexstr: str) -> float:
    """Perceived brightness 0-255, the cheap Rec. 709 weighting."""
    r, g, b = _rgb(hexstr)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_dark(hexstr: str) -> bool:
    return luminance(hexstr) < 110


def chroma(hexstr: str) -> int:
    """How far from grey a colour is: the spread between its strongest and weakest channel.

    A neutral (#5B5B66) scores ~10; a brand colour (#E040A0) scores ~160. Roles
    like ink and muted must come from the low end - a magenta that happens to
    have mid luminance is not a text colour, it is the template's brand leaking.
    """
    r, g, b = _rgb(hexstr)
    return max(r, g, b) - min(r, g, b)


NEUTRAL_CHROMA = 60


def _linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hexstr: str) -> float:
    r, g, b = _rgb(hexstr)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio, 1.0 (identical) to 21.0 (black on white)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, t: float) -> str:
    """Linear blend of a toward b by t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#{:02X}{:02X}{:02X}".format(
        round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


def roles_from_palette(palette: list[str], dark: bool) -> dict[str, str]:
    """Map an ordered palette onto semantic roles.

    Design descriptions list colours in role order - ground, surface, accent,
    text - so we follow that, then fill any gap with a sane value for the mode
    rather than reusing a colour twice and flattening the whole page. Ink is
    then sanity-checked against the ground's luminance, because palettes are
    not always written in the order we hope.
    """
    fallback = DARK_FALLBACK if dark else LIGHT_FALLBACK
    p = list(dict.fromkeys(c for c in (normalise(x) for x in palette) if c))
    # Pad from the fallback, skipping any value the palette already holds -
    # a duplicate here would later be mistaken for a distinct accent.
    for role in ("ground", "surface", "ink", "muted", "accent"):
        if len(p) >= 5:
            break
        if fallback[role] not in p:
            p.append(fallback[role])

    ground, surface = p[0], p[1]
    candidates = [c for c in p[2:] if c not in (ground, surface)]

    ink = fallback["ink"]
    muted = fallback["muted"]
    accent = fallback["accent"]
    accent2 = None
    if candidates:
        neutrals = [c for c in candidates if chroma(c) < NEUTRAL_CHROMA]
        chromatic = [c for c in candidates if chroma(c) >= NEUTRAL_CHROMA]
        # Ink: the neutral furthest from the ground; fall back to any candidate
        # if the palette has no neutrals at all.
        pool = neutrals or candidates
        ink = max(pool, key=luminance) if dark else min(pool, key=luminance)
        # Muted: another neutral, nearest mid-luminance; derive one if there isn't.
        rest_neutral = [c for c in neutrals if c != ink]
        muted = (min(rest_neutral, key=lambda c: abs(luminance(c) - 128)) if rest_neutral
                 else mix(ink, ground, 0.45))
        # Accents: the chromatic colours, strongest first. A neutral is never an accent.
        chromatic.sort(key=chroma, reverse=True)
        if chromatic:
            accent = chromatic[0]
            if len(chromatic) > 1:
                accent2 = chromatic[1]
    if accent2 is None:
        accent2 = mix(accent, ink, 0.35)
    return {"ground": ground, "surface": surface, "ink": ink,
            "muted": muted, "accent": accent, "accent2": accent2}


def apply_overrides(roles: dict[str, str], overrides: dict[str, Any] | None) -> tuple[dict[str, str], list[str]]:
    """Lay a user's brand colours over a template's roles.

    Returns the new role map and a list of notes - things a person should know,
    like an ink that had to be swapped for legibility, or an accent that will be
    hard to read but was left alone because you do not recolour someone's brand.
    """
    out = dict(roles)
    notes: list[str] = []
    ov = overrides or {}

    def take(key: str) -> str | None:
        value = normalise(ov.get(key, ""))
        if ov.get(key) and not value:
            notes.append(f"{key} {ov.get(key)!r} is not a hex colour and was ignored")
        return value

    primary, secondary, ground, ink = take("primary"), take("secondary"), take("ground"), take("ink")

    if ground:
        out["ground"] = ground
    if ink:
        out["ink"] = ink

    dark = is_dark(out["ground"])

    # Neutrals derive from whatever ground and ink ended up being. If either
    # changed, the ones between them must move too or the page loses its steps.
    if ground or ink:
        out["surface"] = mix(out["ground"], out["ink"], 0.04)
        out["muted"] = mix(out["ink"], out["ground"], 0.45)

    if primary:
        out["accent"] = primary
    if secondary:
        out["accent2"] = secondary
    elif primary:
        # A new primary without a secondary should not leave the template's
        # old second accent behind - derive one that belongs to the new brand.
        out["accent2"] = mix(primary, out["ink"], 0.35)

    # Legibility guards. Ink is ours to fix; brand colours are not.
    if contrast(out["ink"], out["ground"]) < MIN_INK_CONTRAST:
        fallback = (DARK_FALLBACK if dark else LIGHT_FALLBACK)["ink"]
        notes.append(f"ink {out['ink']} on {out['ground']} is {contrast(out['ink'], out['ground']):.1f}:1; "
                     f"swapped for {fallback} to stay readable")
        out["ink"] = fallback
        out["muted"] = mix(out["ink"], out["ground"], 0.45)

    for role in ("accent", "accent2"):
        ratio = contrast(out[role], out["ground"])
        if ratio < MIN_ACCENT_CONTRAST:
            notes.append(f"{role} {out[role]} on {out['ground']} is only {ratio:.1f}:1 - fine for fills, "
                         f"but do not set body text in it")

    return out, notes


def mode_of(roles: dict[str, str]) -> str:
    return "dark" if is_dark(roles["ground"]) else "light"
