import pytest

from studio.l3_interface_adapters.gateways.in_memory_reference_store_gateway import InMemoryReferenceStoreGateway
from tests.support.images import png

REFERENCE = (png(8, 8),)
OTHER = (png(4, 4),)


@pytest.fixture
def store():
    return InMemoryReferenceStoreGateway()


def test_an_added_reference_comes_back_under_its_token(store):
    # The page sends the images once, and every later image of the batch carries
    # only the token. A token that did not find them back would break the batch.
    token = store.add(REFERENCE)
    assert store.get(token) == REFERENCE


def test_a_second_add_gets_its_own_token(store):
    first = store.add(REFERENCE)
    second = store.add(OTHER)
    assert first != second
    assert store.get(first) == REFERENCE


def test_an_unknown_token_holds_nothing(store):
    assert store.get("no-such-token") is None


def test_a_dropped_token_holds_nothing(store):
    token = store.add(REFERENCE)
    store.drop(token)
    assert store.get(token) is None


def test_the_oldest_reference_goes_when_the_store_is_full(store):
    # The store is capped, so a batch the user abandons cannot pin memory for the
    # life of the process. The newest entry has to survive its own add.
    tokens = [store.add(REFERENCE) for _ in range(store.LIMIT + 1)]
    assert store.get(tokens[0]) is None
    assert all(store.get(token) is not None for token in tokens[1:])
