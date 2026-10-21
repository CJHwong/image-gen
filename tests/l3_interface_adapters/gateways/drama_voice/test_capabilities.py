from studio.l3_interface_adapters.gateways.drama_voice.capabilities import drama_capabilities


def test_drama_declares_only_the_checked_engine_contract():
    caps = drama_capabilities()
    assert (caps.backend_id, caps.name, caps.default_mode, caps.reference_sample_rate) == (
        "drama3",
        "Drama-3",
        "generate",
        44100,
    )
    assert [mode.id for mode in caps.modes] == ["generate", "clone"]
    assert caps.max_batch == 16
    assert caps.mode("generate").max_references == 0
    clone = caps.mode("clone")
    assert clone.min_references == clone.max_references == 1
    transcript = next(param for param in clone.params if param.id == "ref_text")
    assert transcript.required
    defaults = caps.mode("generate").parse_options({})
    assert defaults == {"temperature": 0.7, "top_p": 0.7, "top_k": 30, "max_tokens": 1024}
    assert all(template.target == "text" for template in clone.templates)
    assert caps.loading.repository == "mlx-community/fish-audio-drama-3-8bit"
