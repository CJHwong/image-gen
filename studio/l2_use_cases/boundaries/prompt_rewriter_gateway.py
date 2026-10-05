from abc import ABC, abstractmethod
from collections.abc import Callable

from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite


class PromptRewriterGateway(ABC):
    """One model that lengthens a prompt. Not an image backend, and not part of one.

    It is a second model, so it cannot be resident beside an image engine: the
    caller frees the engines before it runs and frees it before an engine loads.
    Every call runs on the GPU thread, like every other model call.

    An adapter keeps at most one model resident, because a mode maps to a model
    and the two do not both fit.
    """

    @abstractmethod
    def modes(self) -> tuple[str, ...]:
        """The modes this rewriter serves. An empty tuple hides the page's toggle."""

    @abstractmethod
    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        """Lengthen `prompt` for `mode`. `references` are the pictures the run will carry.

        A marked run has no business sending its mask here: the mask is a
        technical picture, and the rewriter is asked about the scene. The caller
        decides what counts as a picture.

        `on_writing` is called once, when the weights are resident and the first
        segment is about to be written. The caller cannot tell a weight load from
        a decode by itself, so the adapter says which side of the load it is on.

        `should_stop` is read before that first segment and between segments, and
        a true answer raises `Cancelled`. So a stop lands within one segment, and
        never during the load, which is one blocking call.
        """

    @abstractmethod
    def release(self) -> None:
        """Free the model memory. The next rewrite brings it back."""
