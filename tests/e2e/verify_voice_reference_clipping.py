"""Real browser decoding, reference limits, focused editors, and capability switches on the stub."""

import sys

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:" + sys.argv[1]


def check(name, value):
    assert value, name
    print("PASS " + name, flush=True)


def choose(page, name, backend):
    page.locator("#backend-toggle").click()
    page.get_by_role("menuitemradio", name=name, exact=True).click()
    page.wait_for_function("backend => voiceStudio.capabilities.backend_id === backend", arg=backend)


with sync_playwright() as tool:
    browser = tool.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL + "/?workspace=voice")
    page.wait_for_function("typeof voiceStudio !== 'undefined' && voiceStudio?.capabilities.backend_id === 'drama3'")
    check("Voice defaults to Drama-3 Generate", page.locator("#voice-mode-generate").is_checked())
    preservation = page.evaluate("""async () => {
      const {waveBytes, normalizeReference} = await import('/page/lib/voice-audio.js');
      const original = waveBytes(Float32Array.from({length: 20*24000}, (_, i) => Math.sin(i*.17)*.8), 24000);
      const bytes = new Uint8Array(await original.arrayBuffer());
      const unchanged = await normalizeReference(original, 24000);
      const clipped = await normalizeReference(original, 24000, 15);
      const selected = new Uint8Array(await clipped.blob.arrayBuffer());
      const metadata = new Uint8Array(bytes.length + 12);
      metadata.set(bytes.subarray(0, 12));
      metadata.set([74,85,78,75,3,0,0,0,1,2,3,0],12);
      metadata.set(bytes.subarray(12),24);
      new DataView(metadata.buffer).setUint32(4, metadata.length-8, true);
      const decorated = new Blob([metadata], {type:'audio/wav'});
      const retained = await normalizeReference(decorated, 24000);
      const excerpt = new Uint8Array(await (await normalizeReference(decorated, 24000, 15)).blob.arrayBuffer());
      const duplicate = new Uint8Array(bytes.length+10);
      duplicate.set(bytes);
      duplicate.set([100,97,116,97,2,0,0,0,0,0], bytes.length);
      const trailing = new Blob([duplicate], {type:'audio/wav'});
      new DataView(duplicate.buffer).setUint32(4, duplicate.length-8, true);
      const ambiguous = new Blob([duplicate], {type:'audio/wav'});
      let decoded = 0;
      const decode = AudioContext.prototype.decodeAudioData;
      AudioContext.prototype.decodeAudioData = function(...args) {decoded++; return decode.apply(this,args);};
      try {
        for (const blob of [trailing, ambiguous]) {
          try {await normalizeReference(blob,24000,15);} catch { /* Invalid containers may be rejected. */ }
        }
      } finally {AudioContext.prototype.decodeAudioData = decode;}
      return {sameBlob:unchanged.blob === original, seconds:clipped.duration, trimmed:clipped.trimmed,
        exact:selected.slice(44).every((sample, i) => sample === bytes[44+i]),
        nativeFrames:(selected.length-44)/2, metadataRetained:retained.blob === decorated,
        metadataExcerpt:excerpt.length === selected.length && excerpt.every((byte,i) => byte === selected[i]),
        ambiguousDecoded:decoded === 2};
    }""")
    check("compatible PCM references keep their original samples", preservation["sameBlob"])
    check(
        "native reference clipping preserves fifteen seconds of exact PCM",
        preservation["seconds"] == 15
        and preservation["trimmed"]
        and preservation["exact"]
        and preservation["nativeFrames"] == 360000,
    )
    check(
        "PCM reference handling accepts padded metadata chunks",
        preservation["metadataRetained"] and preservation["metadataExcerpt"],
    )
    check("ambiguous WAV containers use the validating decoder", preservation["ambiguousDecoded"])
    for width, height in [(1440, 1000), (390, 700)]:
        page.set_viewport_size({"width": width, "height": height})
        bounds = page.locator(".voice-mode-picker").evaluate("""row => {
          const labels = [...row.querySelectorAll('label')].map(el => el.getBoundingClientRect());
          return {equal: Math.abs(labels[0].width-labels[1].width)<1,
            fills: labels[1].right > row.getBoundingClientRect().right-6};
        }""")
        check("two modes fill equal tracks at " + str(width), bounds["equal"] and bounds["fills"])
        field = page.locator("#voice-text")
        field.fill("A long script line.\n" * 30)
        field.evaluate("el => el.blur()")
        compact = field.bounding_box()["height"]
        field.focus()
        check("focused script grows at " + str(width), field.bounding_box()["height"] >= compact + 40)
        field.evaluate("el => el.blur()")
        check(
            "blur restores size and preserves script",
            abs(field.bounding_box()["height"] - compact) < 1 and len(field.input_value()) > 500,
        )
        check(
            "focused editor introduces no horizontal overflow",
            page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
        )
    page.set_viewport_size({"width": 1440, "height": 1000})
    field.focus()
    page.locator(".voice-advanced summary").click()
    check(
        "clicking Advanced while editing opens it",
        page.locator(".voice-advanced").get_attribute("open") is not None,
    )
    page.locator('label[for="voice-mode-clone"]').click()
    # An actual File goes through decoding, normalization, cropping, and WAV encoding.
    page.evaluate("""async () => {
      const {waveBytes} = await import('/page/lib/voice-audio.js');
      window.longReference = new File([waveBytes(new Float32Array(20*48000).fill(.12),48000)],'long.wav',{type:'audio/wav'});
      await voiceStudio.chooseReference(longReference,{transcript:'Words for the entire twenty seconds.'});
    }""")
    info = page.evaluate("""async () => {
      const ref=voiceStudio.reference, bytes=await ref.blob.arrayBuffer();
      return {seconds:ref.duration,trimmed:ref.trimmed,transcript:ref.transcript,rate:new DataView(bytes).getUint32(24,true),samples:(bytes.byteLength-44)/2};
    }""")
    check(
        "long picks become exactly fifteen seconds at native rate",
        info == {"seconds": 15, "trimmed": True, "transcript": "", "rate": 44100, "samples": 661500},
    )
    check(
        "the reference card identifies the excerpt", "First 15 s" in page.locator(".voice-reference-card").inner_text()
    )
    check(
        "Clone asks for the retained excerpt transcript",
        page.locator("#voice-generate").is_disabled()
        and "transcrib" in page.locator("#voice-go-sub").inner_text().lower(),
    )
    awaitable = "!voiceStudio.referencePending && voiceStudio.reference?.duration === 15"
    # A reference restored while globally locked is prepared when the lock clears.
    page.evaluate("""async () => {
      voiceStudio.busy=true; voiceStudio.reference={blob:longReference,name:'restored.wav',duration:20,transcript:'Old full transcript'};
      voiceStudio.configure({capabilities:voiceStudio.capabilities}); await voiceStudio.updateComplete;
    }""")
    check(
        "restoration waits for active work",
        page.evaluate("voiceStudio.reference.duration === 20 && !voiceStudio.referencePending"),
    )
    page.evaluate("voiceStudio.busy=false")
    page.wait_for_function(awaitable)
    check("unlock trims and clears the old transcript", page.evaluate("!voiceStudio.reference.transcript"))
    # Force a model switch between decode and commit in each direction.
    for initial, initial_id, target, target_id, expected in [
        ("AuK", "auk_base", "Drama-3", "drama3", 15),
        ("Drama-3", "drama3", "AuK", "auk_base", 20),
    ]:
        if page.evaluate("voiceStudio.capabilities.backend_id") != initial_id:
            choose(page, initial, initial_id)
        page.evaluate("""() => {
          if(window.decodePatchInstalled) return; window.decodePatchInstalled=true;
          const original=OfflineAudioContext.prototype.startRendering;
          OfflineAudioContext.prototype.startRendering=async function(...args) {
            const result=await original.apply(this,args);
            if(window.holdDecode) {window.holdDecode=false; await new Promise(resolve=>window.releaseDecode=resolve);}
            return result;
          };
        }""")
        page.evaluate("""async () => {
          const {waveBytes}=await import('/page/lib/voice-audio.js');
          window.longReference=new File([waveBytes(new Float32Array(20*48000).fill(.12),48000)],'long.wav',{type:'audio/wav'});
          window.releaseDecode=null; window.holdDecode=true;
          // New Blob identity prevents the decode cache from hiding the race.
          window.pendingReference=voiceStudio.chooseReference(new File([longReference],'race.wav',{type:'audio/wav'}),{transcript:'Original transcript'});
        }""")
        page.wait_for_function("Boolean(window.releaseDecode)")
        context.request.post(URL + "/api/v1/voice/backend", data={"backend": target_id})
        capabilities = context.request.get(URL + "/api/v1/voice/backends/" + target_id).json()
        page.evaluate("caps => voiceStudio.configure({capabilities:caps})", capabilities)
        page.evaluate("async () => {releaseDecode(); await pendingReference;}")
        check(
            "pending normalization follows " + initial + " to " + target,
            page.evaluate("voiceStudio.reference.duration") == expected,
        )
        check(
            "only an actual trim clears the transcript",
            page.evaluate("voiceStudio.reference.transcript") == ("" if expected == 15 else "Original transcript"),
        )
    widths = page.locator(".voice-mode-picker label").evaluate_all(
        "labels => labels.map(el => el.getBoundingClientRect().width)"
    )
    check("AuK's three modes still divide the row evenly", len(widths) == 3 and max(widths) - min(widths) < 1)
    check(
        "AuK retains its longer reference",
        page.evaluate("!voiceStudio.reference.trimmed && voiceStudio.reference.duration === 20"),
    )
    page.locator('label[for="voice-mode-design"]').click()
    field.focus()
    page.get_by_role("button", name="Templates", exact=True).click()
    check("clicking Templates while editing opens it", page.locator("#voice-templates").is_visible())
    check("no page errors", not errors)
    browser.close()
