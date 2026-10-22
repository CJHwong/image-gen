import pytest

from studio.l3_interface_adapters.gateways.audio.auk_runtime.chunks import (
    CHUNK_SECONDS,
    MIN_SECONDS,
    chunk_text,
    estimate_seconds,
)


def test_the_length_counts_han_characters_and_words_at_their_own_rates():
    assert estimate_seconds("大家好" * 53) == pytest.approx(30.0)
    assert estimate_seconds(" ".join(["word"] * 27)) == pytest.approx(10.0)


def test_a_mixed_text_adds_both_rates():
    chinese = "大家好，" * 53  # noqa: RUF001
    assert estimate_seconds(chinese + " ".join(["word"] * 27)) == pytest.approx(40.0)


def test_a_text_too_short_to_measure_still_gets_the_shortest_window():
    assert estimate_seconds("!") == MIN_SECONDS


def test_a_short_text_is_one_chunk():
    assert chunk_text("Hello there. How are you?") == ["Hello there. How are you?"]


def test_sentences_group_into_chunks_that_each_fit_one_call():
    sentence = " ".join(["word"] * 20) + "."  # about 7.4 seconds
    chunks = chunk_text(" ".join([sentence] * 6))
    assert len(chunks) == 2
    assert all(estimate_seconds(chunk) <= CHUNK_SECONDS for chunk in chunks)
    assert chunks[0] == " ".join([sentence] * 3)


def test_chinese_sentences_join_without_a_space():
    sentence = "今天天氣很好。"
    assert chunk_text(sentence * 2) == ["今天天氣很好。今天天氣很好。"]


def test_a_sentence_too_long_for_one_call_splits_at_its_clauses():
    clause = "一二三四五六七八九十" * 5 + "，"  # noqa: RUF001
    chunks = chunk_text(clause * 6 + "。")
    assert len(chunks) > 1
    assert all(estimate_seconds(chunk) <= CHUNK_SECONDS for chunk in chunks)
    assert "".join(chunks) == clause * 6 + "。"


def test_blank_lines_and_trailing_space_leave_no_empty_chunk():
    assert chunk_text("First line.\n\n\nSecond line.   ") == ["First line. Second line."]


def test_a_short_sentence_gets_a_window_that_does_not_cut_its_last_word():
    # "今天天氣很好" at 5.3 characters a second is 1.13 s, and a 1.14 s window lost the last character in 3 of 8 runs.
    assert estimate_seconds("今天天氣很好。") >= 1.5
