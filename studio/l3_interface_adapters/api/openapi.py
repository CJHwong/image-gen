"""The OpenAPI document for the studio's JSON API.

Written as data, not generated: the routes are a handful and their shapes are the use
cases' own types, so a generator would add a dependency to describe eight endpoints.
A test walks the routes in http_server and the paths here, and fails when one is
missing from the other, which is the part a generator would otherwise guarantee.
"""

from typing import Any

DESCRIPTION = """Every model this studio runs, over JSON.

The page and this API share one controller and one set of use cases: a body is turned
into the same form the page posts, so a limit or a refusal is the same at both doors.

Start with `GET /api/v1/studio`. It names the models, their modes, and the sizes each
one offers, so a request can name a value the model knows.

```sh
curl -s localhost:8765/api/v1/studio | jq '.image.active'
curl -s localhost:8765/api/v1/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "a red pear on a table", "size": "1024x1024", "seed": 7}' \
  | jq -r '.images[0].png_base64' | base64 -d > pear.png
```

Images come back as base64 PNG. A video comes back as the MP4 itself, with the seed in
`X-Studio-Seed`. A run that is stopped answers `409` and names the stop.

A picture a run starts from and a track it follows travel as base64 inside the JSON body,
not as a file upload. An image reference is a base64 string or an object with
`png_base64`; a browser's `FileReader` result with its `data:...;base64,` prefix is
accepted as it is. A video's keyframes are objects that name the frame and the strength,
and its track is an object with a name and base64 data. The schemas below carry one
example of each.

One model fits in memory at a time. A request while another run holds the GPU answers
`409`, so a client should read `GET /api/v1/progress` rather than retry at once.
"""

# A 1 x 1 PNG, so the reference examples in the schemas are real bytes a reader can send.
TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def openapi_document() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Image Gen Studio",
            "version": "1.0.0",
            "description": DESCRIPTION,
        },
        "servers": [{"url": "/", "description": "This studio"}],
        "tags": [
            {"name": "studio", "description": "What this server can run"},
            {"name": "images", "description": "Stills: generate, edit, rewrite"},
            {"name": "videos", "description": "Clips: generate, edit, rewrite"},
        ],
        "paths": {
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
                    "summary": "The run in flight, image or video",
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
                "Error": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {"error": {"type": "string"}},
                    "examples": [{"error": "size must be one of 1024x1024, 768x768, match"}],
                },
                "ImageRequest": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {
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
                            "items": {"type": "string", "contentEncoding": "base64"},
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
                    "required": ["prompt", "references"],
                    "properties": {
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
                            "items": {"type": "string", "contentEncoding": "base64"},
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
                            "items": {"type": "string", "contentEncoding": "base64"},
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
                    "required": ["prompt"],
                    "properties": {
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
                            "description": "A track the clip follows, trimmed to the clip's length",
                            "required": ["name", "data"],
                            "properties": {
                                "name": {"type": "string"},
                                "data": {"type": "string", "contentEncoding": "base64"},
                            },
                        },
                        "enhance": {
                            "type": "boolean",
                            "description": "Lengthen the prompt with the model's own rewriter",
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
                                {"name": "start.png", "image": TINY_PNG, "frame_index": 0, "strength": 1.0},
                                {"name": "end.png", "image": TINY_PNG, "frame_index": 120, "strength": 1.0},
                            ],
                        },
                        {
                            "prompt": "The same woman speaks the line on camera, one continuous shot.",
                            "width": 384,
                            "height": 384,
                            "num_frames": 121,
                            "seed": 7,
                            "references": [{"name": "face.png", "image": TINY_PNG, "frame_index": 0, "strength": 1.0}],
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
                        "adapter": {"type": "string", "description": "An adapter id from /api/v1/studio"},
                        "adapter_strength": {"type": "number"},
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
                                "capabilities": {"type": "object", "additionalProperties": True},
                            },
                        },
                        "video": {
                            "type": ["object", "null"],
                            "properties": {
                                "active": {"type": "string"},
                                "backends": {"type": "array", "items": {"$ref": "#/components/schemas/Backend"}},
                                "capabilities": {"type": "object", "additionalProperties": True},
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


def _image_run(operation_id: str, summary: str) -> dict[str, Any]:
    edit = operation_id == "editImage"
    schema = "#/components/schemas/ImageEditRequest" if edit else "#/components/schemas/ImageRequest"
    return {
        "tags": ["images"],
        "operationId": operation_id,
        "summary": summary,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": schema}}},
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
            "content": {"application/json": {"schema": {"$ref": schema}}},
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
    return {
        "tags": ["images" if workspace == "image" else "videos"],
        "operationId": operation_id,
        "summary": summary,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RewriteRequest"}}},
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
