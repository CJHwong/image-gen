"""Check completed history across stale drafts and independent browser tabs."""

import sys

from playwright.sync_api import sync_playwright
from voice_helpers import choose_voice_profile

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


def ready(page):
    page.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function(
        "!document.getElementById('voice-studio').loading && document.getElementById('voice-studio').capabilities.modes.length === 3"
    )


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    direct = browser.new_context()
    page = direct.new_page()
    ready(page)
    ownership = page.evaluate("""async () => {
      const {clearVoice, saveVoice, loadVoice} = await import('/page/lib/voice-store.js');
      const take = {id:'old-take', createdAt:Date.now(), duration:1, blob:new Blob(['fixture'])};
      const segment = (id, text, takes=[]) => ({id, text, takes, selected:takes[0]?.id || null, inScript:true});
      const project = (script, segments) => ({script, segments, removed:[], cutoff:0, selectedId:null});
      const current = project('New pending sentence.', [segment('new', 'New pending sentence.')]);
      const completed = project('Old completed sentence.', [segment('old', 'Old completed sentence.', [take])]);
      await clearVoice();
      await saveVoice(current, true);
      await saveVoice(completed, false);
      return loadVoice();
    }""")
    check("a late completion keeps the current draft", ownership["script"] == "New pending sentence.")
    check(
        "a late completion remains outside the current script",
        next(item for item in ownership["segments"] if item["id"] == "old")["inScript"] is False,
    )
    check(
        "a late completion preserves its take",
        next(item for item in ownership["segments"] if item["id"] == "old")["takes"][0]["id"] == "old-take",
    )
    stale_draft = page.evaluate("""async () => {
      const {clearVoice, saveVoice, loadVoice} = await import('/page/lib/voice-store.js');
      const take = {id:'retained-take', createdAt:Date.now(), duration:1, blob:new Blob(['fixture'])};
      const completed = {script:'Completed sentence.', segments:[{id:'completed', text:'Completed sentence.', inScript:true, takes:[take], selected:take.id}], removed:[], cutoff:0};
      const incoming = {script:'New pending sentence.', segments:[{id:'pending', text:'New pending sentence.', inScript:true, takes:[], selected:null}], removed:[], cutoff:0};
      await clearVoice();
      await saveVoice(completed, true);
      await saveVoice(incoming, true);
      return loadVoice();
    }""")
    check("a stale draft keeps the newer draft text", stale_draft["script"] == "New pending sentence.")
    check(
        "a stale draft retains missing completed audio",
        any(
            item["id"] == "completed" and item["takes"][0]["id"] == "retained-take" for item in stale_draft["segments"]
        ),
    )
    check(
        "a stale draft retains missing audio as history",
        next(item for item in stale_draft["segments"] if item["id"] == "completed")["inScript"] is False,
    )
    direct.close()

    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    owner = context.new_page()
    other = context.new_page()
    errors = []
    for current in [owner, other]:
        current.on("pageerror", lambda error: errors.append(str(error)))
        ready(current)
    choose_voice_profile(owner)
    owner.locator("#voice-text").fill("Old sentence from the other tab.")
    owner.evaluate("document.getElementById('voice-studio').saved")
    other.reload()
    other.wait_for_function("document.getElementById('voice-studio').script === 'Old sentence from the other tab.'")
    owner.locator("#voice-text").fill("New sentence in the current draft.")
    owner.evaluate("document.getElementById('voice-studio').saved")
    other.locator("#voice-generate").click()
    for current in [owner, other]:
        current.wait_for_function("document.getElementById('voice-studio').takesCount === 1")
        current.evaluate("document.getElementById('voice-studio').saved")
    check(
        "the submitting tab clears its completed script",
        other.locator("#voice-text").input_value() == "",
    )
    owner.reload()
    owner.wait_for_function(
        "!document.getElementById('voice-studio').loading && document.getElementById('voice-studio').takesCount === 1"
    )
    check(
        "reload keeps the current tab draft",
        owner.locator("#voice-text").input_value() == "New sentence in the current draft.",
    )
    check("reload keeps the other tab result in the gallery", owner.locator(".voice-clip[data-take-id]").count() == 1)
    check(
        "the other tab result cannot join the current script",
        owner.evaluate("document.getElementById('voice-studio').selectedTakes.length") == 0,
    )
    check(
        "the current script remains internally pending",
        owner.evaluate("document.getElementById('voice-studio').pending.length") == 1,
    )
    check("the current draft creates no gallery tile", owner.locator(".voice-clip-pending").count() == 0)
    stored = owner.evaluate("""async () => {
      const {loadVoice} = await import('/page/lib/voice-store.js');
      return loadVoice();
    }""")
    check(
        "both tabs save the late result as history",
        all(item.get("inScript") is False for item in stored["segments"] if item["takes"]),
    )
    check("the browser reports no page errors", not errors)
    browser.close()
