"""The OpenAPI document for the studio's JSON API.

Written as data, not generated: the routes are a handful and their shapes are the use
cases' own types, so a generator would add a dependency just to describe these routes.
A test walks the routes in http_server and the paths here, and fails when one is
missing from the other, which is the part a generator would otherwise guarantee.
"""

from copy import deepcopy
from typing import Any, cast

from studio.l3_interface_adapters.api.api_guidance import GUIDANCE
from studio.l3_interface_adapters.api.discovery_schemas import discovery_schemas
from studio.l3_interface_adapters.api.openapi_examples import (
    image_examples,
    operation_examples,
    rewrite_examples,
    video_examples,
    voice_examples,
)
from studio.l3_interface_adapters.api.visual_prompt_guides import IMAGE_PROMPT_REFERENCES, VIDEO_PROMPT_REFERENCES
from studio.l3_interface_adapters.api.voice_prompt_guides import (
    VOICE_API_CONTRACT,
    VOICE_PROMPT_GUIDES,
    VOICE_PROMPT_REFERENCES,
    VOICE_START_HERE,
)

DESCRIPTION = """Use the same model controls as the Studio page through JSON.

1. Read `GET /api/v1/studio` for available model IDs and `GET /api/v1/state` for active work.
2. Inspect a candidate with `GET /api/v1/{images|videos|voice}/backends/{id}`. This does not load or select it.
   Read its modes, parameters, templates, and adapters before constructing a request. Do not guess IDs or ranges.
3. Choose a named request example below. Replace every angle-bracket media placeholder with actual file bytes encoded as base64.
4. Prefer `POST /api/v1/operations` for work that takes time. Save its `status_url` and poll it.
5. Wait for a terminal status. Fetch `result_url` before retained results expire. Fetch available partial results after cancellation or failure.

A sampler reaching its last step does not mean the output is ready. Decode and save can continue afterward.
Only one operation owns model memory. A conflicting request returns `409`; there is no queue.
Missing weights follow the same download policy and errors as the page. Acceptance does not guarantee later model loading succeeds.

Use structured `template` and `template_values` for an offered image or video template.
For example, select `Slow push-in` and fill its named fields instead of copying its text into `prompt`.
Field names preserve capitalization. `looks` maps exact row names to exact option labels.
For a video effect, select its adapter ID and follow its declared prompt, strength, dimensions, and frame count.
Effects use different recipes. The named effect examples show measured settings.

Voice templates use `{field}` placeholders, unlike image and video templates.
Send the offered name as `template` and its field values as `template_values`.
Check `target`: Design templates fill `voice` and preserve spoken `text`; Edit and Drama delivery templates fill `text`.
AuK/AuK Flash offer Design, Clone, and Edit. Drama-3 offers Generate and Clone, with automatic duration.
Use AuK Design for a described speaker and Drama Generate for inline delivery cues.
Clone copies a WAV reference's voice. Drama Clone also needs `ref_text` matching that recording's exact words;
AuK does not need a transcript. Drama references are at most 15 seconds: trim with `/api/v1/audio/trim` first.
Drama `max_tokens` limits audio tokens per internal chunk, not words or final duration. A cap hit fails the job;
another seed or a clean reference can help a model that does not finish. Increasing the cap can prolong looping.

Images return JSON with base64 PNG. Videos return MP4. Voice returns WAV.
The retained result route uses the same media type as the synchronous route.
Image references accept bare base64 or data URLs. Video keyframes and other media require bare base64.
The one-pixel PNG examples test transport only. Replace them with useful scene images.
Media placeholders are deliberately invalid and must be replaced. Never send example placeholders to a model.

The page and API share operation status, cancellation, model choices, and retained results.
Keep settings and local gallery deletion remain browser preferences.
Results expire after one hour, 32 operations, or 256 MiB, whichever limit comes first.
A restart clears all retained server results.
"""

# A 1 x 1 PNG, so the reference examples in the schemas are real bytes a reader can send.
TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def openapi_document() -> dict[str, Any]:
    document: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Image Gen Studio",
            "version": "1.0.0",
            "description": DESCRIPTION + "\n" + VOICE_START_HERE,
        },
        "x-voice-prompt-guides": deepcopy(VOICE_PROMPT_GUIDES),
        "servers": [{"url": "/", "description": "This studio"}],
        "tags": [
            {"name": "studio", "description": "What this server can run"},
            {"name": "images", "description": "Stills: generate, edit, rewrite\n\n" + IMAGE_PROMPT_REFERENCES},
            {"name": "videos", "description": "Clips: generate, edit, rewrite\n\n" + VIDEO_PROMPT_REFERENCES},
            {
                "name": "voice",
                "description": VOICE_API_CONTRACT + "\n" + VOICE_PROMPT_REFERENCES,
            },
        ],
        "paths": {
            **operation_paths(),
            **voice_paths(),
            **audio_paths(),
            **batch_paths(),
            **discovery_paths(),
            "/api/v1/openapi.json": {
                "get": {
                    "tags": ["studio"],
                    "operationId": "readOpenApi",
                    "summary": "This document",
                    "responses": {
                        "200": {
                            "description": "The OpenAPI document",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
            "/api/v1/studio": {
                "get": {
                    "tags": ["studio"],
                    "operationId": "readStudio",
                    "summary": "Models, modes, sizes, Looks and templates",
                    "responses": {
                        "200": {
                            "description": "The studio's current models and their capabilities",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Studio"}}},
                        }
                    },
                }
            },
            "/api/v1/progress": {
                "get": {
                    "tags": ["studio"],
                    "operationId": "readProgress",
                    "summary": "Current sampler progress across media modes",
                    "responses": {
                        "200": {
                            "description": "What the run is doing",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Progress"}}},
                        }
                    },
                }
            },
            "/api/v1/images/generate": {"post": _image_run("generateImage", "Draw stills from a prompt")},
            "/api/v1/images/edit": {"post": _image_run("editImage", "Change a still you already have")},
            "/api/v1/images/rewrite": {
                "post": _rewrite("rewriteImagePrompt", "Rewrite an image prompt into a longer one", "image")
            },
            "/api/v1/images/cancel": {
                "post": {
                    "tags": ["images"],
                    "operationId": "cancelImage",
                    "summary": "Stop the image run in flight",
                    "responses": {"204": {"description": "The stop was asked for"}},
                }
            },
            "/api/v1/videos/generate": {
                "post": _video_run(
                    "generateVideo", "Draw a clip from a prompt, an optional image and an optional track"
                )
            },
            "/api/v1/videos/edit": {"post": _video_run("editVideo", "Change a clip with one adapter")},
            "/api/v1/videos/rewrite": {
                "post": _rewrite("rewriteVideoPrompt", "Rewrite a video prompt into a longer one", "video")
            },
            "/api/v1/videos/cancel": {
                "post": {
                    "tags": ["videos"],
                    "operationId": "cancelVideo",
                    "summary": "Stop the video run in flight",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "request_id": {
                                            "type": "string",
                                            "description": "Omit to stop the render in flight",
                                        }
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "204": {"description": "The render stopped"},
                        "400": _error("The request id is missing"),
                        "409": _error("The render is no longer active"),
                    },
                }
            },
            "/api/v1/rewrite/cancel": {
                "post": {
                    "tags": ["studio"],
                    "operationId": "cancelRewrite",
                    "summary": "Stop the rewrite in flight",
                    "responses": {"204": {"description": "The stop was asked for"}},
                }
            },
        },
        "components": {
            "schemas": {
                **operation_schemas(),
                **discovery_schemas(),
                **voice_schemas(),
                **batch_schemas(),
                "Error": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {"error": {"type": "string"}},
                    "examples": [{"error": "size must be one of 1024x1024, 768x768, match"}],
                },
                "ImageRequest": {
                    "type": "object",
                    "anyOf": [{"required": ["prompt"]}, {"required": ["template"]}],
                    "properties": {
                        **prompt_aid_properties(),
                        "prompt": {"type": "string", "minLength": 1},
                        "backend": {"type": "string", "description": "A still model id from /api/v1/studio"},
                        "size": {
                            "type": "string",
                            "examples": ["1024x1024"],
                            "description": "One of the mode's size choices, from /api/v1/studio",
                        },
                        "seed": {"type": "integer", "description": "Omit to draw one; the answer names it"},
                        "steps": {"type": "integer"},
                        "guidance": {"type": "number"},
                        "cfg": {"type": "number"},
                        "negative": {"type": "string"},
                        "count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 16,
                            "description": "Up to the model's own batch limit, which is never more than 16",
                        },
                        "references": {
                            "type": "array",
                            "description": "Images as base64, with or without a data URL prefix",
                            "items": {"$ref": "#/components/schemas/ImageReference"},
                        },
                        "each_reference": {
                            "type": "boolean",
                            "description": "One image per reference instead of one image from all of them",
                        },
                        "mask": {"type": "boolean", "description": "The last reference is the region mask"},
                    },
                    "additionalProperties": True,
                    "examples": [
                        {"prompt": "a red pear on a table", "size": "1024x1024", "seed": 7},
                        {"prompt": "a cat asleep in a sunbeam", "size": "768x768", "count": 2},
                        {
                            "prompt": "a red pear on the same table, at dusk",
                            "references": [TINY_PNG],
                            "size": "1024x1024",
                            "seed": 7,
                        },
                    ],
                },
                "ImageEditRequest": {
                    "type": "object",
                    "required": ["references"],
                    "anyOf": [{"required": ["prompt"]}, {"required": ["template"]}],
                    "properties": {
                        **prompt_aid_properties(),
                        "prompt": {"type": "string", "minLength": 1},
                        "backend": {"type": "string"},
                        "size": {"type": "string"},
                        "seed": {"type": "integer"},
                        "steps": {"type": "integer"},
                        "guidance": {"type": "number"},
                        "cfg": {"type": "number"},
                        "negative": {"type": "string"},
                        "strength": {"type": "number", "minimum": 0.05, "maximum": 1},
                        "count": {"type": "integer", "minimum": 1, "maximum": 16},
                        "references": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"$ref": "#/components/schemas/ImageReference"},
                        },
                        "each_reference": {"type": "boolean"},
                        "mask": {"type": "boolean"},
                    },
                    "additionalProperties": True,
                    "examples": [
                        {
                            "prompt": "Turn the sky to dusk and keep the house as it is",
                            "references": [TINY_PNG],
                            "size": "match",
                        }
                    ],
                },
                "Image": {
                    "type": "object",
                    "required": [
                        "png_base64",
                        "width",
                        "height",
                        "seed",
                        "steps",
                        "elapsed",
                        "position",
                        "mode",
                        "prompt",
                    ],
                    "properties": {
                        "completed_at": {"type": "number", "description": "Unix time when this image completed"},
                        "png_base64": {"type": "string", "contentEncoding": "base64"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                        "seed": {"type": "integer"},
                        "steps": {"type": "integer"},
                        "elapsed": {"type": "number", "description": "Seconds, model load included"},
                        "position": {"type": "string", "examples": ["2 of 4"]},
                        "mode": {"type": "string"},
                        "prompt": {"type": "string"},
                        "reference": {"type": "integer", "description": "Which reference this edited, or -1"},
                    },
                },
                "ImageRun": {
                    "type": "object",
                    "required": ["images"],
                    "properties": {"images": {"type": "array", "items": {"$ref": "#/components/schemas/Image"}}},
                },
                "RewriteRequest": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {
                        "prompt": {"type": "string"},
                        "mode": {"type": "string", "default": "generate"},
                        "references": {
                            "type": "array",
                            "description": "The pictures the words are about, as base64",
                            "items": {"$ref": "#/components/schemas/ImageReference"},
                        },
                    },
                    "additionalProperties": False,
                },
                "Rewrite": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "size": {"type": ["string", "null"], "description": "A size the rewriter suggests, or null"},
                        "elapsed": {"type": "number"},
                        "cancelled": {"type": "boolean"},
                    },
                },
                "VideoRequest": {
                    "type": "object",
                    "anyOf": [{"required": ["prompt"]}, {"required": ["template"]}],
                    "properties": {
                        **prompt_aid_properties(),
                        "prompt": {"type": "string", "minLength": 1},
                        "backend": {"type": "string"},
                        "width": {"type": "integer", "description": "One of the model's shapes, from /api/v1/studio"},
                        "height": {"type": "integer"},
                        "num_frames": {"type": "integer", "description": "On the model's frame grid"},
                        "frame_rate": {"type": "integer"},
                        "seed": {"type": "integer"},
                        "references": {
                            "type": "array",
                            "description": "Stills placed at a frame of the clip",
                            "items": {
                                "type": "object",
                                "required": ["name", "image", "frame_index", "strength"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "image": {"type": "string", "contentEncoding": "base64"},
                                    "frame_index": {"type": "integer"},
                                    "strength": {"type": "number"},
                                },
                            },
                        },
                        "audio": {
                            "type": "object",
                            "description": "A track the clip follows. Studio pads a shorter track with silence and limits it to the output duration.",
                            "required": ["name", "data"],
                            "properties": {
                                "name": {"type": "string"},
                                "data": {"type": "string", "contentEncoding": "base64"},
                            },
                        },
                        "fast_mode": {
                            "type": "boolean",
                            "default": False,
                            "description": "Fast mode: optional LTX-2.5 rendering with float16 transformer computation and unchanged q8 weights. May change generated details and motion even with the same seed; speed varies by geometry and conditioning. Off preserves default computation. Check the backend capability fast_mode before enabling. Applies to Generate, image/audio-conditioned Generate, and Edit; use one value for the whole batch. Set on each request; no server restart is needed. Not the Rewrite or prompt-enhancement switch.",
                        },
                        "enhance": {
                            "type": "boolean",
                            "default": True,
                            "description": "Compatibility field: LTX Generate always runs the pipeline's Gemma-3 prompt enhancer, even if false is supplied. This is separate from the Rewrite API; LTX-2.5 still encodes the enhanced text with its Gemma-4 tower. Edit adapter prompts are not enhanced. Eligible Generate batches enhance their prompts in one model load, release that process, then render. Auto keeps the per-item path for measured regressions. Eligible LTX-2.5 text batches reuse the video pipeline within the measured geometry/memory limits; other Generate batches render clips sequentially. A batch remains one operation and samples one clip at a time.",
                        },
                        "request_id": {"type": "string", "description": "Name this render, so it can be stopped"},
                    },
                    "additionalProperties": True,
                    "examples": [
                        {
                            "prompt": "A slow push-in on a woman speaking to camera, soft window light, one continuous shot.",
                            "width": 768,
                            "height": 448,
                            "num_frames": 121,
                            "seed": 7,
                        },
                        {
                            "prompt": "The empty room, then the chandeliers come up and the dancers arrive.",
                            "width": 384,
                            "height": 384,
                            "num_frames": 121,
                            "seed": 7,
                            "references": [
                                {
                                    "name": "start.png",
                                    "image": TINY_PNG.split("base64,", 1)[1],
                                    "frame_index": 0,
                                    "strength": 1.0,
                                },
                                {
                                    "name": "end.png",
                                    "image": TINY_PNG.split("base64,", 1)[1],
                                    "frame_index": 120,
                                    "strength": 1.0,
                                },
                            ],
                        },
                        {
                            "prompt": "The same woman speaks the line on camera, one continuous shot.",
                            "width": 384,
                            "height": 384,
                            "num_frames": 121,
                            "seed": 7,
                            "references": [
                                {
                                    "name": "face.png",
                                    "image": TINY_PNG.split("base64,", 1)[1],
                                    "frame_index": 0,
                                    "strength": 1.0,
                                }
                            ],
                            "audio": {"name": "line.wav", "data": "<base64 of a stereo WAV file>"},
                        },
                    ],
                },
                "VideoEditRequest": {
                    "type": "object",
                    "required": ["prompt", "adapter", "clip"],
                    "properties": {
                        "prompt": {"type": "string", "minLength": 1},
                        "backend": {"type": "string"},
                        "adapter": {
                            "type": "string",
                            "description": "An adapter id from discovery. Choose custom for experimental clip conditioning without loading or downloading any task LoRA, and write your own change in prompt. Source fidelity and edit adherence are not yet validated. Other ids select specialized LoRA effects.",
                        },
                        "adapter_strength": {"type": "number"},
                        "width": {"type": "integer", "description": "Read the adapter's measured width"},
                        "height": {"type": "integer", "description": "Read the adapter's measured height"},
                        "num_frames": {"type": "integer", "description": "Read the adapter's frame count"},
                        "frame_rate": {"type": "integer"},
                        "seed": {"type": "integer"},
                        "clip": {
                            "type": "object",
                            "required": ["name", "data"],
                            "properties": {
                                "name": {"type": "string"},
                                "data": {"type": "string", "contentEncoding": "base64"},
                            },
                        },
                        "request_id": {"type": "string"},
                    },
                    "additionalProperties": True,
                    "examples": [
                        {
                            "prompt": "The same shot at night: deep blue moonlight and warm street lamps. One continuous shot.",
                            "adapter": "day-to-night",
                            "clip": {"name": "street.mp4", "data": "<base64 mp4>"},
                        }
                    ],
                },
                "VideoStub": {
                    "type": "object",
                    "description": "A stub server answers with this instead of an MP4",
                    "properties": {
                        "stub": {"type": "boolean"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                        "num_frames": {"type": "integer"},
                        "frame_rate": {"type": "integer"},
                        "seed": {"type": "integer"},
                    },
                },
                "Progress": {
                    "type": "object",
                    "properties": {
                        "running": {"type": "boolean"},
                        "stage": {"type": "string", "examples": ["preparing", "running"]},
                        "step": {"type": "integer"},
                        "total": {"type": "integer"},
                        "phase": {"type": "integer"},
                        "label": {"type": "string"},
                        "kind": {"type": "string"},
                        "stopping": {"type": "boolean"},
                        "request_id": {"type": ["string", "null"]},
                    },
                },
                "Studio": {
                    "type": "object",
                    "properties": {
                        "image": {
                            "type": "object",
                            "properties": {
                                "active": {"type": "string"},
                                "backends": {"type": "array", "items": {"$ref": "#/components/schemas/Backend"}},
                                "capabilities": {"$ref": "#/components/schemas/ImageCapabilities"},
                            },
                        },
                        "video": {
                            "type": ["object", "null"],
                            "properties": {
                                "active": {"type": "string"},
                                "backends": {"type": "array", "items": {"$ref": "#/components/schemas/Backend"}},
                                "capabilities": {"$ref": "#/components/schemas/VideoCapabilities"},
                                "rewrite_modes": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Video-specific rewrite modes, independent of the Image model.",
                                },
                            },
                        },
                        "voice": {
                            "type": ["object", "null"],
                            "properties": {
                                "active": {"type": "string"},
                                "backends": {"type": "array", "items": {"$ref": "#/components/schemas/Backend"}},
                                "capabilities": {"$ref": "#/components/schemas/VoiceCapabilities"},
                            },
                        },
                        "rewrite_modes": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "Backend": {
                    "type": "object",
                    "required": ["id", "name", "description"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            }
        },
    }
    paths = cast(dict[str, dict[str, dict[str, Any]]], document["paths"])
    for methods in paths.values():
        for operation in methods.values():
            operation["description"] = GUIDANCE[operation["operationId"]]
    return document


def _image_run(operation_id: str, summary: str) -> dict[str, Any]:
    edit = operation_id == "editImage"
    schema = "#/components/schemas/ImageEditRequest" if edit else "#/components/schemas/ImageRequest"
    return {
        "tags": ["images"],
        "operationId": operation_id,
        "summary": summary,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": schema}, "examples": image_examples(edit)}},
        },
        "responses": {
            "200": {
                "description": "Every image of the batch",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ImageRun"}}},
            },
            "400": _error("A value the model refuses"),
            "409": _error("Another run holds the GPU, or this run was stopped"),
            "503": _error("The model or the pipeline is not available"),
        },
    }


def _video_run(operation_id: str, summary: str) -> dict[str, Any]:
    edit = operation_id == "editVideo"
    schema = "#/components/schemas/VideoEditRequest" if edit else "#/components/schemas/VideoRequest"
    return {
        "tags": ["videos"],
        "operationId": operation_id,
        "summary": summary,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": schema}, "examples": video_examples(edit)}},
        },
        "responses": {
            "200": {
                "description": "The clip, as the MP4 itself. The seed is in X-Studio-Seed. A stub server answers JSON.",
                "content": {
                    "video/mp4": {"schema": {"type": "string", "contentMediaType": "video/mp4"}},
                    "application/json": {"schema": {"$ref": "#/components/schemas/VideoStub"}},
                },
            },
            "400": _error("A value the model refuses"),
            "409": _error("Another run holds the GPU, or this run was stopped"),
            "503": _error("The model or the pipeline is not available"),
        },
    }


def _rewrite(operation_id: str, summary: str, workspace: str) -> dict[str, Any]:
    description = (
        "Use LTX's native Gemma 3 prompt enhancer, independently of the Image model. "
        "The first attached reference is read by Gemma vision tower with native LTX image-to-video instructions. "
        "Later keyframes remain generator inputs; the enhancer does not read audio. "
        "Use the returned prompt unchanged in Generate to avoid a second enhancement in this server session. "
        "Changing the prompt or the first reference image, or adding/removing that reference, runs enhancement again. "
        "Automatic generation enhancement remains enabled. Rewrite shares the GPU lock and supports cancellation."
        if workspace == "video"
        else "Rewrite using the selected Image model's prompt rewriter."
    )
    return {
        "tags": ["images" if workspace == "image" else "videos"],
        "operationId": operation_id,
        "summary": summary,
        "description": description,
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/RewriteRequest"},
                    "examples": rewrite_examples(workspace),
                }
            },
        },
        "responses": {
            "200": {
                "description": "The longer prompt, and the size it suggests when it read a picture",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Rewrite"}}},
            },
            "400": _error("A value the model refuses"),
            "503": _error("The rewriter or the model is not available"),
        },
    }


def _error(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
    }


def operation_paths() -> dict[str, Any]:
    reads = {
        "/api/v1/state": ("readState", "Active work, recent results, and selected models", "State"),
        "/api/v1/rewrite/state": ("readRewriteState", "The current rewrite phase", "RewriteState"),
        "/api/v1/operations/{id}": ("readOperation", "Read one operation", "Operation"),
        "/api/v1/operations/{id}/result": ("readOperationResult", "Read a retained result", "ImageRun"),
    }
    paths: dict[str, Any] = {}
    identifier = [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}]
    for path, (name, summary, schema) in reads.items():
        content: dict[str, Any] = {"application/json": {"schema": {"$ref": "#/components/schemas/" + schema}}}
        if path.endswith("/result"):
            content["application/json"] = {
                "schema": {
                    "oneOf": [
                        {"$ref": "#/components/schemas/" + name}
                        for name in ("ImageRun", "VideoStub", "Rewrite", "BatchResult")
                    ]
                }
            }
            content["video/mp4"] = {"schema": {"type": "string", "format": "binary"}}
            content["audio/wav"] = {"schema": {"type": "string", "format": "binary"}}
        response = {"description": summary, "content": content}
        paths[path] = {
            "get": {
                "operationId": name,
                "summary": summary,
                "tags": ["studio"],
                "responses": {
                    "200": response,
                    "404": _error("The operation expired or does not exist"),
                    "409": _error(
                        "A single operation has not finished; batch manifests remain readable while items run"
                    ),
                },
            }
        }
        if "{id}" in path:
            paths[path]["get"]["parameters"] = identifier
    paths["/api/v1/operations"] = {
        "post": {
            "operationId": "startOperation",
            "tags": ["studio"],
            "summary": "Start work and return immediately",
            "description": "One operation runs at a time. There is no queue. Poll its URL or /api/v1/state. Results remain in memory for at most one hour, 32 operations, or 256 MiB, whichever limit comes first. The server retains no results after a restart. A legacy page batch keeps its reservation for 30 seconds between image requests. Closing that tab cancels the unfinished batch after this interval. API batches run entirely on the server and use no continuation timeout. A missing result returns 404. Model loading and downloads use the same policy as the page. A worker failure appears in status and error.",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/OperationRequest"},
                        "examples": operation_examples(),
                    }
                },
            },
            "responses": {
                "202": {
                    "description": "Operation accepted",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Operation"}}},
                },
                "400": _error("Invalid operation"),
                "409": _error("The studio is busy"),
            },
        }
    }
    paths["/api/v1/operations/{id}/cancel"] = {
        "post": {
            "operationId": "cancelOperation",
            "tags": ["studio"],
            "parameters": identifier,
            "summary": "Stop this active operation",
            "responses": {
                "204": {"description": "The stop was requested"},
                "404": _error("Unknown operation"),
                "409": _error("The operation already finished"),
            },
        }
    }
    for workspace in ("images", "videos", "voice"):
        paths[f"/api/v1/{workspace}/backend"] = {
            "post": {
                "operationId": "select" + workspace.title() + "Backend",
                "tags": ["studio"],
                "summary": "Select a model without loading its weights",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["backend"],
                                "properties": {"backend": {"type": "string"}},
                            },
                            **(
                                {
                                    "examples": {
                                        "auk_flash": {
                                            "summary": "Select AuK Flash without loading it",
                                            "value": {"backend": "auk"},
                                        },
                                        "auk": {
                                            "summary": "Select AuK without loading it",
                                            "value": {"backend": "auk_base"},
                                        },
                                    }
                                }
                                if workspace == "voice"
                                else {}
                            ),
                        }
                    },
                },
                "responses": {
                    "204": {"description": "Model selected"},
                    "409": _error("The studio is busy"),
                    "503": _error("The model is not available"),
                },
            }
        }
    paths["/api/v1/memory/release"] = {
        "post": {
            "operationId": "releaseModelMemory",
            "tags": ["studio"],
            "summary": "Release the current model from memory",
            "responses": {"204": {"description": "Model released"}, "409": _error("The studio is busy")},
        }
    }
    return paths


def operation_schemas() -> dict[str, Any]:
    operation = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "status_url": {"type": "string"},
            "source": {"enum": ["ui", "api"]},
            "client_id": {"type": "string"},
            "library_id": {
                "type": "string",
                "description": "Browser library identity from X-Studio-Library when present",
            },
            "kind": {"enum": ["image", "video", "voice", "rewrite"]},
            "workspace": {"enum": ["image", "video", "voice"]},
            "mode": {"enum": ["generate", "edit", "clone", "design"]},
            "status": {"enum": ["running", "stopping", "succeeded", "failed", "cancelled"]},
            "started_at": {"type": "number", "description": "Unix seconds"},
            "finished_at": {"type": ["number", "null"]},
            "backend": {"type": "string"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "width": {"type": ["integer", "null"]},
            "height": {"type": ["integer", "null"]},
            "num_frames": {"type": ["integer", "null"]},
            "frame_rate": {"type": ["integer", "null"]},
            "settings": {"type": "object", "description": "Request settings without image, clip, or audio bytes"},
            "progress": {
                "allOf": [{"$ref": "#/components/schemas/Progress"}],
                "description": "Live sampler or rewrite progress. total=0 means indeterminate, so show elapsed time instead of a percentage. Sampler completion does not mean the result is ready; wait for a terminal operation status.",
            },
            "error": {"type": ["string", "null"]},
            "result_url": {"type": ["string", "null"]},
            "batch_index": {"type": "integer", "minimum": 1},
            "batch_total": {"type": "integer", "minimum": 1, "maximum": 16},
            "batch_completed": {
                "type": "integer",
                "minimum": 0,
                "maximum": 16,
                "description": "Number of retained completed batch items.",
            },
        },
    }
    return {
        "Operation": operation,
        "OperationRequest": {
            "type": "object",
            "required": ["kind"],
            "oneOf": [
                {
                    "properties": {"kind": {"const": kind}},
                    "anyOf": [{"$ref": "#/components/schemas/" + name} for name in names],
                }
                for kind, names in (
                    ("image", ("ImageRequest", "ImageEditRequest", "BatchRequest")),
                    ("video", ("VideoRequest", "VideoEditRequest", "BatchRequest")),
                    ("voice", ("VoiceRequest", "BatchRequest")),
                    ("rewrite", ("OperationRewriteRequest",)),
                )
            ],
            "description": "Use the request schema for the selected kind, or BatchRequest for ordered items. Add kind and optionally workspace, mode, client_id. Each accepted operation owns its whole batch.",
            "properties": {
                "kind": {"enum": ["image", "video", "voice", "rewrite"]},
                "workspace": {"enum": ["image", "video", "voice"]},
                "mode": {"enum": ["generate", "edit", "clone", "design"]},
                "client_id": {"type": "string"},
            },
        },
        "State": {
            "type": "object",
            "properties": {
                "active": {"oneOf": [{"$ref": "#/components/schemas/Operation"}, {"type": "null"}]},
                "operations": {"type": "array", "items": {"$ref": "#/components/schemas/Operation"}},
                "studio": {"$ref": "#/components/schemas/Studio"},
            },
        },
        "RewriteState": {
            "type": "object",
            "properties": {
                "running": {"type": "boolean"},
                "stopping": {"type": "boolean"},
                "stage": {"enum": ["idle", "preparing", "writing"]},
            },
        },
    }


def prompt_aid_properties() -> dict[str, Any]:
    return {
        "looks": {
            "type": "object",
            "description": "Choose rows and option labels from the selected mode capabilities. Each row takes one option.",
            "additionalProperties": {
                "oneOf": [{"type": "string"}, {"type": "array", "maxItems": 1, "items": {"type": "string"}}]
            },
        },
        "template": {"type": "string", "description": "A template name from this model capabilities"},
        "template_values": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "Replace each bracket field by its name without brackets",
        },
        "per_reference_prompts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Image batches only. One instruction per reference. Requires each_reference. The master prompt leads each instruction, with Looks last.",
        },
    }


def voice_paths() -> dict[str, Any]:
    return {
        "/api/v1/voice/capabilities": {
            "get": {
                "tags": ["voice"],
                "operationId": "readVoiceCapabilities",
                "summary": "Voice modes, settings, and templates",
                "responses": {
                    "200": {
                        "description": "Active Voice model capabilities",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/VoiceCapabilities"}}},
                    }
                },
            }
        },
        "/api/v1/voice/generate": {
            "post": {
                "tags": ["voice"],
                "operationId": "generateVoice",
                "summary": "Generate, design, clone, or edit speech with the selected model",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/VoiceRequest"},
                            "examples": voice_examples(),
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "WAV audio. Headers identify the operation, seed, and completion time.",
                        "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
                    },
                    "400": _error("The request is invalid"),
                    "409": _error("The studio is busy or the operation stopped"),
                },
            }
        },
    }


def voice_schemas() -> dict[str, Any]:
    return {
        "VoiceRequest": {
            "type": "object",
            "description": VOICE_API_CONTRACT + "\n" + VOICE_START_HERE,
            "additionalProperties": True,
            "anyOf": [{"required": ["text"]}, {"required": ["template"]}],
            "properties": {
                "backend": {
                    "enum": ["auk", "auk_base", "drama3"],
                    "description": "Drama-3 (drama3, default), AuK (auk_base), or AuK Flash (auk). Omitted backend uses the server's current Voice selection; send an explicit ID for reproducible behavior. Read that model's capabilities before choosing a mode or parameters.",
                },
                "template": {
                    "type": "string",
                    "description": "Exact template name from the selected Voice mode. Template.target declares the destination. AuK Design fills voice; Edit and Drama delivery templates fill text. Unknown names reject the request.",
                },
                "template_values": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "number"]},
                    "description": "Named field values from the template. Fields use their declared defaults when omitted. Blank text defaults must be filled. Unknown fields and invalid values reject the request.",
                },
                "mode": {
                    "enum": ["generate", "clone", "design", "edit"],
                    "description": "AuK/AuK Flash allow design, clone and edit; Drama-3 allows generate and clone. Omitted mode uses the model default: design for AuK, generate for Drama-3. Unsupported modes reject the request.",
                },
                "text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 20000,
                    "description": "Words to speak for generate/clone/design; an edit instruction for edit. Drama accepts inline [delivery cues] and paired delivery tags.",
                },
                "voice": {
                    "description": "AuK Design only; ignored in other modes. Required for custom design without a template. Describe speaker attributes here and keep spoken words in text. A Design template supplies this description.",
                },
                "seconds": {
                    "default": 0,
                    "description": "AuK only; ignored by Drama-3, whose duration follows its script. Zero chooses duration from text for clone/design, or from the reference for edit. Templates with length_by divide reference duration by that field. Positive seconds overrides this rule.",
                },
                "convert": {
                    "default": "tw2s",
                    "description": "AuK only; ignored by Drama-3. tw2s converts Traditional Chinese characters before synthesis. Vocabulary stays unchanged. Drama preserves the script as written.",
                },
                "ref_text": {
                    "description": "Required for Drama-3 Clone: exact words spoken in the supplied WAV excerpt, not the new script. Transcribe only the retained audio after trimming to 15 seconds. The API does not run speech recognition. AuK Clone does not need this field.",
                },
                "temperature": {
                    "default": 0.7,
                    "description": "Drama-3 sampling temperature; ignored by AuK/AuK Flash.",
                },
                "top_p": {
                    "default": 0.7,
                    "description": "Drama-3 nucleus sampling; ignored by AuK/AuK Flash.",
                },
                "top_k": {
                    "default": 30,
                    "description": "Drama-3 candidate count; ignored by AuK/AuK Flash.",
                },
                "max_tokens": {
                    "default": 2048,
                    "description": "Drama-3 only; ignored by AuK/AuK Flash. Audio-token safety limit per internal text chunk, not words, duration, or percent complete. A cap hit fails instead of publishing partial audio. Try another seed, simpler cues, or Clone with a clean reference if the model does not finish; a higher cap can prolong looping.",
                },
                "seed": {"type": "integer", "minimum": 0, "maximum": 4294967295},
                "reference": {
                    "type": "object",
                    "required": ["wav_base64"],
                    "properties": {
                        "name": {"type": "string"},
                        "wav_base64": {"type": "string", "contentEncoding": "base64"},
                    },
                    "description": "Required for clone/edit. WAV bytes only, at most 32 MiB. AuK allows 120 seconds; Drama-3 allows 15 seconds. Read max_reference_seconds from model discovery. Use raw base64 without a data URL.",
                },
            },
            "allOf": [
                {
                    "if": {
                        "anyOf": [
                            {"required": ["mode"], "properties": {"mode": {"const": "design"}}},
                            {
                                "not": {"required": ["mode"]},
                                "required": ["backend"],
                                "properties": {"backend": {"enum": ["auk", "auk_base"]}},
                            },
                        ]
                    },
                    "then": {
                        "required": ["text"],
                        "anyOf": [{"required": ["voice"]}, {"required": ["template"]}],
                        "properties": {"voice": {"type": "string"}},
                    },
                },
                {
                    "if": {"required": ["mode"], "properties": {"mode": {"enum": ["clone", "edit"]}}},
                    "then": {"required": ["reference"]},
                },
                {
                    "if": {"required": ["backend"], "properties": {"backend": {"const": "drama3"}}},
                    "then": {
                        "properties": {
                            "mode": {"enum": ["generate", "clone"]},
                            "temperature": {"type": "number", "minimum": 0.1, "maximum": 1.5},
                            "top_p": {"type": "number", "minimum": 0.1, "maximum": 1},
                            "top_k": {"type": "integer", "minimum": 1, "maximum": 100},
                            "max_tokens": {"type": "integer", "minimum": 64, "maximum": 2048},
                        }
                    },
                },
                {
                    "if": {
                        "required": ["backend", "mode"],
                        "properties": {"backend": {"const": "drama3"}, "mode": {"const": "clone"}},
                    },
                    "then": {"required": ["ref_text"], "properties": {"ref_text": {"type": "string", "minLength": 1}}},
                },
                {
                    "if": {"required": ["backend"], "properties": {"backend": {"enum": ["auk", "auk_base"]}}},
                    "then": {
                        "properties": {
                            "mode": {"enum": ["design", "clone", "edit"]},
                            "seconds": {"type": "number", "minimum": 0, "maximum": 120},
                            "convert": {"enum": ["tw2s", "off"]},
                        }
                    },
                },
                {
                    "if": {
                        "anyOf": [
                            {"required": ["mode"], "properties": {"mode": {"enum": ["generate", "design"]}}},
                            {
                                "not": {"required": ["mode"]},
                                "required": ["backend"],
                                "properties": {"backend": {"enum": ["auk", "auk_base", "drama3"]}},
                            },
                        ]
                    },
                    "then": {"properties": {"reference": False}},
                },
            ],
        }
    }


def batch_paths() -> dict[str, Any]:
    return {
        "/api/v1/operations/{id}/items/{index}/result": {
            "get": {
                "tags": ["studio"],
                "operationId": "readBatchItemResult",
                "summary": "Read one completed batch item",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {
                        "name": "index",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 16},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "The item's original media response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "oneOf": [
                                        {"$ref": "#/components/schemas/ImageRun"},
                                        {"$ref": "#/components/schemas/VideoStub"},
                                    ]
                                }
                            },
                            "video/mp4": {"schema": {"type": "string", "format": "binary"}},
                            "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                        },
                    },
                    "404": _error("The item has no retained result"),
                },
            }
        }
    }


def batch_schemas() -> dict[str, Any]:
    return {
        "OperationRewriteRequest": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "workspace": {"enum": ["image", "video"]},
                "references": {"type": "array", "items": {"$ref": "#/components/schemas/ImageReference"}},
            },
        },
        "BatchRequest": {
            "type": "object",
            "required": ["kind", "items"],
            "description": "Top-level fields are defaults for every item. Items override defaults. Use one backend and kind for the entire batch. Video items must also share the top-level fast_mode boolean (default false); it cannot change between items. Each item yields one result: count must be one and each_reference must be false. Items run in order; completed outputs survive later failure or cancellation. Indices start at one.",
            "properties": {
                "kind": {"enum": ["image", "video", "voice"]},
                "backend": {"type": "string"},
                "mode": {"type": "string"},
                "seed": {"type": "integer"},
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 16,
                    "items": {
                        "type": "object",
                        "description": "A partial ImageRequest, VideoRequest, or VoiceRequest. Inherits missing fields from the batch. Nested items and backend/kind/workspace changes are forbidden.",
                        "properties": {
                            "prompt": {"type": "string"},
                            "text": {"type": "string"},
                            "seed": {"type": "integer"},
                            "template": {"type": "string"},
                            "template_values": {
                                "type": "object",
                                "additionalProperties": {"type": ["string", "number"]},
                            },
                        },
                    },
                },
            },
        },
        "BatchResult": {
            "type": "object",
            "required": ["items", "completed", "batch_total"],
            "description": "Readable while a batch runs. Items appear after retention; fetch each result_url immediately. Later cancellation or failure preserves completed items.",
            "properties": {
                "completed": {"type": "integer"},
                "batch_total": {"type": "integer"},
                "items": {"type": "array", "items": {"$ref": "#/components/schemas/BatchItemResult"}},
            },
        },
        "BatchItemResult": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "minimum": 1},
                "kind": {"enum": ["image", "video", "voice"]},
                "status": {"const": "succeeded"},
                "result_url": {"type": "string"},
                "prompt": {"type": "string"},
                "settings": {"type": "object"},
                "completed_at": {"type": "number"},
                "seconds": {"type": "number"},
                "sample_rate": {"type": "integer"},
                "seed": {"type": "integer"},
            },
        },
    }


def discovery_paths() -> dict[str, Any]:
    return {
        f"/api/v1/{workspace}/backends/{{id}}": {
            "get": {
                "tags": ["studio"],
                "operationId": operation_id,
                "summary": "Read a model without selecting or loading it",
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {
                    "200": {
                        "description": "The model's complete capabilities",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/" + schema}}},
                    },
                    "404": _error("The backend is unknown"),
                },
            }
        }
        for workspace, schema, operation_id in (
            ("images", "ImageCapabilities", "readImageBackend"),
            ("videos", "VideoCapabilities", "readVideoBackend"),
            ("voice", "VoiceCapabilities", "readVoiceBackend"),
        )
    }


def audio_paths() -> dict[str, Any]:
    return {
        "/api/v1/audio/trim": {
            "post": {
                "tags": ["voice"],
                "operationId": "trimAudio",
                "summary": "Cut a WAV selection without a model",
                "description": "Returns the selected PCM samples with the original sample rate, channels, and sample width. This CPU request runs while a generation operation is active. It reserves no operation and starts no generation. Limits: 32 MiB decoded WAV, 120 seconds, uncompressed PCM with 1 to 4 bytes per sample. Bounds must be finite numbers. Frame cuts use round(seconds * sample_rate); the selection must include at least one frame.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["audio", "start_seconds", "end_seconds"],
                                "properties": {
                                    "audio": {
                                        "type": "object",
                                        "required": ["data"],
                                        "properties": {
                                            "name": {"type": "string"},
                                            "data": {
                                                "type": "string",
                                                "contentEncoding": "base64",
                                                "description": "Bare base64 of a PCM WAV file. Data URLs are rejected.",
                                            },
                                        },
                                    },
                                    "start_seconds": {"type": "number", "minimum": 0, "maximum": 120},
                                    "end_seconds": {
                                        "type": "number",
                                        "exclusiveMinimum": 0,
                                        "maximum": 120,
                                        "description": "After start_seconds and at most the decoded WAV duration.",
                                    },
                                },
                            },
                            "examples": {
                                "middle_second": {
                                    "summary": "Keep 0.25 to 1.25 seconds of a WAV",
                                    "description": "This complete request includes a tiny two-second transport-test WAV at 8 Hz. Replace audio.data with your recording. The selected eight stereo frames preserve their original PCM bytes.",
                                    "value": {
                                        "audio": {
                                            "name": "transport-test.wav",
                                            "data": "UklGRmQAAABXQVZFZm10IBAAAAABAAIACAAAACAAAAAEABAAZGF0YUAAAAAAAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYnKCkqKywtLi8wMTIzNDU2Nzg5Ojs8PT4/",
                                        },
                                        "start_seconds": 0.25,
                                        "end_seconds": 1.25,
                                    },
                                }
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "The selected WAV. X-Studio-Duration reports its exact duration after sample rounding.",
                        "headers": {
                            "X-Studio-Duration": {
                                "schema": {"type": "number"},
                                "description": "Selected frames divided by the original sample rate.",
                            }
                        },
                        "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
                    },
                    "400": _error("Invalid media, range, or request"),
                },
            }
        }
    }
