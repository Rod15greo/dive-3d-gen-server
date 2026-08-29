"""
Stable Fast 3D (SF3D) — Stability AI
https://github.com/Stability-AI/stable-fast-3d

Geração de mesh + PBR em ~0.5 s a partir de uma imagem.
Requer ~6 GB VRAM (roda tranquilo em A10G 24 GB).
Entrada: imagem RGBA (PIL)
Saída:   bytes do arquivo .glb
"""

import io
from pathlib import Path

import torch
from PIL import Image

MODEL_CACHE = "/models/sf3d"
MODEL_ID = "stabilityai/stable-fast-3d"

_model = None  # singleton — reutilizado entre requisições no mesmo container


def _load_model():
    global _model  # noqa: WPS420
    if _model is not None:
        return _model

    import sys
    sys.path.insert(0, "/sf3d")
    from huggingface_hub import snapshot_download
    from sf3d.system import SF3D

    if not Path(f"{MODEL_CACHE}/config.yaml").exists() or not Path(f"{MODEL_CACHE}/model.safetensors").exists():
        print("Baixando SF3D...")
        snapshot_download(MODEL_ID, local_dir=MODEL_CACHE)
        # Persiste no volume para próximos cold starts
        import modal
        modal.Volume.from_name("dive-3d-gen-models").commit()

    _model = SF3D.from_pretrained(
        MODEL_CACHE,
        config_name="config.yaml",
        weight_name="model.safetensors",
    ).to("cuda")
    _model.eval()
    print("SF3D carregado.")
    return _model


def _quality_to_params(quality: str) -> dict:
    return {
        "fast":     {"bake_resolution": 512},
        "balanced": {"bake_resolution": 1024},
        "high":     {"bake_resolution": 2048},
    }.get(quality, {"bake_resolution": 1024})


def generate(image: Image.Image, quality: str = "balanced") -> bytes:
    model = _load_model()
    params = _quality_to_params(quality)

    # Remove fundo se a imagem não tiver canal alpha já limpo
    from sf3d.utils import remove_background, resize_foreground
    import rembg

    image = remove_background(image.convert("RGBA"), rembg.new_session())
    image = resize_foreground(image, ratio=0.85)

    with torch.no_grad():
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            mesh, _ = model.run_image(image, **params)

    buf = io.BytesIO()
    mesh.export(buf, file_type="glb", include_normals=True)
    print(f"[SF3D] Generated {buf.tell()} GLB bytes at {params['bake_resolution']}px")
    return buf.getvalue()


def _has_white_background(image: Image.Image) -> bool:
    """Heurística simples: verifica se os cantos são brancos."""
    arr = image.convert("RGBA").load()
    w, h = image.size
    corners = [arr[0, 0], arr[w - 1, 0], arr[0, h - 1], arr[w - 1, h - 1]]
    return all(c[3] > 200 and c[0] > 200 and c[1] > 200 and c[2] > 200 for c in corners)


def _remove_background(image: Image.Image) -> Image.Image:
    try:
        from rembg import remove
        return remove(image.convert("RGB"))
    except ImportError:
        return image.convert("RGBA")
