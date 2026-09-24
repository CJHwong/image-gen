from abc import ABC, abstractmethod

from studio.l1_entities.image_job import ReferenceImage


class ReferenceStoreGateway(ABC):
    """Reference images held for the life of one batch, under a token.

    The page sends the images once. Every later image of the batch carries only
    the token, so a large image is not posted again for each one.
    """

    @abstractmethod
    def add(self, images: tuple[ReferenceImage, ...]) -> str:
        """Hold the images and return their token."""

    @abstractmethod
    def get(self, token: str) -> tuple[ReferenceImage, ...] | None:
        """None when the token is unknown or was dropped."""

    @abstractmethod
    def drop(self, token: str) -> None: ...
