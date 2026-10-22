# ruff: noqa: RUF001
"""How long a text takes to say, and where to split a text too long for one call.

AuK does not choose a length: it fills the length it is given. So the length is
estimated from the text. The rates were measured on AuK's own clones: 5.3 Han
characters per second. English is 2.7 words per second.

The length is a window the words are fitted into, so a window that is too short cuts the
end of the last word. A six-character clone with a 1.14 s window lost its last character
in 3 of 8 runs. With 1.5 s it lost none in 8 runs, so no window is shorter than that.

One call holds about 25 seconds: a 24-second clone read 6 of 6 hard words. Longer
text is split at sentence ends, and a sentence still too long at clause marks.
"""

import re

HAN_PER_SECOND = 5.3
WORDS_PER_SECOND = 2.7
MIN_SECONDS = 1.5
CHUNK_SECONDS = 25.0

HAN = re.compile(r"[㐀-䶿一-鿿]")
WORD = re.compile(r"[A-Za-z0-9]+(?:['.][A-Za-z0-9]+)*")
SENTENCE_END = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+|\n+")
CLAUSE_END = re.compile(r"(?<=[，、,：:])")


def estimate_seconds(text: str) -> float:
    return max(MIN_SECONDS, len(HAN.findall(text)) / HAN_PER_SECOND + len(WORD.findall(text)) / WORDS_PER_SECOND)


def _split_long(piece: str) -> list[str]:
    if estimate_seconds(piece) <= CHUNK_SECONDS:
        return [piece]
    return [part for part in CLAUSE_END.split(piece) if part.strip()]


def chunk_text(text: str) -> list[str]:
    """Group sentences into chunks of up to CHUNK_SECONDS of speech each."""
    pieces = [
        part for sentence in SENTENCE_END.split(text) if sentence.strip() for part in _split_long(sentence.strip())
    ]
    chunks: list[str] = []
    for piece in pieces:
        if chunks and estimate_seconds(chunks[-1] + piece) <= CHUNK_SECONDS:
            chunks[-1] = chunks[-1] + (" " if WORD.match(piece) else "") + piece
        else:
            chunks.append(piece)
    return chunks
