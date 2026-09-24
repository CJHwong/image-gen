import secrets
import threading

from studio.l2_use_cases.boundaries.reference_store_gateway import ReferenceStoreGateway


class InMemoryReferenceStoreGateway(ReferenceStoreGateway):
    """The one thing the server keeps between requests. It never reaches disk.

    The store is capped, so a batch the user abandons cannot pin memory for the
    life of the process: the oldest entry goes first.
    """

    LIMIT = 4

    def __init__(self):
        self.images = {}
        self._lock = threading.Lock()

    def add(self, images):
        token = secrets.token_urlsafe(12)
        with self._lock:
            while len(self.images) >= self.LIMIT:
                self.images.pop(next(iter(self.images)))
            self.images[token] = images
        return token

    def get(self, token):
        with self._lock:
            return self.images.get(token)

    def drop(self, token):
        with self._lock:
            self.images.pop(token, None)
