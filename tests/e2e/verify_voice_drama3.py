"""Check Drama-3's capability-driven Voice form against a fresh stub server."""

import base64
import io
import sys
import time
import wave

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("document.getElementById('voice-studio')?.capabilities?.backend_id === 'auk_base'")
    page.locator('label[for="voice-mode-edit"]').click()
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name="Drama-3", exact=True).click()
    page.wait_for_function("document.getElementById('voice-studio').capabilities?.backend_id === 'drama3'")
    check("unsupported Edit reconciles to Generate", page.locator("#voice-mode-generate").is_checked())
    check("Drama exposes Generate and Clone", page.locator('input[name="voice-mode"]').count() == 2)
    check("Drama hides voice description", page.locator("#voice-description").count() == 0)
    check("Generate needs no reference", page.locator("#voice-reference").count() == 0)
    page.locator("details.voice-advanced").evaluate("(element) => element.open = true")
    check("Drama hides duration and Chinese conversion", page.locator("#voice-seconds, #voice-convert").count() == 0)
    check("Drama offers native sampling controls", page.locator("#voice-param-temperature").count() == 1)
    check("Generate names the missing script", "script" in page.locator("#voice-go-sub").inner_text().lower())
    page.locator("#voice-templates-toggle").click()
    page.get_by_role("menuitem", name="Whisper", exact=True).click()
    check("delivery template writes an inline cue", "[whispers]" in page.locator("#voice-text").input_value())
    page.locator("#voice-param-temperature").fill("0.9")
    script = "This recording belongs to Drama three."
    page.locator("#voice-text").fill(script)
    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/voice/operations")
    ) as request:
        page.locator("#voice-generate").click()
    payload = request.value.post_data_json
    check("plain script does not carry an old template", payload["text"] == script and "template" not in payload)
    check("Drama does not send AuK settings", not {"voice", "seconds", "convert", "reference"} & payload.keys())
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 1 && !document.getElementById('voice-studio').locked"
    )
    check(
        "successful generation clears model-specific inputs",
        page.evaluate("Object.keys(voiceStudio.engineOptions).length === 0"),
    )
    check("one script produces one gallery clip", page.locator(".voice-clip[data-take-id]").count() == 1)
    check("Drama has no unsupported Edit action", page.locator("#voice-selected-edit").count() == 0)
    page.wait_for_function("document.getElementById('voice-studio').previewReady")
    page.locator("#voice-track-toggle").click()
    page.locator("#voice-selected-clone").click()
    page.wait_for_function("voiceStudio.reference && !voiceStudio.referencePending")
    check("full clip handoff prefills transcript", page.locator("#voice-reference-text").input_value() == script)
    page.locator("#voice-text").fill("A new sentence with the same voice.")
    page.locator("#voice-reference-text").fill("")
    check(
        "Clone names the missing transcript",
        page.locator("#voice-generate").is_disabled()
        and "transcrib" in page.locator("#voice-go-sub").inner_text().lower(),
    )
    page.locator("#voice-reference-text").fill(script)
    page.evaluate("document.getElementById('voice-studio').saved")
    page.reload()
    page.wait_for_function("document.getElementById('voice-studio').capabilities?.backend_id === 'drama3'")
    check("refresh keeps the Clone transcript", page.locator("#voice-reference-text").input_value() == script)
    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/voice/operations")
    ) as request:
        page.locator("#voice-generate").click()
    check("Clone submits the transcript", request.value.post_data_json["ref_text"] == script)
    page.wait_for_function(
        "document.getElementById('voice-studio').takesCount === 2 && !document.getElementById('voice-studio').locked"
    )
    page.wait_for_function("document.getElementById('voice-studio').previewReady")
    preview = page.locator("audio-preview")
    preview.get_by_role("spinbutton", name="Selection start", exact=True).fill("0.2")
    preview.get_by_role("spinbutton", name="Selection start", exact=True).press("Tab")
    page.locator("#voice-track-toggle").click()
    page.locator("#voice-selected-clone").click()
    page.wait_for_function("voiceStudio.reference && !voiceStudio.referencePending")
    check("trimmed audio requires a corrected transcript", page.locator("#voice-reference-text").input_value() == "")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(b"\x00\x10" * 44100)
    page.get_by_role("button", name="Clear voice reference", exact=True).click()
    page.locator("#voice-reference").set_input_files(
        {"name": "native.wav", "mimeType": "audio/wav", "buffer": buffer.getvalue()}
    )
    page.wait_for_function(
        "document.getElementById('voice-studio').reference && !document.getElementById('voice-studio').referencePending"
    )
    rate = page.evaluate(
        "async () => new DataView(await document.getElementById('voice-studio').reference.blob.arrayBuffer()).getUint32(24, true)"
    )
    check("Drama references preserve 44.1 kHz", rate == 44100)
    native = page.evaluate(
        """async encoded => {
      const preview = document.createElement('audio-preview');
      document.body.append(preview);
      preview.blob = new Blob([Uint8Array.from(atob(encoded), x => x.charCodeAt(0))], {type:'audio/wav'});
      await preview.updateComplete; await preview._loading;
      preview.start = 0.2; preview.end = 0.8;
      const event = new Promise(resolve => preview.addEventListener('audio-preview-action', resolve, {once:true}));
      await preview.action('clone');
      const bytes = await (await event).detail.blob.arrayBuffer();
      preview.remove();
      return {rate: new DataView(bytes).getUint32(24, true), samples: (bytes.byteLength - 44) / 2};
    }""",
        base64.b64encode(buffer.getvalue()).decode(),
    )
    check("selected exports preserve native rate and samples", native == {"rate": 44100, "samples": 26460})
    document = context.request.get(URL + "/api/v1/voice/backends/drama3").json()
    check(
        "discovery describes the same default and sample rate",
        document["default_mode"] == "generate" and document["reference_sample_rate"] == 44100,
    )
    accepted = context.request.post(
        URL + "/api/v1/operations", data={"kind": "voice", "backend": "drama3", "text": "Default synthesis."}
    ).json()
    check("API omitted mode selects Generate", accepted["mode"] == "generate")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = context.request.get(URL + "/api/v1/operations/" + accepted["id"]).json()
        if state["status"] not in ["running", "stopping"]:
            break
        time.sleep(0.1)
    check("API synthesis succeeds without a voice description", state["status"] == "succeeded")
    page.locator('label[for="voice-mode-clone"]').click()
    page.locator("#voice-templates-toggle").click()
    page.get_by_role("menuitem", name="Whisper", exact=True).click()
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name="AuK", exact=True).click()
    page.wait_for_function("voiceStudio.capabilities?.backend_id === 'auk_base'")
    check(
        "Clone model switches clear incompatible templates",
        page.evaluate(
            "voiceStudio.mode === 'clone' && !voiceStudio.templateName && Object.keys(voiceStudio.engineOptions).length === 0"
        ),
    )
    page.locator("details.voice-advanced").evaluate("(element) => element.open = true")
    page.locator("#voice-seconds").fill("8")
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name="Drama-3", exact=True).click()
    page.wait_for_function("voiceStudio.capabilities?.backend_id === 'drama3'")
    check(
        "hidden AuK duration cannot label Drama output",
        "Automatic duration" in page.locator("details.voice-advanced summary").inner_text(),
    )
    page.locator("details.voice-advanced").evaluate("(element) => element.open = true")
    page.locator("#voice-param-temperature").fill("1.1")
    page.evaluate("voiceStudio.saved")
    pending = []
    page.route("**/api/v1/state", lambda route: pending.append(route))
    page.reload()
    page.wait_for_function("document.getElementById('voice-studio')?.loading === false")
    for route in list(pending):
        route.continue_()
    page.unroute("**/api/v1/state")
    page.wait_for_function("voiceStudio.capabilities?.backend_id === 'drama3'")
    check(
        "early draft restoration keeps model-specific settings",
        page.evaluate("voiceStudio.engineOptions.temperature") == 1.1,
    )
    joined = page.evaluate("""async () => {
      const {joinAudio, waveBytes} = await import('/page/lib/voice-audio.js');
      const blob = await joinAudio([waveBytes(new Float32Array(44100), 44100), waveBytes(new Float32Array(48000), 48000)], 0);
      const bytes = await blob.arrayBuffer();
      return {rate:new DataView(bytes).getUint32(24, true), samples:(bytes.byteLength - 44) / 2};
    }""")
    check("joined mixed-rate exports preserve the highest native rate", joined == {"rate": 48000, "samples": 96000})
    page.evaluate("""async () => {
      const studio = voiceStudio;
      const {waveBytes} = await import('/page/lib/voice-audio.js');
      const blob = waveBytes(new Float32Array(16 * 44100), 44100);
      await studio.useSelection({detail:{action:'clone',blob,start:0,end:16,name:'long-gallery.wav'}});
      studio.reference = {...studio.reference, transcript:'A long reference.'};
      studio.setScript('A short script.');
      await studio.updateComplete;
    }""")
    check(
        "overlong gallery Clone uses the first fifteen seconds",
        page.evaluate("voiceStudio.reference.duration === 15 && voiceStudio.reference.trimmed"),
    )
    posted = []
    page.on(
        "request",
        lambda request: (
            posted.append(request.url)
            if request.method == "POST" and request.url.endswith("/voice/operations")
            else None
        ),
    )
    page.evaluate(
        "voiceStudio.reference = {...voiceStudio.reference, duration:16}; voiceStudio.generate({id:'length-check',text:'A short script.'})"
    )
    check(
        "direct single-item generation enforces the same reference limit",
        not posted and "15 seconds" in page.evaluate("voiceStudio.error"),
    )
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name="AuK", exact=True).click()
    page.wait_for_function("voiceStudio.capabilities?.backend_id === 'auk_base'")
    check("AuK accepts its longer supported reference", not page.locator("#voice-generate").is_disabled())
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name="Drama-3", exact=True).click()
    page.wait_for_function("voiceStudio.capabilities?.backend_id === 'drama3'")
    page.wait_for_function("!voiceStudio.referencePending && voiceStudio.reference.duration === 15")
    check(
        "switching models automatically trims to the reference limit",
        not page.locator("#voice-generate").is_disabled(),
    )
    check("the browser reports no page errors", not errors)
    browser.close()
