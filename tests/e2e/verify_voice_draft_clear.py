"""Check conditional draft clears in the browser's IndexedDB transaction."""

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, condition):
    assert condition, name
    print("PASS " + name, flush=True)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    page = browser.new_page()
    page.goto(URL + "/page/lib/voice-store.js")
    results = page.evaluate("""async () => {
      const {clearVoice, saveVoice, loadVoice} = await import('/page/lib/voice-store.js');
      const take = (id, createdAt=100) => ({id, createdAt, blob:new Blob(['fixture'])});
      const segment = (id, takes=[]) => ({id, text:id, takes, inScript:true, selected:takes[0]?.id || null});
      const project = (draftId, script, segments=[]) => ({draftId, script, voice:script, segments, selectedId:null, removed:[], cutoff:0});
      const completed = project('submitted', 'Submitted script', [segment('completed', [take('audio')])]);
      const cleared = project('cleared', '', [segment('completed', [take('audio')])]);
      await clearVoice();
      await saveVoice(completed, true);
      await saveVoice(cleared, true, null, 'submitted');
      const matching = await loadVoice();
      await clearVoice();
      await saveVoice(project('newer', 'New script', [segment('pending')]), true);
      await saveVoice(cleared, true, null, 'submitted');
      const stale = await loadVoice();
      await clearVoice();
      const removed = project('newer', 'Preserved script', [segment('pending')]);
      removed.removed = ['deleted'];
      removed.cutoff = 50;
      await saveVoice(removed, true);
      const old = project('cleared', '', [segment('history', [take('deleted'), take('cutoff', 50), take('kept', 51)])]);
      await saveVoice(old, true, null, 'submitted');
      const filtered = await loadVoice();
      await saveVoice(project('unconditional', 'Explicit update'), true);
      const unconditional = await loadVoice();
      await clearVoice();
      const legacy = project(undefined, 'Legacy script', [segment('legacy')]);
      await saveVoice(legacy, true);
      await saveVoice(cleared, true, null, null);
      const legacyMatching = await loadVoice();
      await clearVoice();
      await saveVoice(project('newer', 'Newer than legacy'), true);
      await saveVoice(cleared, true, null, null);
      const legacyStale = await loadVoice();
      await clearVoice();
      return {matching, stale, filtered, unconditional, legacyMatching, legacyStale};
    }""")
    check("a matching completion clears the script", results["matching"]["script"] == "")
    check("a matching completion clears the voice", results["matching"]["voice"] == "")
    check("a matching completion saves the new draft ID", results["matching"]["draftId"] == "cleared")
    check("a matching completion retains its audio", results["matching"]["segments"][0]["takes"][0]["id"] == "audio")
    check("a stale completion preserves newer script", results["stale"]["script"] == "New script")
    check("a stale completion preserves newer voice", results["stale"]["voice"] == "New script")
    check("a stale completion preserves newer draft ID", results["stale"]["draftId"] == "newer")
    check("a stale completion preserves pending input", results["stale"]["segments"][0]["id"] == "pending")
    history = next(segment for segment in results["stale"]["segments"] if segment["id"] == "completed")
    check("a stale completion merges its audio", history["takes"][0]["id"] == "audio")
    check("a stale completion adds history outside the script", history["inScript"] is False)
    filtered = next(segment for segment in results["filtered"]["segments"] if segment["id"] == "history")
    check("a stale completion respects removal and cutoff", [take["id"] for take in filtered["takes"]] == ["kept"])
    check("three-argument draft saves still replace inputs", results["unconditional"]["script"] == "Explicit update")
    check("a matching legacy completion clears inputs", results["legacyMatching"]["script"] == "")
    check("a matching legacy completion saves its new draft ID", results["legacyMatching"]["draftId"] == "cleared")
    check("a stale legacy completion preserves newer inputs", results["legacyStale"]["script"] == "Newer than legacy")
    check(
        "a stale legacy completion merges completed audio",
        results["legacyStale"]["segments"][0]["takes"][0]["id"] == "audio",
    )
    page.evaluate("""async () => {
      const {saveVoice} = await import('/page/lib/voice-store.js');
      await saveVoice({script:'A restored legacy script.', voice:'A calm clear narrator.', mode:'design',
        segments:[{id:'legacy-input', text:'A restored legacy script.', takes:[], selected:null, inScript:true}],
        removed:[], cutoff:0}, true);
    }""")
    page.context.request.post(URL + "/api/v1/voice/backend", data={"backend": "auk_base"})
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("""() => {
      const studio = document.getElementById('voice-studio');
      return studio && !studio.loading && studio.ready;
    }""")
    check(
        "the browser restores the legacy script",
        page.locator("#voice-text").input_value() == "A restored legacy script.",
    )
    page.locator("#voice-generate").click()
    page.wait_for_function("""() => {
      const studio = document.getElementById('voice-studio');
      return studio.takesCount === 1 && !studio.locked;
    }""")
    page.evaluate("document.getElementById('voice-studio').saved")
    check("generation clears the unedited legacy script", page.locator("#voice-text").input_value() == "")
    page.reload()
    page.wait_for_function("!document.getElementById('voice-studio').loading")
    check("reload keeps the legacy script cleared", page.locator("#voice-text").input_value() == "")
    check("reload keeps the legacy voice cleared", page.locator("#voice-description").input_value() == "")
    check("reload retains the generated legacy audio", page.locator(".voice-clip[data-take-id]").count() == 1)
    browser.close()
