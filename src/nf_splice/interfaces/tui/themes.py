"""The six curated themes, their measured contrast and the theme preference.

Every colour in the workspace comes from one token set per theme (ADR-0067):
widgets, the AI dock and the footer use the Textual variables these themes
define, never literal colours. :func:`contrast_report` measures each theme
with the WCAG 2.x relative-luminance formula and :func:`simulate` applies
colour-vision-deficiency matrices; ``tests/test_tui_themes.py`` requires
4.5:1 for text and 3:1 for control boundaries in every theme. States are
never told apart by colour alone: each also has a glyph and a word.

The preference is personal: it is kept in the user's configuration folder
(``tui.json``), never in a repository or its private ``.splice-local/``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from textual.theme import Theme

from nf_splice.credentials import config_directory

DEFAULT_THEME = "splice-night"


@dataclass(frozen=True, slots=True)
class Palette:
    """One theme's tokens (hex colours)."""

    name: str
    title: str
    dark: bool
    canvas: str
    header: str
    sidebar: str
    surface: str
    selected: str
    border: str
    #: Input, button and focus-ring boundaries (measured against 3:1).
    control: str
    accent: str
    primary: str
    on_primary: str
    text: str
    muted: str
    success: str
    warning: str
    error: str


PALETTES: tuple[Palette, ...] = (
    Palette(
        "splice-night",
        "SPLICE Night",
        True,
        canvas="#101720",
        header="#182636",
        sidebar="#14202C",
        surface="#1B2B3B",
        selected="#214668",
        border="#324458",
        control="#677583",
        accent="#4DB2FF",
        primary="#1673C8",
        on_primary="#FFFFFF",
        text="#F3F7FC",
        muted="#A9BED0",
        success="#49CB95",
        warning="#F1B85B",
        error="#FF8592",
    ),
    Palette(
        "splice-day",
        "SPLICE Day",
        False,
        canvas="#F6F8FC",
        header="#E6EDF4",
        sidebar="#EDF2F6",
        surface="#FFFFFF",
        selected="#CEE5FF",
        border="#C6D1DD",
        control="#818890",
        accent="#1458A5",
        primary="#155899",
        on_primary="#FFFFFF",
        text="#152638",
        muted="#455D70",
        success="#1A724F",
        warning="#795016",
        error="#A62F45",
    ),
    Palette(
        "ocean-amber",
        "Ocean & Amber",
        True,
        canvas="#101B2B",
        header="#20334A",
        sidebar="#17283D",
        surface="#223A54",
        selected="#305778",
        border="#48657E",
        control="#6D8498",
        accent="#93CEFF",
        primary="#1B70A6",
        on_primary="#FFFFFF",
        text="#F8FBFF",
        muted="#C5D8E6",
        success="#9BD4FF",
        warning="#FFCA79",
        error="#FFF0BF",
    ),
    Palette(
        "violet-gold",
        "Violet & Gold",
        True,
        canvas="#191629",
        header="#28213E",
        sidebar="#201A32",
        surface="#302744",
        selected="#55416D",
        border="#554866",
        control="#7A7088",
        accent="#C3ADFF",
        primary="#6B4AA9",
        on_primary="#FFFFFF",
        text="#FAF6FF",
        muted="#D2C7E0",
        success="#E1D2FF",
        warning="#FFDB8A",
        error="#FFE9AC",
    ),
    Palette(
        "high-contrast-dark",
        "High Contrast Dark",
        True,
        canvas="#000000",
        header="#151515",
        sidebar="#090909",
        surface="#141414",
        selected="#334354",
        border="#929292",
        control="#929292",
        accent="#A9E1FF",
        primary="#176B9A",
        on_primary="#FFFFFF",
        text="#FFFFFF",
        muted="#EEEEEE",
        success="#FFFFFF",
        warning="#FFDB5B",
        error="#FFB2A7",
    ),
    Palette(
        "high-contrast-light",
        "High Contrast Light",
        False,
        canvas="#FFFFFF",
        header="#ECECEC",
        sidebar="#F2F2F2",
        surface="#FFFFFF",
        selected="#DAE8FA",
        border="#616161",
        control="#616161",
        accent="#034987",
        primary="#034987",
        on_primary="#FFFFFF",
        text="#080808",
        muted="#303030",
        success="#080808",
        warning="#754300",
        error="#8C2044",
    ),
)
PALETTE_BY_NAME = {item.name: item for item in PALETTES}


def theme(palette: Palette) -> Theme:
    """The Textual theme of one palette; extra tokens are CSS variables."""
    return Theme(
        name=palette.name,
        primary=palette.primary,
        secondary=palette.accent,
        accent=palette.accent,
        warning=palette.warning,
        error=palette.error,
        success=palette.success,
        foreground=palette.text,
        background=palette.canvas,
        surface=palette.surface,
        panel=palette.header,
        boost=palette.selected,
        dark=palette.dark,
        variables={
            "splice-header": palette.header,
            "splice-sidebar": palette.sidebar,
            "splice-surface": palette.surface,
            "splice-selected": palette.selected,
            "splice-border": palette.border,
            "splice-control": palette.control,
            "splice-muted": palette.muted,
            "splice-on-primary": palette.on_primary,
            "text-muted": palette.muted,
            "border": palette.control,
            "border-blurred": palette.border,
            "block-cursor-background": palette.selected,
            "block-cursor-foreground": palette.text,
            "block-cursor-text-style": "bold",
            "input-selection-background": palette.selected,
            "footer-background": palette.sidebar,
            "footer-key-foreground": palette.accent,
            "footer-description-foreground": palette.muted,
        },
    )


THEMES: tuple[Theme, ...] = tuple(theme(item) for item in PALETTES)


# ------------------------------------------------------------ measurement


def _rgb(colour: str) -> tuple[float, float, float]:
    value = colour.lstrip("#")
    return (
        int(value[0:2], 16) / 255,
        int(value[2:4], 16) / 255,
        int(value[4:6], 16) / 255,
    )


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(colour: str) -> float:
    """WCAG 2.x relative luminance of an sRGB hex colour."""
    red, green, blue = (_linear(item) for item in _rgb(colour))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio, 1 to 21."""
    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


#: Machado, Oliveira and Fernandes (2009) matrices at full severity, applied
#: to linear RGB; monochrome is luminance only.
_DEFICIENCIES: dict[str, tuple[tuple[float, float, float], ...]] = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}
DEFICIENCIES = (*_DEFICIENCIES, "monochrome")


def _encode(channel: float) -> int:
    channel = min(max(channel, 0.0), 1.0)
    value = (
        channel * 12.92
        if channel <= 0.0031308
        else 1.055 * channel ** (1 / 2.4) - 0.055
    )
    return round(value * 255)


def simulate(colour: str, deficiency: str) -> str:
    """How a colour appears with a colour-vision deficiency (approximation)."""
    linear = [_linear(item) for item in _rgb(colour)]
    if deficiency == "monochrome":
        grey = relative_luminance(colour)
        values = [grey, grey, grey]
    else:
        matrix = _DEFICIENCIES[deficiency]
        values = [
            sum(row[index] * linear[index] for index in range(3)) for row in matrix
        ]
    return "#" + "".join(f"{_encode(item):02X}" for item in values)


#: Text roles and the backgrounds they appear on (4.5:1 each).
TEXT_PAIRS = (
    ("text", ("canvas", "surface", "sidebar", "header", "selected")),
    ("muted", ("canvas", "surface", "sidebar", "header")),
    ("accent", ("canvas", "surface", "sidebar", "header")),
    ("success", ("canvas", "surface", "sidebar", "header")),
    ("warning", ("canvas", "surface", "sidebar", "header")),
    ("error", ("canvas", "surface", "sidebar", "header")),
    ("on_primary", ("primary",)),
)
#: Boundaries of controls and the focus ring (3:1 each).
CONTROL_PAIRS = (
    ("control", ("canvas", "surface", "header")),
    ("accent", ("surface", "canvas")),
)


@dataclass(frozen=True, slots=True)
class ContrastCheck:
    theme: str
    foreground: str
    background: str
    ratio: float
    required: float

    @property
    def passed(self) -> bool:
        return self.ratio >= self.required


def contrast_report(palette: Palette) -> list[ContrastCheck]:
    """Every measured pair of one theme."""
    checks = []
    for pairs, required in ((TEXT_PAIRS, 4.5), (CONTROL_PAIRS, 3.0)):
        for foreground, backgrounds in pairs:
            for background in backgrounds:
                checks.append(
                    ContrastCheck(
                        palette.name,
                        foreground,
                        background,
                        round(
                            contrast_ratio(
                                getattr(palette, foreground),
                                getattr(palette, background),
                            ),
                            2,
                        ),
                        required,
                    )
                )
    return checks


# ------------------------------------------------------------ preference


def _preference_file(environment: Mapping[str, str] | None = None) -> Path:
    return config_directory(environment) / "tui.json"


def load_theme_preference(environment: Mapping[str, str] | None = None) -> str:
    """The person's saved theme, or the default."""
    try:
        document = json.loads(_preference_file(environment).read_text("utf-8"))
    except (OSError, ValueError):
        return DEFAULT_THEME
    name = document.get("theme") if isinstance(document, dict) else None
    return name if name in PALETTE_BY_NAME else DEFAULT_THEME


def save_theme_preference(
    name: str, environment: Mapping[str, str] | None = None
) -> Path | None:
    """Save the theme in the user's configuration folder (best effort)."""
    if name not in PALETTE_BY_NAME:
        raise ValueError(f"unknown theme {name!r}")
    path = _preference_file(environment)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            document = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            document = {}
        if not isinstance(document, dict):
            document = {}
        document["theme"] = name
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        return None
    return path
