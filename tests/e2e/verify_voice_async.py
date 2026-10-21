"""Check progressive Voice batches, cancellation, and transient result failures.

Run against a fresh `uv run studio --stub --all-backends --port <port>`.
"""

import sys
import time

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile

URL = "http://127.0.0.1:" + sys.argv[1]
VOICE = "A calm woman in her thirties with a warm, clear voice and a neutral American accent."


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    owner = context.new_page()
    observer = context.new_page()
    errors = []
    for page in (owner, observer):
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
        page.goto(URL + "/?workspace=voice")
        page.wait_for_function("document.getElementById('voice-studio').capabilities.modes.length === 3")
    choose_voice_profile(owner)
    submitted = context.request.post(
        URL + "/api/v1/operations",
        data={
            "kind": "voice",
            "mode": "design",
            "voice": VOICE,
            "seconds": 1,
            "items": [{"text": f"This is independent recording {index}."} for index in range(16)],
        },
    )
    check("the explicit API batch is accepted", submitted.status == 202)
    observer.wait_for_function("document.getElementById('voice-studio').takesCount > 0")
    operation = context.request.get(URL + "/api/v1/state").json()["active"]
    check("completed takes appear before the batch finishes", operation["status"] == "running")
    owner.wait_for_function("document.getElementById('voice-studio').locked")
    check("the first tab sidebar locks during the API batch", owner.locator("#form").evaluate("form => form.inert"))
    check("the observer sidebar locks during the batch", observer.locator("#form").evaluate("form => form.inert"))
    response = context.request.post(URL + "/api/v1/operations/" + operation["id"] + "/cancel")
    check("the batch accepts cancellation", response.status == 204)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = context.request.get(URL + "/api/v1/operations/" + operation["id"]).json()
        if state["status"] == "cancelled":
            break
        time.sleep(0.1)
    check("the batch stops", state["status"] == "cancelled")
    manifest = context.request.get(URL + state["result_url"]).json()
    count = len(manifest["items"])
    check("cancellation retains completed takes", 0 < count < 16)
    for page in (owner, observer):
        page.wait_for_function("count => document.getElementById('voice-studio').takesCount === count", arg=count)
    check("both tabs receive every completed take exactly once", True)
    observer.wait_for_function("!document.getElementById('form').inert")
    check("the sidebar unlocks after cancellation", True)

    owner.evaluate("""() => {
      const original = window.fetch;
      window.failVoiceResult = true;
      window.fetch = function(input, options) {
        const url = String(input);
        if (window.failVoiceResult && url.includes('/operations/') && url.endsWith('/result')) {
          return Promise.reject(new Error('Temporary result outage'));
        }
        return original.call(this, input, options);
      };
    }""")
    owner.locator("#voice-text").fill("This line survives a brief network outage.")
    owner.locator("#voice-generate").click()
    owner.wait_for_function("!document.getElementById('voice-studio').busy")
    owner.evaluate("window.failVoiceResult = false")
    owner.wait_for_function(
        "document.getElementById('voice-studio').segments.some(segment => segment.text.includes('network outage') && segment.takes.length > 0)"
    )
    check("the owner recovers a result after a transient fetch failure", True)
    long_script = "\n".join(f"Long script sentence {index}." for index in range(20))
    before = owner.evaluate("document.getElementById('voice-studio').takesCount")
    choose_voice_profile(owner)
    owner.locator("#voice-text").fill(long_script)
    check("a long script can generate one recording", owner.locator("#voice-generate").is_enabled())
    with owner.expect_request(
        lambda request: request.url.endswith("/voice/operations") and request.method == "POST"
    ) as pending:
        owner.locator("#voice-generate").click()
    payload = pending.value.post_data_json
    check("the complete script is one API input", payload["text"] == long_script and "items" not in payload)
    check(
        "Design keeps its mode without a finished script reference",
        payload["mode"] == "design" and "reference" not in payload,
    )
    owner.wait_for_function("!document.getElementById('voice-studio').busy")
    check(
        "a long script adds exactly one recording",
        owner.evaluate("document.getElementById('voice-studio').takesCount") == before + 1,
    )
    choose_voice_profile(owner)
    owner.locator(".voice-advanced summary").click()
    owner.locator("#voice-convert").select_option("off")
    owner.locator("#voice-text").fill("A recording with character conversion disabled.")
    with owner.expect_request(
        lambda request: request.url.endswith("/voice/operations") and request.method == "POST"
    ) as pending:
        owner.locator("#voice-generate").click()
    check("a conversion change starts a matching voice design", pending.value.post_data_json["mode"] == "design")
    owner.wait_for_function("!document.getElementById('voice-studio').busy")
    check(
        "recordings retain their character conversion setting",
        owner.evaluate(
            "document.getElementById('voice-studio').segments.flatMap(segment => segment.takes).some(take => take.convert === 'off')"
        ),
    )
    check("there are no unhandled browser errors", not errors)
    browser.close()
