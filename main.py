"""
Dive 3D Gen — Modal server
Expõe uma API FastAPI serverless com GPU A10G (24 GB VRAM).
Suporta 3 modelos: sf3d | trellis | hunyuan
"""

import base64
import io
import os
from pathlib import Path
from typing import Optional

import modal

# ---------------------------------------------------------------------------
# Modal app
# ---------------------------------------------------------------------------

APP_NAME = os.getenv("DIVE3D_APP_NAME", "dive-3d-gen")
MODEL_VOLUME_NAME = os.getenv("DIVE3D_MODEL_VOLUME", "dive-3d-gen-models")
API_KEYS_DICT_NAME = os.getenv("DIVE3D_API_KEYS_DICT", "dive-3d-gen-api-keys")
HUGGINGFACE_SECRET_NAME = os.getenv("DIVE3D_HF_SECRET", "dive-3d-gen-huggingface")

app = modal.App(APP_NAME)

model_volume = modal.Volume.from_name(MODEL_VOLUME_NAME, create_if_missing=True)
api_keys_store = modal.Dict.from_name(API_KEYS_DICT_NAME, create_if_missing=True)

# ---------------------------------------------------------------------------
# Container images
# ---------------------------------------------------------------------------

_cuda_base = "nvidia/cuda:12.1.0-devel-ubuntu22.04"

sf3d_image = (
    modal.Image.from_registry(_cuda_base, add_python="3.10")
    .apt_install("git", "libgl1", "libglib2.0-0", "clang")  # clang necessário para compilar extensões CUDA (texture_baker/uv_unwrapper)
    .pip_install(
        "torch==2.5.1", "torchvision==0.20.1",
        "numpy==1.26.4",  # pinar antes do build — extensões C++ precisam de numpy 1.x
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .run_commands(
        "pip install -U setuptools==69.5.1 wheel ninja",
        "git clone --depth=1 https://github.com/Stability-AI/stable-fast-3d.git /sf3d",
        # --no-build-isolation: usa torch/numpy já instalados durante o build das extensões C++
        "cd /sf3d && USE_CUDA=1 TORCH_CUDA_ARCH_LIST=8.6 CPATH=/usr/local/cuda/include:${CPATH:-} pip install -r requirements.txt --no-build-isolation --extra-index-url https://download.pytorch.org/whl/cu121",
    )
    .add_local_dir("models", remote_path="/root/models")
)

trellis_image = (
    modal.Image.from_registry(_cuda_base, add_python="3.10")
    .apt_install("git", "build-essential", "clang", "libgl1", "libglib2.0-0", "libegl1", "ninja-build")
    .pip_install(
        "torch==2.4.0", "torchvision==0.19.0", "numpy==1.26.4",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .run_commands(
        "pip install -U setuptools==69.5.1 wheel ninja",
        "git clone --depth=1 --recurse-submodules https://github.com/microsoft/TRELLIS.git /trellis",
        "pip install pillow imageio imageio-ffmpeg tqdm easydict opencv-python-headless scipy rembg onnxruntime trimesh open3d xatlas pyvista pymeshfix igraph transformers==4.46.3 huggingface_hub",
        "pip install numpy==1.26.4 --force-reinstall --no-deps",
        "pip install git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8",
        "pip install xformers==0.0.27.post2 --index-url https://download.pytorch.org/whl/cu121",
        "pip install spconv-cu120",
        "pip install kaolin -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.4.0_cu121.html",
        "git clone --depth=1 https://github.com/NVlabs/nvdiffrast.git /tmp/nvdiffrast",
        "cd /tmp/nvdiffrast && TORCH_CUDA_ARCH_LIST=8.6 CPATH=/usr/local/cuda/include:${CPATH:-} pip install . --no-build-isolation",
        "git clone --depth=1 --recurse-submodules https://github.com/autonomousvision/mip-splatting.git /tmp/mip-splatting",
        "cd /tmp/mip-splatting && TORCH_CUDA_ARCH_LIST=8.6 CPATH=/usr/local/cuda/include:${CPATH:-} pip install submodules/diff-gaussian-rasterization --no-build-isolation",
    )
    .add_local_dir("models", remote_path="/root/models")
)

hunyuan_image = (
    modal.Image.from_registry(_cuda_base, add_python="3.10")
    # PyMeshLab's PLY I/O plugin (used by Tencent's FaceReducer) requires
    # libOpenGL.so.0, provided by libopengl0 on Ubuntu 22.04.
    .apt_install("git", "libgl1", "libopengl0", "libglib2.0-0", "ninja-build", "clang")
    # torch first — diso and CUDA extensions need torch in the build env
    .pip_install(
        "torch==2.5.1", "torchvision==0.20.1",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "huggingface_hub", "Pillow", "numpy", "trimesh[easy]",
        # Keep the tested Diffusers version for Hunyuan's local custom pipeline.
        "einops", "diffusers==0.31.0", "accelerate",
        "transformers==4.49.0", "omegaconf", "tqdm",
        "scikit-image", "scipy", "opencv-python-headless",
        "xatlas", "pymeshlab", "pygltflib",
        "rembg", "onnxruntime",
        "pydantic==2.10.6", "ninja", "pybind11",
    )
    .run_commands(
        # wheel needed by diso's setup.py bdist_wheel
        "pip install wheel setuptools",
        # diso: CUDA extension, needs torch headers (--no-build-isolation) and CUDA CPATH
        "CPATH=/usr/local/cuda/include:${CPATH:-} TORCH_CUDA_ARCH_LIST=8.6 pip install diso --no-build-isolation",
        # Pin torch in case any dep above upgraded it
        "pip install torch==2.5.1 torchvision==0.20.1 --extra-index-url https://download.pytorch.org/whl/cu121 --force-reinstall --no-deps",
        # Official Tencent repo — has FlashVDM, Turbo models, correct texture pipeline
        "git clone --depth=1 https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git /hunyuan",
        "cd /hunyuan && pip install -e . --no-deps",
        # TORCH_CUDA_ARCH_LIST=8.6: required when building without a visible GPU (A10G = SM 8.6)
        "cd /hunyuan/hy3dgen/texgen/custom_rasterizer && TORCH_CUDA_ARCH_LIST=8.6 CPATH=/usr/local/cuda/include:${CPATH:-} python3 setup.py install",
        "cd /hunyuan/hy3dgen/texgen/differentiable_renderer && TORCH_CUDA_ARCH_LIST=8.6 CPATH=/usr/local/cuda/include:${CPATH:-} python3 setup.py install",
    )
    .add_local_dir("models", remote_path="/root/models")
)

web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "python-multipart", "Pillow")
)

# ---------------------------------------------------------------------------
# GPU functions
# ---------------------------------------------------------------------------

@app.function(
    gpu="A10G",
    image=sf3d_image,
    volumes={"/models": model_volume},
    secrets=[modal.Secret.from_name(HUGGINGFACE_SECRET_NAME)],
    timeout=600,
)
def run_sf3d(image_bytes: bytes, quality: str = "balanced") -> bytes:
    import sys
    sys.path.insert(0, "/sf3d")
    from PIL import Image
    from models.sf3d import generate as sf3d_generate
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    return sf3d_generate(pil_image, quality=quality)


@app.function(
    gpu="A10G",
    image=trellis_image,
    volumes={"/models": model_volume},
    secrets=[modal.Secret.from_name(HUGGINGFACE_SECRET_NAME)],
    timeout=1200,
    scaledown_window=600,
)
def run_trellis(prompt: Optional[str], image_bytes: Optional[bytes], quality: str = "balanced") -> bytes:
    import sys
    sys.path.insert(0, "/trellis")
    from PIL import Image
    from models.trellis import generate as trellis_generate

    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA") if image_bytes else None
    return trellis_generate(prompt=prompt, image=pil_image, quality=quality)


@app.function(gpu="A10G", image=hunyuan_image, volumes={"/models": model_volume}, timeout=1200, scaledown_window=600)
def run_hunyuan(prompt: Optional[str], image_bytes: Optional[bytes], quality: str = "balanced") -> bytes:
    import sys
    sys.path.insert(0, "/hunyuan")
    from PIL import Image
    from models.hunyuan import generate as hunyuan_generate
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA") if image_bytes else None
    return hunyuan_generate(prompt=prompt, image=pil_image, quality=quality)


# ---------------------------------------------------------------------------
# Web API — FastAPI importado APENAS aqui (web_image tem fastapi, gpu images não)
# ---------------------------------------------------------------------------

@app.function(image=web_image)
@modal.asgi_app(label="dive-3d-gen")
def serve():
    from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware

    web_app = FastAPI(title="Dive 3D Gen API", version="0.1.0")
    web_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    MODELS = {"sf3d": run_sf3d, "trellis": run_trellis, "hunyuan": run_hunyuan}
    MODEL_SUPPORTS_TEXT = {"sf3d": False, "trellis": True, "hunyuan": False}

    def _validate_key(key: str) -> bool:
        try:
            entry = api_keys_store.get(key)
            return bool(entry and entry.get("active", True))
        except Exception:
            return False

    @web_app.get("/health")
    async def health():
        return {"status": "ok", "models": list(MODELS.keys())}

    @web_app.post("/generate")
    async def generate(
        model: str = Form("sf3d"),
        prompt: Optional[str] = Form(None),
        quality: str = Form("balanced"),
        image: Optional[UploadFile] = File(None),
        x_api_key: str = Header(..., alias="X-API-Key"),
    ):
        if not _validate_key(x_api_key):
            raise HTTPException(status_code=403, detail="API key inválida.")
        if model not in MODELS:
            raise HTTPException(status_code=400, detail=f"Modelo desconhecido: {model}.")
        if not MODEL_SUPPORTS_TEXT[model] and not image:
            raise HTTPException(status_code=400, detail=f"'{model}' requer imagem.")
        if not prompt and not image:
            raise HTTPException(status_code=400, detail="Envie prompt ou imagem.")

        image_bytes = await image.read() if image else None

        try:
            entry = api_keys_store[x_api_key]
            entry["requests"] = entry.get("requests", 0) + 1
            api_keys_store[x_api_key] = entry
        except Exception:
            pass

        fn = MODELS[model]
        if model == "sf3d":
            call = fn.spawn(image_bytes=image_bytes, quality=quality)
        else:
            call = fn.spawn(prompt=prompt, image_bytes=image_bytes, quality=quality)

        return {"job_id": call.object_id, "status": "queued", "model": model}

    @web_app.get("/status/{job_id}")
    async def status(job_id: str, x_api_key: str = Header(..., alias="X-API-Key")):
        if not _validate_key(x_api_key):
            raise HTTPException(status_code=403, detail="API key inválida.")
        import concurrent.futures
        try:
            call = modal.FunctionCall.from_id(job_id)
            glb_bytes: bytes = call.get(timeout=0)
            return {"status": "done", "glb_base64": base64.b64encode(glb_bytes).decode()}
        except (modal.exception.TimeoutError, TimeoutError, concurrent.futures.TimeoutError):
            return {"status": "running"}
        except modal.exception.RemoteError as exc:
            return {"status": "error", "detail": str(exc)}
        except Exception as exc:
            return {"status": "error", "detail": str(exc) or type(exc).__name__}

    return web_app
