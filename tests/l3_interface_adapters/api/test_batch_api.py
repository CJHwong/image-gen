import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l3_interface_adapters.api.batch_api import normalize_batch


def test_batch_inherits_defaults_and_preserves_varied_settings():
    payload = {
        "kind": "video",
        "backend": "ltx25_mlx",
        "seed": 7,
        "width": 384,
        "items": [{"prompt": "cat"}, {"prompt": "dog", "seed": 8, "width": 512}],
    }
    assert normalize_batch(payload) == [
        {"kind": "video", "backend": "ltx25_mlx", "seed": 7, "width": 384, "prompt": "cat"},
        {"kind": "video", "backend": "ltx25_mlx", "seed": 8, "width": 512, "prompt": "dog"},
    ]
    assert payload["items"][0] == {"prompt": "cat"}


@pytest.mark.parametrize("items", [None, {}, [], ["bad"], [{}] * 17])
def test_batch_requires_one_to_sixteen_item_objects(items):
    with pytest.raises(InvalidJob, match="items"):
        normalize_batch({"kind": "image", "items": items})


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "video"),
        ("backend", "other"),
        ("workspace", "video"),
        ("items", [{}]),
        ("count", 2),
        ("each_reference", True),
        ("total", 2),
        ("index", 2),
        ("reference_token", "old"),
    ],
)
def test_batch_rejects_ambiguous_or_cross_model_items(field, value):
    with pytest.raises(InvalidJob):
        normalize_batch({"kind": "image", "backend": "one", "items": [{field: value}]})


@pytest.mark.parametrize("kind", [None, "rewrite", [], 3])
def test_batch_rejects_unsupported_kinds(kind):
    with pytest.raises(InvalidJob, match="kind"):
        normalize_batch({"kind": kind, "items": [{}]})


def test_voice_batch_uses_the_same_defaults_and_order():
    assert normalize_batch({"kind": "voice", "speaker": "amy", "items": [{"text": "Hello"}, {"text": "Goodbye"}]}) == [
        {"kind": "voice", "speaker": "amy", "text": "Hello"},
        {"kind": "voice", "speaker": "amy", "text": "Goodbye"},
    ]


def test_batch_allows_explicit_matching_workspace_backend_kind_and_one_count():
    assert normalize_batch(
        {
            "kind": "image",
            "backend": "one",
            "items": [
                {
                    "kind": "image",
                    "backend": "one",
                    "workspace": "image",
                    "count": 1,
                    "each_reference": False,
                    "mode": "edit",
                }
            ],
        }
    ) == [
        {"kind": "image", "backend": "one", "workspace": "image", "count": 1, "each_reference": False, "mode": "edit"}
    ]


def test_batch_defaults_cannot_hide_an_image_count():
    with pytest.raises(InvalidJob, match="count"):
        normalize_batch({"kind": "image", "count": 3, "items": [{}]})


@pytest.mark.parametrize("count", [True, "1", 1.0])
def test_batch_count_is_the_integer_one(count):
    with pytest.raises(InvalidJob, match="count"):
        normalize_batch({"kind": "image", "count": count, "items": [{}]})


def test_batch_without_backend_may_only_inherit_the_selected_backend():
    with pytest.raises(InvalidJob, match="backend"):
        normalize_batch({"kind": "image", "items": [{"backend": "one"}]})


@pytest.mark.parametrize("value", [True, False])
def test_video_batch_fast_mode_is_shared_by_all_items(value):
    items = normalize_batch({"kind": "video", "fast_mode": value, "items": [{}, {"fast_mode": value}]})
    assert [item["fast_mode"] for item in items] == [value, value]


def test_video_batch_cannot_override_fast_mode_per_item():
    with pytest.raises(InvalidJob, match="same fast_mode"):
        normalize_batch({"kind": "video", "fast_mode": True, "items": [{"fast_mode": False}]})
