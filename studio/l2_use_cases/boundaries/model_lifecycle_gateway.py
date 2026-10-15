from abc import ABC, abstractmethod


class ModelLifecycleGateway(ABC):
    """The one operation the studio needs to return a model's memory."""

    @abstractmethod
    def release(self) -> None:
        """Free this model's memory, if it is resident."""
