from abc import ABC, abstractmethod


class ModelResidencyGateway(ABC):
    """Keep one model family as the sole owner of the studio's model memory slot."""

    @abstractmethod
    def activate(self, backend_id: str) -> None:
        """Release a different model before the selected backend runs."""

    @abstractmethod
    def release(self) -> None:
        """Free the current model and leave the slot empty."""
