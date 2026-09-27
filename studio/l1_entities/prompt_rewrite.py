"""What a prompt rewriter hands back.

A rewriter is not an image backend. It reads the loose words in the prompt box
and writes a longer instruction for the image model, then it gets out of the
way. The shape it suggests travels as a ratio, not as one of this backend's
size ids, because the rewriter is a different model with its own idea of what
fits an image, and only the mode knows which sizes it offers.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptRewrite:
    prompt: str
    """The longer instruction, in English, ready to send to the image model."""

    ratio: str | None = None
    """A shape such as "3:2", or None when the rewriter suggested none."""

    follow_reference: bool = False
    """Render at the shape of the picture the run already carries."""
