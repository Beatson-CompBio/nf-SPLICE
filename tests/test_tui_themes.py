"""Themes: measured contrast, colour-vision simulation and a saved choice.

The ratios are WCAG 2.x relative-luminance contrast; the simulations use the
Machado, Oliveira and Fernandes (2009) matrices at full severity. They are
measurements of the palettes, not a substitute for testing with people.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from layer_fixtures import ADA
from multi_route import copy_fixture
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.interfaces.tui.modals import ThemeDialog
from nf_splice.interfaces.tui.navigation import GLYPHS, LABELS
from nf_splice.interfaces.tui.themes import (
    DEFAULT_THEME,
    DEFICIENCIES,
    PALETTES,
    TEXT_PAIRS,
    contrast_ratio,
    contrast_report,
    load_theme_preference,
    save_theme_preference,
    simulate,
)
from nf_splice.services.workspace import initialise
from tui_helpers import settle

STYLESHEET = (
    Path(__file__).parents[1] / "src" / "nf_splice" / "interfaces" / "tui" / "tui.tcss"
)


def test_six_themes_including_two_high_contrast_ones() -> None:
    names = [item.name for item in PALETTES]
    assert len(names) == len(set(names)) == 6
    assert DEFAULT_THEME == "splice-night"
    assert {"high-contrast-dark", "high-contrast-light"} <= set(names)
    assert {item.dark for item in PALETTES} == {True, False}


@pytest.mark.parametrize("palette", PALETTES, ids=lambda item: item.name)
def test_every_text_and_control_pair_meets_its_contrast_ratio(palette: object) -> None:
    failures = [
        f"{item.foreground} on {item.background}: {item.ratio} < {item.required}"
        for item in contrast_report(palette)  # type: ignore[arg-type]
        if not item.passed
    ]
    assert not failures


@pytest.mark.parametrize("palette", PALETTES, ids=lambda item: item.name)
@pytest.mark.parametrize("deficiency", DEFICIENCIES)
def test_status_text_stays_readable_with_colour_vision_deficiencies(
    palette: object, deficiency: str
) -> None:
    backgrounds = dict(TEXT_PAIRS)["success"]
    for role in ("text", "muted", "success", "warning", "error"):
        for background in backgrounds:
            ratio = contrast_ratio(
                simulate(getattr(palette, role), deficiency),
                simulate(getattr(palette, background), deficiency),
            )
            assert ratio >= 4.5, (role, background, round(ratio, 2))


def test_states_never_rely_on_colour_alone() -> None:
    # Success and error can look alike to some people, so every state also
    # has its own glyph and words.
    assert len(set(GLYPHS.values())) == len(GLYPHS)
    assert len(set(LABELS.values())) == len(LABELS)


def test_the_stylesheet_uses_only_theme_tokens() -> None:
    text = re.sub(r"/\*.*?\*/", "", STYLESHEET.read_text(encoding="utf-8"), flags=re.S)
    declarations = re.findall(r"[a-z-]+\s*:\s*([^;{}]+);", text)
    literal = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    assert declarations
    assert not [value for value in declarations if literal.search(value)]


def test_a_theme_choice_is_saved_in_the_configuration_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = {"NF_SPLICE_CONFIG_DIR": str(tmp_path / "config")}
    assert load_theme_preference(environment) == DEFAULT_THEME
    path = save_theme_preference("ocean-amber", environment)
    assert path == tmp_path / "config" / "tui.json"
    assert load_theme_preference(environment) == "ocean-amber"
    with pytest.raises(ValueError):
        save_theme_preference("no-such-theme", environment)
    path.write_text("{not json", encoding="utf-8")
    assert load_theme_preference(environment) == DEFAULT_THEME


@pytest.mark.asyncio
async def test_every_theme_renders_and_the_dialog_remembers_the_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NF_SPLICE_CONFIG_DIR", str(tmp_path / "config"))
    root = copy_fixture(tmp_path)
    initialise(root, ADA)
    app = NfSpliceApp(root, user="Ada", start="overview", remember_theme=True)
    async with app.run_test(size=(140, 45)) as pilot:
        await settle(app, pilot)
        assert app.theme == DEFAULT_THEME
        for palette in PALETTES:
            app.theme = palette.name
            await pilot.pause()
            assert app.screen.styles.background is not None
        app.theme = DEFAULT_THEME
        app.action_theme()
        await pilot.pause()
        assert isinstance(app.screen, ThemeDialog)
        app.screen.dismiss("high-contrast-light")
        await settle(app, pilot)
        assert app.theme == "high-contrast-light"
    assert load_theme_preference() == "high-contrast-light"
