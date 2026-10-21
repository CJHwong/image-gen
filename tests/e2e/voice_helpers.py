"""Use shared Voice controls through their public browser interface."""


def choose_voice_profile(page):
    page.locator("#voice-templates-toggle").click()
    page.locator("#voice-templates").get_by_role("menuitem", name="Voice profile", exact=True).click()


def create_voice_clips(page, texts):
    for text in texts:
        page.wait_for_function("!document.getElementById('voice-studio').locked")
        if page.locator("#voice-description").count() and not page.locator("#voice-description").input_value():
            choose_voice_profile(page)
        expected = page.evaluate("document.getElementById('voice-studio').takesCount") + 1
        page.locator("#voice-text").fill(text)
        page.locator("#voice-generate").click()
        page.wait_for_function(
            "expected => document.getElementById('voice-studio').takesCount === expected && !document.getElementById('voice-studio').locked",
            arg=expected,
            timeout=120000,
        )


def open_clip_actions(page):
    if not page.locator("#voice-track-menu").is_visible():
        page.locator("#voice-track-toggle").click()


def generate_another_take(page):
    open_clip_actions(page)
    page.locator("#voice-selected-reuse").click()
    page.locator("#voice-generate").click()


def synthetic_microphone(context):
    """Real MediaRecorder input without a platform audio-device dependency.

    Chromium's fake getUserMedia stayed pending on the headless office Mac even
    with permission granted. A WebCodecs audio track supplies deterministic PCM;
    the page still records WebM, decodes it and submits the actual WAV transport.
    """
    context.add_init_script("""(() => {
      navigator.mediaDevices.getUserMedia = async () => {
        const track = new MediaStreamTrackGenerator({kind: 'audio'});
        const writer = track.writable.getWriter();
        let timestamp = 0;
        const samples = Float32Array.from({length: 4800}, (_, i) => Math.sin(i * Math.PI * 2 * 220 / 48000) * .1);
        const timer = setInterval(async () => {
          const frame = new AudioData({format:'f32', sampleRate:48000, numberOfFrames:4800,
            numberOfChannels:1, timestamp, data:samples});
          timestamp += 100000;
          try { await writer.write(frame); } catch (_) {} finally { frame.close(); }
        }, 100);
        const stop = track.stop.bind(track);
        track.stop = () => { clearInterval(timer); stop(); writer.close().catch(() => {}); };
        return new MediaStream([track]);
      };
    })();""")
