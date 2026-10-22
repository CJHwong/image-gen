"""The published reference must offer usable examples and typed discovery records."""

import base64
from dataclasses import asdict, fields

from studio.l1_entities.capabilities import Capabilities, ModeSpec, ParamSpec, Template
from studio.l1_entities.video_capabilities import VideoAdapter, VideoCapabilities
from studio.l3_interface_adapters.api.openapi import openapi_document
from studio.l3_interface_adapters.api.prompt_builder import prepare_prompt
from studio.l3_interface_adapters.controllers.video_controller import video_job
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.capabilities import qwen21_turbo_capabilities
from studio.l3_interface_adapters.gateways.video.shared.capabilities import ltx25_mlx_capabilities


def test_generate_routes_offer_named_payloads_instead_of_generated_defaults():
    document = openapi_document()
    for route in (
        "images/generate",
        "images/edit",
        "videos/generate",
        "videos/edit",
        "images/rewrite",
        "videos/rewrite",
        "operations",
    ):
        media = document["paths"]["/api/v1/" + route]["post"]["requestBody"]["content"]["application/json"]
        assert media["examples"], route
        assert all(example["summary"] and isinstance(example["value"], dict) for example in media["examples"].values())


def test_structured_video_example_uses_the_measured_template():
    document = openapi_document()
    examples = document["paths"]["/api/v1/videos/generate"]["post"]["requestBody"]["content"]["application/json"][
        "examples"
    ]
    body = examples["slow_push_in"]["value"]
    capabilities = ltx25_mlx_capabilities()
    mode = {**asdict(capabilities.mode("generate")), "templates": asdict(capabilities)["templates"]}
    prepared = prepare_prompt(body, mode, video=True)
    job = video_job(prepared, capabilities)
    assert "slowly moves toward the teapot" in job.prompt
    assert job.width == 384 and job.num_frames == 121


def test_custom_no_lora_example_is_a_valid_video_edit_and_never_an_image_example():
    document = openapi_document()
    paths = document["paths"]
    examples = paths["/api/v1/videos/edit"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    body = {
        **examples["custom_no_lora"]["value"],
        "mode": "edit",
        "clip": {"name": "clip.mp4", "data": base64.b64encode(b"clip bytes").decode()},
    }

    job = video_job(body, ltx25_mlx_capabilities())

    assert job.edit is not None and job.edit.lora_file == ""
    assert job.edit.adapter == "custom"
    image_examples = paths["/api/v1/images/edit"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    assert "custom_no_lora" not in image_examples


def test_image_example_uses_the_official_turbo_schedule():
    document = openapi_document()
    examples = document["paths"]["/api/v1/images/generate"]["post"]["requestBody"]["content"]["application/json"][
        "examples"
    ]
    body = examples["product_photo"]["value"]
    capabilities = qwen21_turbo_capabilities()
    options = capabilities.mode("generate").parse_options({key: str(value) for key, value in body.items()})
    assert options["steps"] == 8


def test_discovery_schemas_describe_fields_clients_need_to_build_a_request():
    schemas = openapi_document()["components"]["schemas"]
    for name, record in [
        ("ImageCapabilities", Capabilities),
        ("ImageMode", ModeSpec),
        ("Parameter", ParamSpec),
        ("Template", Template),
        ("VideoCapabilities", VideoCapabilities),
        ("VideoAdapter", VideoAdapter),
    ]:
        assert set(field.name for field in fields(record)) <= set(schemas[name]["properties"]), name
    assert schemas["Studio"]["properties"]["image"]["properties"]["capabilities"]["$ref"].endswith("/ImageCapabilities")
    assert schemas["Studio"]["properties"]["video"]["properties"]["capabilities"]["$ref"].endswith("/VideoCapabilities")


def test_media_examples_identify_replacements_and_keyframe_image_bytes_are_real():
    examples = openapi_document()["paths"]["/api/v1/videos/generate"]["post"]["requestBody"]["content"][
        "application/json"
    ]["examples"]
    encoded = examples["first_keyframe"]["value"]["references"][0]["image"]
    assert base64.b64decode(encoded, validate=True).startswith(b"\x89PNG")
    supplied = examples["supplied_speech"]
    assert "replace" in supplied["description"].lower()
    assert supplied["value"]["audio"]["data"].startswith("<")


def test_voice_discovery_describes_actual_records():
    from studio.l1_entities import voice_capabilities as voice

    schemas = openapi_document()["components"]["schemas"]
    for name, record in [
        ("VoiceCapabilities", voice.Capabilities),
        ("VoiceMode", voice.ModeSpec),
        ("VoiceParameter", voice.ParamSpec),
        ("VoiceTemplate", voice.Template),
        ("LoadingPolicy", voice.LoadingPolicy),
    ]:
        assert {field.name for field in fields(record)} <= set(schemas[name]["properties"]), name


def test_voice_examples_cover_design_clone_and_edit_with_explicit_media_replacements():
    examples = openapi_document()["paths"]["/api/v1/voice/generate"]["post"]["requestBody"]["content"][
        "application/json"
    ]["examples"]
    assert {item["value"]["mode"] for item in examples.values()} == {"generate", "design", "clone", "edit"}
    assert len(examples["designed_narration"]["value"]["voice"]) > 120
    assert examples["clone_reference"]["value"]["reference"]["wav_base64"].startswith("<replace")


def test_batch_examples_obey_the_shared_batch_contract():
    from studio.l2_use_cases.prepare_batch_use_case import PrepareBatchUseCase

    normalize_batch = PrepareBatchUseCase().execute

    document = openapi_document()
    examples = document["paths"]["/api/v1/operations"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    for name, kind in [("image_storyboard", "image"), ("video_shots", "video"), ("voice_segments", "voice")]:
        payload = examples[name]["value"]
        items = normalize_batch(payload)
        assert len(items) == 2
        assert all(item["kind"] == kind for item in items)
    assert "reference" in normalize_batch(examples["voice_segments"]["value"])[1]
    schemas = document["components"]["schemas"]
    assert schemas["BatchRequest"]["properties"]["items"]["maxItems"] == 16
    route = document["paths"]["/api/v1/operations/{id}/items/{index}/result"]["get"]
    assert "audio/wav" in route["responses"]["200"]["content"]


def test_inactive_model_discovery_needs_no_model_switch():
    paths = openapi_document()["paths"]
    for workspace, schema in [("images", "ImageCapabilities"), ("videos", "VideoCapabilities")]:
        route = paths["/api/v1/" + workspace + "/backends/{id}"]["get"]
        assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/" + schema)
        assert route["parameters"][0]["name"] == "id"


def test_voice_template_request_preserves_typed_values_and_automatic_speed_duration():
    document = openapi_document()
    schema = document["components"]["schemas"]["VoiceRequest"]
    assert schema["anyOf"] == [{"required": ["text"]}, {"required": ["template"]}]
    assert schema["properties"]["template"]["type"] == "string"
    values = schema["properties"]["template_values"]["additionalProperties"]
    assert values == {"type": ["string", "number"]}
    examples = document["paths"]["/api/v1/voice/generate"]["post"]["requestBody"]["content"]["application/json"][
        "examples"
    ]
    request = examples["change_speed"]["value"]
    assert request["template"] == "Speed"
    assert request["template_values"] == {"speed": "1.5"}
    assert request["seconds"] == 0
    assert "text" not in request
    batch_values = document["components"]["schemas"]["BatchRequest"]["properties"]["items"]["items"]["properties"][
        "template_values"
    ]
    assert batch_values["additionalProperties"] == {"type": ["string", "number"]}


def test_audio_trim_example_is_a_complete_pcm_request():
    import io
    import wave

    from studio.l3_interface_adapters.api.audio_trim import trim_audio

    operation = openapi_document()["paths"]["/api/v1/audio/trim"]["post"]
    example = operation["requestBody"]["content"]["application/json"]["examples"]["middle_second"]
    selected, duration = trim_audio(example["value"])
    assert duration == 1
    with wave.open(io.BytesIO(selected), "rb") as stream:
        assert stream.getnframes() == 8
    assert "audio/wav" in operation["responses"]["200"]["content"]
    assert "400" in operation["responses"]


def test_voice_model_examples_name_flash_and_base_without_loading():
    paths = openapi_document()["paths"]
    examples = paths["/api/v1/voice/backend"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    assert {item["value"]["backend"] for item in examples.values()} == {"auk", "auk_base"}
    examples = paths["/api/v1/voice/generate"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    assert examples["clone_with_auk"]["value"]["backend"] == "auk_base"


def test_design_template_examples_keep_spoken_text_separate_from_voice_fields():
    document = openapi_document()
    examples = document["paths"]["/api/v1/voice/generate"]["post"]["requestBody"]["content"]["application/json"][
        "examples"
    ]
    request = examples["design_template"]["value"]
    assert request["template"] == "Narration" and request["text"]
    assert "voice" not in request
    assert request["template_values"]["tone"] == "warm and thoughtful"
    schema = document["components"]["schemas"]["VoiceRequest"]
    condition = schema["allOf"][0]["then"]
    assert condition["required"] == ["text"]
    assert condition["anyOf"] == [{"required": ["voice"]}, {"required": ["template"]}]
    batch = document["paths"]["/api/v1/operations"]["post"]["requestBody"]["content"]["application/json"]["examples"][
        "voice_design_templates"
    ]["value"]
    assert batch["kind"] == "voice" and len(batch["items"]) == 2
    assert all(item["template"] and item["text"] for item in batch["items"])


def test_voice_prompt_references_are_discoverable_and_do_not_claim_upstream_api_features():
    from urllib.parse import urlsplit

    document = openapi_document()
    guides = document["x-voice-prompt-guides"]
    assert len(guides) >= 20
    assert {backend for guide in guides for backend in guide["models"]} == {"drama3", "auk", "auk_base"}
    assert all(urlsplit(guide["url"]).scheme == "https" and guide["scope"] and guide["topics"] for guide in guides)
    assert {urlsplit(guide["url"]).hostname for guide in guides} <= {
        "docs.fish.audio",
        "huggingface.co",
        "speech.fish.audio",
        "sgl-project.github.io",
        "recipes.vllm.ai",
        "github.com",
        "auk-project.github.io",
    }
    voice = next(tag for tag in document["tags"] if tag["name"] == "voice")
    for guide in guides:
        assert guide["url"] in voice["description"]
    assert "Studio does not expose" in voice["description"]
    assert "previous_takes" in voice["description"] and "multi-reference speaker casting" in voice["description"]
    assert "Unknown top-level fields" in voice["description"] and "ignored, not rejected" in voice["description"]
    for path in ["/api/v1/voice/generate", "/api/v1/voice/backends/{id}", "/api/v1/voice/capabilities"]:
        operation = next(iter(document["paths"][path].values()))
        assert "https://docs.fish.audio/features/text-to-speech/drama-3" in operation["description"]
        assert "https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COOKBOOK.md" in operation["description"]
    guides[0]["models"].clear()
    assert openapi_document()["x-voice-prompt-guides"][0]["models"] == ["drama3"]


def test_visual_prompt_guides_are_available_at_model_discovery_and_generation():
    document = openapi_document()
    tags = {tag["name"]: tag["description"] for tag in document["tags"]}
    image_link = "https://huggingface.co/Qwen/Qwen-Image-2.1"
    video_link = "https://docs.ltx.io/api-documentation/implementation-guides/prompting-guide"
    assert image_link in tags["images"]
    assert video_link in tags["videos"]
    assert "not a separate comprehensive 2.1 prompt manual" in tags["images"]
    assert "multi-shot section is explicitly about LTX-2.5" in tags["videos"]
    assert "discovered modes" in tags["videos"]
    assert "automatically enhances LTX Generate" in tags["videos"]
    operations = {
        operation["operationId"]: operation for path in document["paths"].values() for operation in path.values()
    }
    for name in ("generateImage", "editImage", "readImageBackend"):
        assert image_link in operations[name]["description"]
    for name in ("generateVideo", "editVideo", "readVideoBackend"):
        assert video_link in operations[name]["description"]


def test_drama_token_default_matches_capabilities_and_named_example():
    from studio.l3_interface_adapters.gateways.audio.drama3.capabilities import drama_capabilities

    document = openapi_document()
    default = document["components"]["schemas"]["VoiceRequest"]["properties"]["max_tokens"]["default"]
    example = document["paths"]["/api/v1/voice/generate"]["post"]["requestBody"]["content"]["application/json"][
        "examples"
    ]["drama_delivery"]["value"]
    assert (
        default
        == example["max_tokens"]
        == drama_capabilities().mode("generate").parse_options({})["max_tokens"]
        == 2048
    )


def test_video_rewrite_describes_real_image_grounding_and_cache_identity():
    route = openapi_document()["paths"]["/api/v1/videos/rewrite"]["post"]
    assert "vision tower" in route["description"]
    assert "first reference image" in route["description"]
    sample = route["requestBody"]["content"]["application/json"]["examples"]["animate_reference"]
    assert base64.b64decode(sample["value"]["references"][0]["png_base64"], validate=True).startswith(b"\x89PNG")
    assert "same first image" in sample["description"]
