"""Check Voice generation previews, progress, and shared operation state.

Run against a fresh `uv run studio --stub --all-backends --port <port>`.
"""

import sys
import time

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile

URL = "http://127.0.0.1:" + sys.argv[1]
VOICE = "A calm narrator with a warm, clear voice and a steady pace."


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


def ready(page):
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio')?.ready")


def finished(page, count):
    page.wait_for_function(
        "count => document.getElementById('voice-studio').takesCount === count && !document.getElementById('voice-studio').locked",
        arg=count,
        timeout=120000,
    )


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    ready(page)
    choose_voice_profile(page)
    page.locator("#voice-text").fill("A continuous recording for the generation preview.")
    pending = []
    page.route("**/voice/operations", lambda route: pending.append(route))
    with page.expect_request("**/voice/operations"):
        page.locator("#voice-generate").click()
    page.locator("#voice-generation").wait_for(state="visible")
    wave = page.get_by_role("progressbar", name="Audio generation progress", exact=True)
    check("Generate immediately replaces the preview before acceptance", bool(pending))
    check("preparation progress stays indeterminate", wave.get_attribute("aria-valuenow") is None)
    check(
        "generation hides the player and output actions",
        page.locator("audio-preview, .voice-output-actions").count() == 0,
    )
    check(
        "the pending gallery tile has the selection circle",
        page.locator(".voice-render-pending.selected svg.mark").count() == 1,
    )
    check(
        "the waveform animates during preparation",
        page.locator(".voice-generation-bars line").first.evaluate("line => getComputedStyle(line).animationName")
        == "voice-generation-pulse",
    )
    page.emulate_media(reduced_motion="reduce")
    check(
        "reduced motion disables the waveform animation",
        page.locator(".voice-generation-bars line").first.evaluate("line => getComputedStyle(line).animationName")
        == "none",
    )
    page.emulate_media(reduced_motion="no-preference")
    preparing_bounds = wave.bounding_box()
    page.screenshot(path="/tmp/voice-generation-desktop.png")
    pending.pop().continue_()
    page.unroute("**/voice/operations")
    finished(page, 1)
    check("the completed result replaces generation", page.locator("#voice-generation").count() == 0)
    check("the completed result restores the player", page.locator("audio-preview").count() == 1)
    page.wait_for_function("document.getElementById('voice-studio').previewReady")
    player_bounds = page.locator(".audio-preview-wave").bounding_box()
    check(
        "generation and the finished player share waveform dimensions",
        abs(player_bounds["width"] - preparing_bounds["width"]) < 1
        and abs(player_bounds["height"] - preparing_bounds["height"]) < 1,
    )
    check(
        "the real waveform fades in when ready",
        page.locator(".audio-preview-wave > svg").evaluate("wave => getComputedStyle(wave).animationName")
        == "voice-generation-ready",
    )

    check("success removes the pending tile", page.locator(".voice-render-pending").count() == 0)

    page.get_by_role("combobox", name="Playback speed", exact=True).select_option("1.5")
    page.locator("#voice-selected-edit").click()
    page.wait_for_function(
        "document.getElementById('voice-studio').mode === 'edit' && document.getElementById('voice-studio').reference"
    )
    page.locator("#voice-text").fill("Make the delivery calmer.")
    page.route("**/voice/operations", lambda route: pending.append(route))
    with page.expect_request("**/voice/operations"):
        page.locator("#voice-generate").click()
    page.locator("#voice-generation").wait_for(state="visible")
    check("Edit immediately shows generation before acceptance", bool(pending))
    page.get_by_role("button", name="Select audio 1", exact=True).click()
    check("an older clip can replace generation during a run", page.locator("audio-preview").count() == 1)
    check("the older clip retains its selected circle", page.locator(".voice-clip.selected svg.mark").count() == 1)
    check("handoff actions stay locked during generation", page.locator("#voice-selected-edit").is_disabled())
    check(
        "the older clip can still download", page.get_by_role("button", name="Download audio", exact=True).is_enabled()
    )
    edit_request = pending.pop()
    accepted_answer = edit_request.fetch()
    accepted_operation = accepted_answer.json()
    page.evaluate("operation => document.getElementById('voice-studio').setOperation(operation)", accepted_operation)
    check("the first accepted snapshot preserves older clip browsing", page.locator("audio-preview").count() == 1)
    check("the accepted snapshot leaves the older tile selected", page.locator(".voice-clip.selected").count() == 1)
    page.get_by_role("button", name="Show audio generation", exact=True).click()
    check("the pending tile returns to generation", page.locator("#voice-generation").is_visible())
    check("only the pending tile stays selected", page.locator("#voice-gallery .frame.selected").count() == 1)
    edit_request.fulfill(response=accepted_answer)
    page.unroute("**/voice/operations")
    finished(page, 2)
    check("the edited result restores the player", page.locator("audio-preview").count() == 1)
    check("editing preserves the original recording", page.locator(".voice-clip").count() == 2)
    check(
        "the reconstructed player preserves playback speed",
        page.get_by_role("combobox", name="Playback speed", exact=True).input_value() == "1.5",
    )

    page.locator('label[for="voice-mode-design"]').click()
    page.locator("#voice-text").fill("Keep this unsubmitted draft.")
    page.locator("#voice-description").fill(VOICE)
    observer = context.new_page()
    observer.on("pageerror", lambda error: errors.append(str(error)))
    ready(observer)
    response = context.request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "voice",
            "mode": "design",
            "voice": VOICE,
            "items": [{"text": f"Independent API recording {index}."} for index in range(16)],
        },
    )
    check("the external API batch starts", response.status == 202)
    operation = response.json()
    for tab in (page, observer):
        tab.locator("#voice-generation").wait_for(state="visible")
        check(
            "an API operation shows generation in each tab", tab.locator(".voice-render-pending.selected").count() == 1
        )
    page.set_viewport_size({"width": 390, "height": 800})
    bounds = page.locator("#voice-generation").bounding_box()
    check("generation fits the phone viewport", bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390)
    page.screenshot(path="/tmp/voice-generation-phone.png")

    progress_override = {"step": 4, "total": 10}

    def completed_progress(route):
        answer = route.fetch()
        state = answer.json()
        if state.get("active", {}).get("id") == operation["id"]:
            state["active"]["progress"] = progress_override
        route.fulfill(response=answer, json=state)

    observer.route("**/api/v1/state", completed_progress)
    observer.wait_for_function(
        "document.querySelector('.voice-generation-wave')?.getAttribute('aria-valuenow') === '40'"
    )
    check(
        "the waveform resolves according to server progress",
        observer.locator("#voice-generation-clip rect").get_attribute("width") == "256",
    )
    check(
        "generation holds resolved bars steady",
        observer.locator(".voice-generation-fill line").first.evaluate("line => getComputedStyle(line).animationName")
        == "none",
    )
    check(
        "the animation is identified as illustrative",
        "Illustrative waveform" in observer.locator(".voice-generation-note").inner_text(),
    )
    check(
        "progress and elapsed time stay in the shared operation bar",
        observer.locator(".voice-generation-status .num").count() == 0,
    )
    progress_override = {"step": 10, "total": 10}
    observer.wait_for_function(
        "document.querySelector('.voice-generation-wave')?.getAttribute('aria-valuenow') === '99'"
    )
    check(
        "unfinished operations cap progress at ninety-nine",
        observer.locator(".voice-generation-wave").get_attribute("aria-valuenow") == "99",
    )
    check(
        "complete engine steps show a finishing label",
        observer.locator(".voice-generation-status strong").inner_text() == "Finishing audio",
    )
    check(
        "finishing holds the waveform with a subtle shimmer",
        observer.locator(".voice-generation-fill").evaluate("wave => getComputedStyle(wave).animationName")
        == "voice-generation-shimmer",
    )
    observer.emulate_media(reduced_motion="reduce")
    check(
        "reduced motion disables finishing shimmer",
        observer.locator(".voice-generation-fill").evaluate("wave => getComputedStyle(wave).animationName") == "none",
    )
    observer.emulate_media(reduced_motion="no-preference")
    observer.unroute("**/api/v1/state")
    cancel = context.request.post(URL + "/api/v1/operations/" + operation["id"] + "/cancel")
    check("the API operation accepts cancellation", cancel.status == 204)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = context.request.get(URL + "/api/v1/operations/" + operation["id"]).json()
        if state["status"] == "cancelled":
            break
        time.sleep(0.1)
    check("the API operation stops", state["status"] == "cancelled")
    for tab in (page, observer):
        tab.wait_for_function("!document.getElementById('voice-studio').locked")
        check("cancellation removes generation from each tab", tab.locator("#voice-generation").count() == 0)
    check(
        "API cancellation preserves the unsubmitted script",
        page.locator("#voice-text").input_value() == "Keep this unsubmitted draft.",
    )
    check("API cancellation preserves the unsubmitted voice", page.locator("#voice-description").input_value() == VOICE)
    check("the browser reports no page errors", not errors)
    browser.close()
