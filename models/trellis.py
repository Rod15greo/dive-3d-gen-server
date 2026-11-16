"""Official Microsoft TRELLIS image/text-to-3D wrapper."""

import io
import os
from pathlib import Path
from typing import Optional

from PIL import Image

MODEL_CACHE = "/models/trellis"
# Mesmo nome de Volume usado por main.py (repassado ao container via .env()).
MODEL_VOLUME_NAME = os.getenv("DIVE3D_MODEL_VOLUME", "dive-3d-gen-models")
IMAGE_MODEL_ID = "microsoft/TRELLIS-image-large"
TEXT_MODEL_ID = "microsoft/TRELLIS-text-large"

_image_pipeline = None
_text_pipeline = None


def _configure_runtime() -> None:
    # xFormers has a prebuilt CUDA 12.1 wheel. Native spconv avoids per-worker tuning.
    os.environ.setdefault("ATTN_BACKEND", "xformers")
    os.environ.setdefault("SPCONV_ALGO", "native")


def _model_path(name: str) -> str:
    return f"{MODEL_CACHE}/{name}"


def _ensure_model(model_id: str, name: str) -> str:
    model_path = _model_path(name)
    if Path(f"{model_path}/pipeline.json").exists():
        return model_path

    from huggingface_hub import snapshot_download

    print(f"[TRELLIS] Downloading {model_id}...")
    snapshot_download(model_id, local_dir=model_path)

    import modal

    modal.Volume.from_name(MODEL_VOLUME_NAME).commit()
    return model_path


def _load_image_pipeline():
    global _image_pipeline
    if _image_pipeline is not None:
        return _image_pipeline

    _configure_runtime()
    from trellis.pipelines import TrellisImageTo3DPipeline

    _image_pipeline = TrellisImageTo3DPipeline.from_pretrained(
        _ensure_model(IMAGE_MODEL_ID, "image-large")
    )
    _image_pipeline.cuda()
    print("[TRELLIS] Image pipeline loaded.")
    return _image_pipeline


def _load_text_pipeline():
    global _text_pipeline
    if _text_pipeline is not None:
        return _text_pipeline

    _configure_runtime()
    from trellis.pipelines import TrellisTextTo3DPipeline

    _text_pipeline = TrellisTextTo3DPipeline.from_pretrained(
        _ensure_model(TEXT_MODEL_ID, "text-large")
    )
    _text_pipeline.cuda()
    print("[TRELLIS] Text pipeline loaded.")
    return _text_pipeline


def _quality_to_params(quality: str) -> dict:
    values = {
        "fast": (12, 512, 0.95),
        "balanced": (20, 1024, 0.95),
        "high": (50, 2048, 0.90),
    }
    steps, texture_size, simplify = values.get(quality, values["balanced"])
    return {
        "sparse_structure_sampler_params": {"steps": steps},
        "slat_sampler_params": {"steps": steps},
        "texture_size": texture_size,
        "simplify": simplify,
    }


def generate(
    prompt: Optional[str], image: Optional[Image.Image], quality: str = "balanced"
) -> bytes:
    if image is None and not prompt:
        raise ValueError("TRELLIS requires an image or a text prompt.")

    params = _quality_to_params(quality)
    sampler_params = {
        "sparse_structure_sampler_params": params["sparse_structure_sampler_params"],
        "slat_sampler_params": params["slat_sampler_params"],
    }

    if image is not None:
        outputs = _load_image_pipeline().run(image, seed=42, **sampler_params)
    else:
        outputs = _load_text_pipeline().run(prompt, seed=42, **sampler_params)

    from trellis.utils import postprocessing_utils

    glb = postprocessing_utils.to_glb(
        outputs["gaussian"][0],
        outputs["mesh"][0],
        simplify=params["simplify"],
        texture_size=params["texture_size"],
    )
    buffer = io.BytesIO()
    glb.export(buffer, file_type="glb")
    print(
        f"[TRELLIS] Generated {buffer.tell()} GLB bytes "
        f"at {params['texture_size']}px."
    )
    return buffer.getvalue()
