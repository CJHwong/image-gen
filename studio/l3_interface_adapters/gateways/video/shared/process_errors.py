"""Explain LTX engine failures while preserving their original diagnostic tail."""

from collections import deque

TAIL_LINES = 12

# What a failed weight fetch looks like, and the step it needs. The first run downloads
# about 72 GB, so the common failure is an unprepared machine, not a broken render. The
# tail stays after the hint: the class name and the status are what a report needs.
FETCH_FIXES = (
    (
        ("gatedrepoerror", "cannot access gated repo"),
        "The weights sit in a gated repo. Accept its terms on the model page and run "
        "`uv run hf auth login` once, then run this again.",
    ),
    (
        ("repositorynotfounderror", "repository not found"),
        "No Hugging Face repo has that id. Check the pack id under [mlx_video] in studio.toml.",
    ),
    (
        ("connectionerror", "maxretryerror", "nameresolutionerror"),
        "The studio could not reach Hugging Face. Check the network, then run this again.",
    ),
)


def crash_report(return_code: int, recent: deque[str]) -> str:
    tail = " | ".join(list(recent)[-TAIL_LINES:])
    if not tail:
        return f"MLX video pipeline failed with exit status {return_code} and said nothing."
    hint = fetch_fix(tail)
    lead = f"{hint} " if hint else ""
    return f"{lead}MLX video pipeline failed with exit status {return_code}. Its last lines: {tail}"


def fetch_fix(tail: str) -> str:
    lowered = tail.lower()
    for needles, fix in FETCH_FIXES:
        if any(needle in lowered for needle in needles):
            return fix
    return ""
