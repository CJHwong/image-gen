"""Check studio themes on a fresh stub with all models offered.

Usage: uv run --with playwright python tests/e2e/verify_themes.py <port> [screenshot-directory]
"""

import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = f"http://127.0.0.1:{sys.argv[1]}/"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
THEMES = (("blueprint", "Blueprint"), ("cel", "Cel Studio"), ("broadcast", "Broadcast"), ("risograph", "Risograph"))
LEGACY = ("Darkroom", "Leica M", "Kodak Instamatic", "Polaroid SX-70")


def luminance(value):
    channels = [int(value.lstrip("#")[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def contrast(first, second):
    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


def select_theme(page, name):
    page.locator("#theme-toggle").click()
    page.get_by_role("menuitemradio", name=name, exact=True).click()
    expect(page.locator("#theme-menu")).to_be_hidden()


def surfaces(page):
    return page.evaluate("""() => ['html', '.stage', '.workspace-tabs'].map(selector => {
      const style = getComputedStyle(document.querySelector(selector));
      return [style.color, style.backgroundColor, style.backgroundImage, style.borderRadius, style.fontFamily];
    })""")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    errors = []
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)
    expect(page.locator("#theme-menu [role=menuitemradio]")).to_have_count(8)
    # Populate real components through the stub, so media styles are checked too.
    page.locator("#prompt").fill("A red pear on a wooden table.")
    page.locator("#go").click()
    expect(page.locator("#strip .frame:not(.pending)").first).to_be_visible(timeout=65000)
    page.locator("#workspace-tabs button").filter(has_text="Voice").click()
    page.locator("#voice-text").fill("A short studio theme preview.")
    page.locator("#voice-generate").click()
    expect(page.locator("audio-preview")).to_be_visible(timeout=20000)
    page.emulate_media(color_scheme="light")
    legacy_surfaces = {}
    for name in LEGACY:
        select_theme(page, name)
        legacy_surfaces[name] = surfaces(page)
    for theme, name in THEMES:
        select_theme(page, name)
        expect(page.locator("html")).to_have_attribute("data-theme", theme)
        page.locator("#theme-toggle").click()
        expect(page.get_by_role("menuitemradio", name=name, exact=True)).to_have_attribute("aria-checked", "true")
        page.keyboard.press("Escape")
        for workspace in ("Image", "Video", "Voice"):
            tab = page.locator("#workspace-tabs button").filter(has_text=workspace)
            tab.click()
            expect(tab).to_have_attribute("aria-pressed", "true")
            expect(
                page.locator({"Image": "#go", "Video": "#video-generate", "Voice": "#voice-generate"}[workspace])
            ).to_be_visible()
            for scheme in ("light", "dark"):
                page.emulate_media(color_scheme=scheme)
                palettes = page.evaluate("""() => [document.documentElement, document.querySelector('.stage')].map(element => {
                  const style = getComputedStyle(element);
                  return Object.fromEntries(['--text', '--text-2', '--text-3', '--chrome', '--chrome-2', '--chrome-3',
                    '--accent-fill', '--on-accent'].map(key => [key, style.getPropertyValue(key).trim()]));
                })""")
                for palette in palettes:
                    for foreground in ("--text", "--text-2", "--text-3"):
                        for background in ("--chrome", "--chrome-2", "--chrome-3"):
                            assert contrast(palette[foreground], palette[background]) >= 4.5, (
                                theme,
                                workspace,
                                palette,
                            )
                    assert contrast(palette["--accent-fill"], palette["--on-accent"]) >= 4.5
            media = page.locator(".stage img, .stage video, audio-preview svg")
            assert media.evaluate_all(
                "els => els.every(el => getComputedStyle(el).filter === 'none' && getComputedStyle(el).mixBlendMode === 'normal')"
            )
            if workspace == "Video":
                colors = page.locator(".video-empty").evaluate("""el => {
                  const style = getComputedStyle(el);
                  const rgb = style.color.match(/[0-9]+/g).map(Number);
                  return ['#' + rgb.map(c => c.toString(16).padStart(2, '0')).join(''), style.getPropertyValue('--box').trim()];
                }""")
                assert contrast(*colors) >= 4.5, (theme, "Video empty-state contrast", colors)
            if SHOTS:
                SHOTS.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(SHOTS / f"{theme}-{workspace.lower()}.png"), animations="disabled")
            for width in (1000, 768, 390):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (theme, workspace, width)
                button = page.locator(
                    {"Image": "#go", "Video": "#video-generate", "Voice": "#voice-generate"}[workspace]
                )
                expect(button).to_be_visible()
            page.set_viewport_size({"width": 1440, "height": 1000})
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", theme)
        fresh = context.new_page()
        fresh.goto(URL)
        expect(fresh.locator("html")).to_have_attribute("data-theme", theme)
        fresh.close()
        page.locator("#theme-toggle").focus()
        expect(page.locator("#theme-toggle")).to_be_focused()
        print(f"PASS {name}: all workspaces, previews, contrast, responsive widths, reload and fresh tab", flush=True)
    page.emulate_media(color_scheme="light")
    for name in LEGACY:
        select_theme(page, "Blueprint")
        select_theme(page, name)
        assert surfaces(page) == legacy_surfaces[name], (name, "legacy surfaces did not reset")
    print("PASS switching back restores all four legacy themes", flush=True)
    page.set_viewport_size({"width": 390, "height": 360})
    page.locator("#theme-toggle").click()
    menu = page.locator("#theme-menu")
    last = page.get_by_role("menuitemradio", name="Risograph", exact=True)
    last.scroll_into_view_if_needed()
    expect(last).to_be_visible()
    bounds = menu.bounding_box()
    assert bounds and bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 360
    assert menu.evaluate("el => el.scrollHeight > el.clientHeight"), "short menu must scroll"
    last.click()
    expect(page.locator("html")).to_have_attribute("data-theme", "risograph")
    print("PASS final theme remains reachable in a short phone viewport", flush=True)
    assert not errors, errors
    browser.close()
print("PASS all four studio themes", flush=True)
