# Dive 3D Gen Server

Modal-hosted image/text-to-3D API that returns textured GLB assets. It powers
the official Unity package and Blender add-on, but any HTTP client can use it.

## Models

| Model | Input | Output |
| --- | --- | --- |
| SF3D | Image | Textured GLB |
| TRELLIS | Image or text | Textured PBR GLB |
| Hunyuan3D-2 | Image | Textured PBR GLB |

## Prerequisites

- Python 3.10 or newer.
- A [Modal](https://modal.com) account and CLI authentication.
- A Hugging Face access token. Accept the upstream model terms before using it.
- An NVIDIA A10G-capable Modal account. Model execution incurs Modal GPU costs.

## Deploy your own server

```powershell
git clone https://github.com/Rod15greo/dive-3d-gen-server.git
cd dive-3d-gen-server
python -m pip install -r requirements.txt
python -m modal setup
python -m modal secret create dive-3d-gen-huggingface HF_TOKEN=YOUR_HF_TOKEN
python -m modal deploy main.py
```

The first call for each model downloads its weights to the Modal Volume and can
take substantially longer than later calls. Modal prints the public endpoint at
the end of deployment.

Create a client API key after deploying:

```powershell
python -m modal run scripts/manage_keys.py::create_key --name "my-client"
```

Give the generated key and your Modal endpoint only to users who may consume
your GPU budget. Revoke a key when needed:

```powershell
python -m modal run scripts/manage_keys.py::revoke_key --key "KEY_TO_REVOKE"
```

## Resource names

By default the app uses `dive-3d-gen`, `dive-3d-gen-models`,
`dive-3d-gen-api-keys`, and `dive-3d-gen-huggingface`. These resources are
scoped to each Modal account, so the defaults work for independent deployments.
Override them before `modal deploy` when needed:

```powershell
$env:DIVE3D_APP_NAME = "my-dive-3d"
$env:DIVE3D_MODEL_VOLUME = "my-dive-3d-models"
$env:DIVE3D_API_KEYS_DICT = "my-dive-3d-api-keys"
$env:DIVE3D_HF_SECRET = "my-huggingface-secret"
python -m modal deploy main.py
```

## API

`POST /generate` accepts `multipart/form-data` with an `X-API-Key` header.

| Field | Values |
| --- | --- |
| `model` | `sf3d`, `trellis`, or `hunyuan` |
| `quality` | `fast`, `balanced`, or `high` |
| `prompt` | Optional text; supported by TRELLIS |
| `image` | Optional image; required by SF3D and Hunyuan |

```bash
curl -X POST "https://YOUR-ENDPOINT/generate" \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "model=trellis" \
  -F "quality=balanced" \
  -F "image=@reference.png"
```

The response contains a `job_id`. Poll `GET /status/{job_id}` with the same
header until `status` is `done`, then decode `glb_base64` into a `.glb` file.

`GET /health` is public and returns the available model names.

## Security and licenses

No API key, Hugging Face token, model weights, or generated assets are stored
in this repository. Keep secrets in Modal and avoid publishing client keys.

This repository is MIT-licensed. The bundled code downloads upstream models at
runtime; their licenses and usage terms remain those of Stability AI, Microsoft
TRELLIS, and Tencent Hunyuan3D-2.
