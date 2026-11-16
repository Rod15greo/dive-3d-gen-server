# Dive 3D Gen Server

Modal-hosted image/text-to-3D API that returns textured GLB assets. It powers
the official Unity package and Blender add-on, but any HTTP client can use it.

## Complete guide

Download the Portuguese end-to-end guide for installing the plugins, using a
shared server, deploying your own Modal server, and managing API keys:
[Guia_Dive_3D_Gen.pdf](docs/Guia_Dive_3D_Gen.pdf).

The editable source is [GUIA_DE_USO.md](docs/GUIA_DE_USO.md). Regenerate the
PDF after documentation changes with `python docs/generate_user_guide.py`.

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
the end of deployment. The Unity package and Blender add-on ship with an empty
Server URL, so give this endpoint to your users along with their API keys.

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

These names are passed into the containers through `Image.env`, so the web API
and the model functions always use the same Volume and Dict.

## Runtime settings

Also read at `modal deploy` time:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DIVE3D_SCALEDOWN_WINDOW` | `300` | Seconds a TRELLIS/Hunyuan GPU container stays idle before shutting down. |
| `DIVE3D_MAX_IMAGE_MB` | `20` | Maximum uploaded image size. |
| `DIVE3D_HUNYUAN_TRACE` | `0` | `1` stores the user's input image and intermediate Hunyuan outputs under `/models/diagnostics` in the Volume. Debug only. |

**Why 300 s idle window:** loading TRELLIS or Hunyuan weights into a fresh
container takes long, so keeping the container warm lets a user iterate on
several generations without paying a cold start each time. Every idle second is
billed A10G time, though. The previous value (600 s) charged up to 10 minutes of
idle GPU after each burst of work; 300 s keeps a typical editing session warm
while halving the worst-case idle cost. Use `0`-`60` for occasional use and
lower cost, or raise it for heavy interactive sessions.

## API

`POST /generate` accepts `multipart/form-data` with an `X-API-Key` header.

| Field | Values |
| --- | --- |
| `model` | `sf3d`, `trellis`, or `hunyuan` |
| `quality` | `fast`, `balanced`, or `high` |
| `prompt` | Optional text (up to 1000 characters); supported by TRELLIS |
| `image` | Optional image; required by SF3D and Hunyuan. PNG, JPEG or WEBP (BMP, TGA, TIFF, PSD and GIF also accepted), up to `DIVE3D_MAX_IMAGE_MB` |

Errors: `403` invalid/revoked key, `400` invalid fields, `413` image too
large, `415` file is not a supported image.

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
