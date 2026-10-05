"""The qwen21 prompt rewriters: the JSON they answer with, and the one model they keep.

mlx-vlm weighs 18.84 GB a card and is imported on the first rewrite, so every test
here stubs it through `heavy_modules` and asserts the arguments the adapter passed
to it. No weights are read and nothing is downloaded.
"""

from unittest.mock import Mock

import pytest
from PIL import Image

from studio.l1_entities.errors import Cancelled
from studio.l3_interface_adapters.gateways.qwen21 import rewriter as rewriter_module
from studio.l3_interface_adapters.gateways.qwen21.rewriter import (
    CACHE_FILES,
    MAX_TOKENS,
    Qwen21Rewriter,
    _as_rewrite,
    _in_the_request_language,
    _system_prompt,
    cache_line,
    in_the_cache,
)
from tests.support.heavy import heavy_modules
from tests.support.images import png


@pytest.fixture
def system_prompt(tmp_path):
    path = tmp_path / "system_prompt.txt"
    path.write_text("You lengthen a request.\n", encoding="utf-8")
    return path


def rewriter_stubs(stream, system_prompt_path):
    """The mlx-vlm and huggingface_hub names this adapter imports, as recording stubs."""
    return {
        "mlx_vlm": {"stream_generate": stream, "load": Mock(return_value=("the model", "the processor"))},
        "mlx_vlm.prompt_utils": {"apply_chat_template": Mock(return_value="the formatted prompt")},
        "mlx_vlm.utils": {"load_config": Mock(return_value={"image_token": "<|image|>"})},
        "huggingface_hub": {"hf_hub_download": Mock(return_value=str(system_prompt_path))},
        "huggingface_hub.logging": {"set_verbosity_error": Mock()},
        "huggingface_hub.utils": {"disable_progress_bars": Mock()},
    }


def writing(*segments):
    """A stream_generate that yields one item per printed segment, the way mlx-vlm does.

    Measured against the installed library, 2026-10-05: each item carries the text
    printed since the last read, and the terminal one carries only the flushed
    tail. So a caller that reads the last item alone loses most of the answer, and
    the test that proves the assembly is the one that splits the JSON in two.
    """
    return Mock(return_value=iter([Mock(text=segment) for segment in segments]))


def answering(text):
    """A stream that writes the whole answer as one segment."""
    return writing(text)


def no_writing():
    pass


def never_stop():
    return False


class NotCached(Exception):
    """The hub's own LocalEntryNotFoundError, which the adapter catches by name."""


def cache_stubs(cached: set[str]) -> dict:
    """A snapshot_download that answers for `cached` and refuses for the rest.

    Nothing is read and nothing is downloaded: the lookup the adapter makes is
    the library's, so the test replaces the library.
    """

    def snapshot_download(repo, **kwargs):
        if repo in cached:
            return f"/hub/{repo}"
        raise NotCached(repo)

    return {
        "huggingface_hub": {"snapshot_download": Mock(side_effect=snapshot_download)},
        "huggingface_hub.errors": {"LocalEntryNotFoundError": NotCached},
    }


def test_a_repo_the_hub_already_holds_is_in_the_cache():
    """The lookup is the library's own, and it asks for the files mlx_vlm will ask
    for, so a cached repo is one whose load downloads nothing."""
    stubs = cache_stubs({"Qwen/PE-T2I"})
    with heavy_modules(stubs):
        assert in_the_cache("Qwen/PE-T2I") is True

    kwargs = stubs["huggingface_hub"]["snapshot_download"].call_args.kwargs
    assert kwargs == {"local_files_only": True, "allow_patterns": list(CACHE_FILES)}


def test_a_repo_the_hub_lacks_is_not_in_the_cache():
    stubs = cache_stubs(set())
    with heavy_modules(stubs):
        assert in_the_cache("Qwen/PE-I2I") is False
    assert stubs["huggingface_hub"]["snapshot_download"].called


def test_the_line_names_every_mode_and_the_size_of_whatever_is_missing():
    """Measured 2026-09-27: the two cards are 18.84 GB each. The line tells the user
    that wait is coming before the Rewrite click, because the progress bar stays off."""
    models = {"generate": "Qwen/PE-T2I", "edit": "Qwen/PE-I2I"}
    with heavy_modules(cache_stubs({"Qwen/PE-T2I", "Qwen/PE-I2I"})):
        assert cache_line(models) == "Rewriters: generate cached, edit cached"
    with heavy_modules(cache_stubs({"Qwen/PE-T2I"})):
        assert cache_line(models) == "Rewriters: generate cached, edit not fetched (18.84 GB on first use)"
    with heavy_modules(cache_stubs({"Qwen/PE-I2I"})):
        assert cache_line(models) == "Rewriters: generate not fetched, edit cached (18.84 GB on first use)"
    with heavy_modules(cache_stubs(set())):
        assert cache_line(models) == "Rewriters: generate not fetched, edit not fetched (18.84 GB each on first use)"


def test_the_system_prompt_is_read_from_the_weights_repo(system_prompt):
    """The card depends on the instructions shipped beside its weights, so they travel
    with the repo rather than with this code."""
    download = Mock(return_value=str(system_prompt))
    with heavy_modules({"huggingface_hub": {"hf_hub_download": download}}):
        assert _system_prompt("Qwen/PE-T2I") == "You lengthen a request."
    assert download.call_args.args == ("Qwen/PE-T2I", "system_prompt.txt")


def test_a_plain_json_answer_carries_the_prompt_the_ratio_and_the_reference_flag():
    """Measured 2026-09-27: no thinking block is emitted at all, so the whole answer is
    already the JSON."""
    answer = _as_rewrite('{"rewritten_prompt": "a pear, longer", "wh_ratio": "3:2", "ratio_follow": true}')
    assert answer.prompt == "a pear, longer"
    assert answer.ratio == "3:2" and answer.follow_reference is True


def test_a_thinking_block_is_dropped_before_the_json():
    answer = _as_rewrite('weighing the request...</think>{"rewritten_prompt": "a pear, longer"}')
    assert answer.prompt == "a pear, longer" and answer.ratio is None


def test_a_fenced_answer_is_unwrapped():
    answer = _as_rewrite('```json\n{"rewritten_prompt": "a pear, longer"}\n```')
    assert answer.prompt == "a pear, longer"


def test_prose_is_kept_as_the_prompt_rather_than_failing_the_click():
    answer = _as_rewrite("A pear on a table, longer.")
    assert answer.prompt == "A pear on a table, longer." and answer.follow_reference is False


def test_a_cjk_request_is_asked_for_in_cjk():
    """Measured 2026-09-27, ten seeds each: a CJK request alone answers in Chinese 10 of
    10, an English one alone drifts into Chinese 2 of 10, and asking for English in the
    request's own words took that to 0 of 10."""
    assert _in_the_request_language("一隻貓在桌上") == "一隻貓在桌上"


def test_an_english_request_is_asked_for_in_english():
    sent = _in_the_request_language("make the sky a sunset")
    assert sent.startswith("make the sky a sunset")  # the request itself is kept
    assert sent.endswith("Write the instruction in English.")


def test_one_stray_cjk_character_does_not_make_the_request_cjk():
    """The test is the share of letters, not the presence of one letter."""
    sent = _in_the_request_language("a cat, 貓, on a table with a lamp and a book")
    assert sent.startswith("a cat, 貓, on a table with a lamp and a book")
    assert sent.endswith("Write the instruction in English.")


def test_a_request_that_is_exactly_half_cjk_is_not_cjk():
    """The share has to be more than half, not half. "a貓" holds two letters and one
    of them is CJK, so it takes the English sentence. This is the only test on the
    boundary: the branch could loosen from `>` to `>=` and nothing else would fail."""
    sent = _in_the_request_language("a貓")
    assert sent.startswith("a貓")
    assert sent.endswith("Write the instruction in English.")


def test_a_request_that_has_no_letters_at_all_is_asked_for_in_english():
    assert _in_the_request_language("1234 !!!").endswith("Write the instruction in English.")


def test_the_rewriter_sends_the_request_and_the_sampling_it_was_measured_at(system_prompt):
    generate = answering('{"rewritten_prompt": "a longer one"}')
    stubs = rewriter_stubs(generate, system_prompt)
    with heavy_modules(stubs):
        rewriter = Qwen21Rewriter({"generate": "Qwen/PE-T2I"})
        answer = rewriter.rewrite("a cat", "generate", (), no_writing, never_stop)

    assert answer.prompt == "a longer one"
    assert stubs["mlx_vlm"]["load"].call_args.args == ("Qwen/PE-T2I",)
    messages = stubs["mlx_vlm.prompt_utils"]["apply_chat_template"].call_args.args[2]
    assert messages[0] == {"role": "system", "content": "You lengthen a request."}
    assert messages[1]["content"].startswith("a cat")
    assert stubs["mlx_vlm.prompt_utils"]["apply_chat_template"].call_args.kwargs == {"num_images": 0}
    assert generate.call_args.args[2] == "the formatted prompt"
    assert generate.call_args.kwargs == {
        "image": None,
        "max_tokens": MAX_TOKENS,
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "enable_thinking": True,
        "verbose": False,
    }
    assert MAX_TOKENS == 16384  # 317 to 505 tokens out, so the budget is never reached


def test_the_answer_is_assembled_from_the_segments_the_stream_yields(system_prompt):
    """The stream hands over a word or two at a time and the last item holds only the
    flushed tail, so the answer is assembled across the loop. This JSON is split in
    two on purpose: reading the last item alone would parse nothing."""
    stream = writing('{"rewritten_', 'prompt": "a longer one"}')
    with heavy_modules(rewriter_stubs(stream, system_prompt)):
        rewriter = Qwen21Rewriter({"generate": "Qwen/PE-T2I"})
        answer = rewriter.rewrite("a cat", "generate", (), no_writing, never_stop)
    assert answer.prompt == "a longer one"


def test_the_writing_phase_is_reported_once_the_weights_are_resident(system_prompt):
    """The caller cannot tell a weight load from a decode from the outside, so the
    adapter is the one that says which side of the load it is on. The page offers a
    cancel from that moment, and not before."""
    phases = []
    with heavy_modules(rewriter_stubs(answering('{"rewritten_prompt": "a longer one"}'), system_prompt)):
        rewriter = Qwen21Rewriter({"generate": "Qwen/PE-T2I"})
        rewriter.rewrite("a cat", "generate", (), lambda: phases.append("writing"), never_stop)
    assert phases == ["writing"]


def test_a_cancel_before_the_first_segment_stops_the_rewrite(monkeypatch, system_prompt):
    """A stop asked for during the load is remembered rather than lost, which is the
    whole point of the page locking its button until the writing starts."""
    parsed = Mock()
    monkeypatch.setattr(rewriter_module, "_as_rewrite", parsed)
    with heavy_modules(rewriter_stubs(answering('{"rewritten_prompt": "a longer one"}'), system_prompt)):
        rewriter = Qwen21Rewriter({"generate": "Qwen/PE-T2I"})
        with pytest.raises(Cancelled):
            rewriter.rewrite("a cat", "generate", (), no_writing, lambda: True)
    assert not parsed.called  # the segment that was generated is dropped, not parsed


def test_a_cancel_between_segments_stops_the_rewrite_mid_answer(monkeypatch, system_prompt):
    """The check sits at the top of the loop, so a stop lands within one segment: one
    more segment is generated and thrown away, and nothing is parsed."""
    parsed = Mock()
    monkeypatch.setattr(rewriter_module, "_as_rewrite", parsed)
    asked = []

    def stop_after_the_first():
        asked.append(True)
        return len(asked) > 1

    stream = writing('{"rewritten_', 'prompt": "a longer one"}')
    with heavy_modules(rewriter_stubs(stream, system_prompt)):
        rewriter = Qwen21Rewriter({"generate": "Qwen/PE-T2I"})
        with pytest.raises(Cancelled):
            rewriter.rewrite("a cat", "generate", (), no_writing, stop_after_the_first)
    assert len(asked) == 2 and not parsed.called


def test_a_reference_reaches_the_card_as_an_image_and_never_as_a_file(system_prompt):
    """mlx-vlm's own process_image calls load_image only for a str, so a PIL image is
    passed straight through and no reference is written to disk."""
    generate = answering('{"rewritten_prompt": "a longer one"}')
    stubs = rewriter_stubs(generate, system_prompt)
    with heavy_modules(stubs):
        rewriter = Qwen21Rewriter({"edit": "Qwen/PE-I2I"})
        rewriter.rewrite("a pear", "edit", (png(32, 24),), no_writing, never_stop)

    images = generate.call_args.kwargs["image"]
    assert [image.size for image in images] == [(32, 24)]
    assert isinstance(images[0], Image.Image) and images[0].mode == "RGB"
    assert stubs["mlx_vlm.prompt_utils"]["apply_chat_template"].call_args.kwargs == {"num_images": 1}


def test_one_model_stays_resident_until_the_other_mode_asks_for_its_own(system_prompt):
    """The two cards do not both fit, so this adapter keeps at most one resident."""
    generate = answering('{"rewritten_prompt": "a longer one"}')
    stubs = rewriter_stubs(generate, system_prompt)
    with heavy_modules(stubs):
        rewriter = Qwen21Rewriter({"generate": "Qwen/PE-T2I", "edit": "Qwen/PE-I2I"})
        rewriter.rewrite("a cat", "generate", (), no_writing, never_stop)
        rewriter.rewrite("a cat", "generate", (), no_writing, never_stop)
        assert stubs["mlx_vlm"]["load"].call_count == 1  # the second rewrite reused it
        rewriter.rewrite("a pear", "edit", (), no_writing, never_stop)
        assert stubs["mlx_vlm"]["load"].call_count == 2
        assert stubs["mlx_vlm"]["load"].call_args.args == ("Qwen/PE-I2I",)

    # Resolving a cached model still prints a line and a progress bar, and this server
    # keeps its terminal quiet.
    assert stubs["huggingface_hub.utils"]["disable_progress_bars"].called
    assert stubs["huggingface_hub.logging"]["set_verbosity_error"].called


def test_the_modes_are_the_ones_the_backend_wired_in():
    assert Qwen21Rewriter({"generate": "Qwen/PE-T2I", "edit": "Qwen/PE-I2I"}).modes() == ("generate", "edit")


def test_release_drops_the_model_and_holds_nothing_when_there_is_nothing_to_drop(monkeypatch, system_prompt):
    freed = Mock()
    monkeypatch.setattr(rewriter_module, "release_mlx_buffers", freed)
    stubs = rewriter_stubs(answering("{}"), system_prompt)
    with heavy_modules(stubs):
        rewriter = Qwen21Rewriter({"generate": "Qwen/PE-T2I"})
        rewriter.release()
        assert freed.call_count == 0  # nothing was resident, so there is nothing to free
        rewriter.rewrite("a cat", "generate", (), no_writing, never_stop)
        rewriter.release()
        assert freed.call_count == 1
        rewriter.rewrite("a cat", "generate", (), no_writing, never_stop)
        assert stubs["mlx_vlm"]["load"].call_count == 2  # the model was rebuilt after the release
