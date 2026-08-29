import io
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

MODEL_CACHE = "/models/hunyuan"
MODEL_ID = "tencent/Hunyuan3D-2"

# Temporary end-to-end evidence capture for the texture investigation. It is
# deliberately limited to Hunyuan jobs and stored under the existing private
# Modal volume so the intermediate Paint outputs can be inspected directly.
TRACE_ENABLED = True
TRACE_ROOT = "/models/diagnostics"

_shape_pipeline = None
_tex_pipelines = {}

_MODEL_SUBFOLDERS = (
    "hunyuan3d-dit-v2-0-turbo",
    "hunyuan3d-paint-v2-0",
    "hunyuan3d-paint-v2-0-turbo",
    "hunyuan3d-delight-v2-0",
)


def _trace(message: str):
    print(f"[HunyuanTrace] {message}")


def _trace_dir_for_image(image: Optional[Image.Image]) -> Path:
    digest = "text-only" if image is None else hashlib.sha256(image.tobytes()).hexdigest()[:16]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(TRACE_ROOT, f"{run_id}_{digest}")


def _as_display_image(value):
    if isinstance(value, Image.Image):
        return value.convert("RGB")

    try:
        import torch

        if isinstance(value, torch.Tensor):
            value = value.detach().float().cpu().numpy()
    except ImportError:
        pass

    if not isinstance(value, np.ndarray):
        return None

    value = np.squeeze(value)
    if value.ndim != 3:
        return None
    if value.shape[0] in (1, 3, 4) and value.shape[-1] not in (1, 3, 4):
        value = np.moveaxis(value, 0, -1)
    if value.shape[-1] not in (1, 3, 4):
        return None

    if value.dtype.kind == "f":
        value = np.clip(value, 0.0, 1.0) * 255.0
    value = np.clip(value, 0, 255).astype(np.uint8)
    if value.shape[-1] == 1:
        value = np.repeat(value, 3, axis=-1)
    return Image.fromarray(value[..., :3], mode="RGB")


def _trace_artifact(trace_dir: Path, name: str, value):
    if not TRACE_ENABLED or value is None:
        return

    trace_dir.mkdir(parents=True, exist_ok=True)
    values = list(value) if isinstance(value, (list, tuple)) else [value]
    previews = [image for item in values if (image := _as_display_image(item)) is not None]
    if not previews:
        _trace(f"{name}: no preview available ({type(value).__name__})")
        return

    stats = []
    for index, image in enumerate(previews):
        pixels = np.asarray(image, dtype=np.float32)
        stats.append({
            "index": index,
            "size": list(image.size),
            "mean_rgb": np.round(pixels.mean(axis=(0, 1)), 2).tolist(),
            "std_rgb": np.round(pixels.std(axis=(0, 1)), 2).tolist(),
            "min_rgb": pixels.min(axis=(0, 1)).astype(int).tolist(),
            "max_rgb": pixels.max(axis=(0, 1)).astype(int).tolist(),
        })

    if len(previews) == 1:
        previews[0].save(trace_dir / f"{name}.png")
    else:
        tile_size = 512
        columns = min(3, len(previews))
        rows = (len(previews) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * tile_size, rows * tile_size), "black")
        for index, image in enumerate(previews):
            preview = image.copy()
            preview.thumbnail((tile_size, tile_size))
            x = (index % columns) * tile_size + (tile_size - preview.width) // 2
            y = (index // columns) * tile_size + (tile_size - preview.height) // 2
            sheet.paste(preview, (x, y))
        sheet.save(trace_dir / f"{name}.jpg", quality=92)

    (trace_dir / f"{name}.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    _trace(f"{name}: {json.dumps(stats, separators=(',', ':'))}")


def _trace_mesh(trace_dir: Path, name: str, mesh):
    if not TRACE_ENABLED:
        return

    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    summary = {
        "vertices": int(len(vertices)),
        "faces": int(len(faces)),
        "bounds": np.round(np.asarray(mesh.bounds), 5).tolist(),
    }
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / f"{name}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _trace(f"{name}: {json.dumps(summary, separators=(',', ':'))}")

    material = getattr(getattr(mesh, "visual", None), "material", None)
    _trace_artifact(trace_dir, f"{name}_albedo", getattr(material, "image", None))


def _commit_trace(trace_dir: Path, summary: dict):
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if TRACE_ENABLED:
        import modal

        modal.Volume.from_name("dive-3d-gen-models").commit()
        _trace(f"run={trace_dir.name} diagnostics committed to volume")


class _TraceCallable:
    def __init__(self, name: str, callback, target):
        self._name = name
        self._callback = callback
        self._target = target

    def __call__(self, *args, **kwargs):
        result = self._target(*args, **kwargs)
        self._callback(self._name, result)
        return result


def _attach_texture_trace(tex_pipe):
    if getattr(tex_pipe, "_dive_trace_attached", False):
        return

    def record(name, value):
        trace_dir = getattr(tex_pipe, "_dive_trace_dir", None)
        if trace_dir is not None:
            _trace_artifact(trace_dir, name, value)

    tex_pipe.models["delight_model"] = _TraceCallable(
        "01_delighted_input", record, tex_pipe.models["delight_model"]
    )
    tex_pipe.models["multiview_model"] = _TraceCallable(
        "04_predicted_views", record, tex_pipe.models["multiview_model"]
    )

    original_normals = tex_pipe.render_normal_multiview
    def traced_normals(*args, **kwargs):
        result = original_normals(*args, **kwargs)
        record("02_normal_controls", result)
        return result
    tex_pipe.render_normal_multiview = traced_normals

    original_positions = tex_pipe.render_position_multiview
    def traced_positions(*args, **kwargs):
        result = original_positions(*args, **kwargs)
        record("03_position_controls", result)
        return result
    tex_pipe.render_position_multiview = traced_positions

    original_bake = tex_pipe.bake_from_multiview
    def traced_bake(*args, **kwargs):
        result = original_bake(*args, **kwargs)
        record("05_baked_texture", result[0])
        record("05_bake_mask", result[1])
        return result
    tex_pipe.bake_from_multiview = traced_bake

    original_inpaint = tex_pipe.texture_inpaint
    def traced_inpaint(*args, **kwargs):
        result = original_inpaint(*args, **kwargs)
        record("06_inpainted_texture", result)
        return result
    tex_pipe.texture_inpaint = traced_inpaint
    tex_pipe._dive_trace_attached = True


def _ensure_model_cache():
    from huggingface_hub import snapshot_download

    missing = [name for name in _MODEL_SUBFOLDERS if not Path(MODEL_CACHE, name).exists()]
    if not missing:
        return

    print(f"[Hunyuan3D] Missing model folders in {MODEL_CACHE}: {missing}")
    snapshot_download(
        MODEL_ID,
        local_dir=MODEL_CACHE,
        allow_patterns=[f"{name}/*" for name in missing],
    )

    import modal

    modal.Volume.from_name("dive-3d-gen-models").commit()


def _texture_subfolder_for_quality(quality: str) -> str:
    # The official examples default to the full paint model. Keep turbo for
    # fast mode only; texture quality is the visible failure mode here.
    if quality == "fast":
        return "hunyuan3d-paint-v2-0-turbo"
    return "hunyuan3d-paint-v2-0"


def _load_pipelines(quality: str):
    global _shape_pipeline, _tex_pipelines

    tex_subfolder = _texture_subfolder_for_quality(quality)
    if _shape_pipeline and tex_subfolder in _tex_pipelines:
        return _shape_pipeline, _tex_pipelines[tex_subfolder]

    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
    from hy3dgen.texgen import Hunyuan3DPaintPipeline

    _ensure_model_cache()

    if _shape_pipeline is None:
        print("[Hunyuan3D] Loading shape model: hunyuan3d-dit-v2-0-turbo")
        _shape_pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
            MODEL_CACHE,
            subfolder="hunyuan3d-dit-v2-0-turbo",
            use_safetensors=True,
            device="cuda",
        )
        _shape_pipeline.enable_flashvdm()

    if tex_subfolder not in _tex_pipelines:
        print(f"[Hunyuan3D] Loading texture model: {tex_subfolder}")
        # A10G has 24 GB VRAM; total shape+texture pipeline needs about 16 GB.
        _tex_pipelines[tex_subfolder] = Hunyuan3DPaintPipeline.from_pretrained(
            MODEL_CACHE,
            subfolder=tex_subfolder,
        )
        _attach_texture_trace(_tex_pipelines[tex_subfolder])

    return _shape_pipeline, _tex_pipelines[tex_subfolder]


def _quality_to_steps(quality: str) -> int:
    # Turbo shape model uses step distillation, so it needs far fewer steps.
    return {"fast": 4, "balanced": 5, "high": 8}.get(quality, 5)


def generate(
    prompt: Optional[str],
    image: Optional[Image.Image],
    quality: str = "balanced",
) -> bytes:
    import torch

    shape_pipe, tex_pipe = _load_pipelines(quality)
    steps = _quality_to_steps(quality)
    tex_subfolder = _texture_subfolder_for_quality(quality)
    print(f"[Hunyuan3D] generate quality={quality} shape_steps={steps} texture={tex_subfolder}")

    trace_dir = _trace_dir_for_image(image)
    trace_summary = {
        "quality": quality,
        "shape_model": "hunyuan3d-dit-v2-0-turbo",
        "shape_steps": steps,
        "texture_model": tex_subfolder,
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
    }
    _trace(f"run={trace_dir.name} config={json.dumps(trace_summary, separators=(',', ':'))}")
    _trace_artifact(trace_dir, "00_input", image)

    if image is not None:
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        from hy3dgen.rembg import BackgroundRemover

        image = BackgroundRemover()(image)
        _trace_artifact(trace_dir, "00_background_removed", image)

    if image is not None:
        mesh = shape_pipe(
            image=image,
            num_inference_steps=steps,
            octree_resolution=256,
        )[0]
    else:
        mesh = shape_pipe(
            prompt=prompt,
            num_inference_steps=steps,
            octree_resolution=256,
        )[0]

    _trace_mesh(trace_dir, "07_shape_mesh_raw", mesh)

    # The official Tencent app/API preprocesses the generated mesh before Paint.
    # Feeding the raw 300k+ face mesh into xatlas creates a fragmented UV atlas,
    # which is exactly where the noisy speckled texture is introduced.
    from hy3dgen.shapegen import DegenerateFaceRemover, FaceReducer, FloaterRemover

    try:
        mesh = FloaterRemover()(mesh)
        mesh = DegenerateFaceRemover()(mesh)
        mesh = FaceReducer()(mesh, max_facenum=40000)
    except Exception as exc:
        trace_summary["error"] = {
            "stage": "mesh_preprocess",
            "type": type(exc).__name__,
            "message": str(exc),
        }
        _trace(f"run={trace_dir.name} mesh_preprocess_error={type(exc).__name__}: {exc}")
        _commit_trace(trace_dir, trace_summary)
        raise
    _trace_mesh(trace_dir, "07_shape_mesh_for_paint", mesh)
    torch.cuda.empty_cache()

    texture_pipeline = tex_pipe.models["multiview_model"]._target.pipeline
    trace_summary.update({
        "paint_pipeline": type(texture_pipeline).__name__,
        "paint_scheduler": type(texture_pipeline.scheduler).__name__,
        "paint_unet": f"{type(texture_pipeline.unet).__module__}.{type(texture_pipeline.unet).__name__}",
    })
    tex_pipe._dive_trace_dir = trace_dir

    try:
        mesh = tex_pipe(mesh, image=image)
        _trace_mesh(trace_dir, "08_textured_mesh", mesh)
    finally:
        _commit_trace(trace_dir, trace_summary)

    _ = mesh.vertex_normals
    buf = io.BytesIO()
    mesh.export(buf, file_type="glb")
    _trace(f"run={trace_dir.name} glb_bytes={buf.tell()} glb_sha256={hashlib.sha256(buf.getvalue()).hexdigest()}")
    return buf.getvalue()
