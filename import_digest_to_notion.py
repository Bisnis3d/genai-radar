import re
import os
import json
import shutil
from pathlib import Path
from datetime import datetime

from notion_client import Client
from dotenv import load_dotenv


# ----------------------------
# Config (.env)
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_ID = os.getenv("NOTION_DB_ID")

if not NOTION_TOKEN or not DB_ID:
    raise SystemExit("Faltan variables de entorno: NOTION_TOKEN y/o NOTION_DB_ID")

notion = Client(auth=NOTION_TOKEN)


# ----------------------------
# Anti-duplicados LOCAL (diario + global)
# ----------------------------
def today_key() -> str:
    return datetime.now().strftime("%Y%m%d")


def load_global_log() -> dict:
    """
    Log global permanente: state/import_log_global.json
    Evita duplicados entre distintos días.
    """
    state_dir = BASE_DIR / "state"
    state_dir.mkdir(exist_ok=True)

    log_path = state_dir / "import_log_global.json"
    if not log_path.exists():
        return {"path": log_path, "urls": set(), "names": set()}

    data = json.loads(log_path.read_text(encoding="utf-8") or "{}")
    return {
        "path": log_path,
        "urls": set(data.get("urls", [])),
        "names": set(data.get("names", [])),
    }


def load_import_log() -> dict:
    """
    Log diario: state/import_log_YYYYMMDD.json
    Evita duplicados si ejecutas el .bat varias veces el mismo día.
    """
    state_dir = BASE_DIR / "state"
    state_dir.mkdir(exist_ok=True)

    log_path = state_dir / f"import_log_{today_key()}.json"
    if not log_path.exists():
        return {"path": log_path, "urls": set(), "names": set()}

    data = json.loads(log_path.read_text(encoding="utf-8") or "{}")
    return {
        "path": log_path,
        "urls": set(data.get("urls", [])),
        "names": set(data.get("names", [])),
    }


def save_log(log: dict):
    payload = {
        "urls": sorted(list(log["urls"])),
        "names": sorted(list(log["names"])),
    }
    log["path"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def is_duplicate(url: str, title: str, daily_log: dict, global_log: dict) -> bool:
    """Comprueba duplicado en log diario y en log global."""
    if url:
        if url in daily_log["urls"] or url in global_log["urls"]:
            return True
    if not url and title:
        if title in daily_log["names"] or title in global_log["names"]:
            return True
    return False


def mark_imported(url: str, title: str, daily_log: dict, global_log: dict):
    if url:
        daily_log["urls"].add(url)
        global_log["urls"].add(url)
    if title:
        daily_log["names"].add(title)
        global_log["names"].add(title)


# ----------------------------
# Heurísticas (Source / Category / Ecosystem)
# ----------------------------
CATEGORY_COVERS = {
    "Generación":      "https://raw.githubusercontent.com/Bisnis3d/img_notion/main/cat_Generacin.png",
    "Control":         "https://raw.githubusercontent.com/Bisnis3d/img_notion/main/cat_Control.png",
    "Motion":          "https://raw.githubusercontent.com/Bisnis3d/img_notion/main/cat_Motion.png",
    "LoRA / Adapter":  "https://raw.githubusercontent.com/Bisnis3d/img_notion/main/cat_LoRA___Adapter.png",
    "Postproceso":     "https://raw.githubusercontent.com/Bisnis3d/img_notion/main/cat_Postproceso.png",
    "Workflow / Node": "https://raw.githubusercontent.com/Bisnis3d/img_notion/main/cat_Workflow___Node.png",
    "Tooling":         "https://raw.githubusercontent.com/Bisnis3d/img_notion/main/cat_Tooling.png",
    "Conocimiento":    "https://raw.githubusercontent.com/Bisnis3d/img_notion/main/cat_Conocimiento.png",
}


def guess_source(url: str) -> str:
    u = (url or "").lower()
    if "github.com" in u:
        return "GitHub"
    if "huggingface.co" in u:
        return "HuggingFace"
    if "civitai.com" in u:
        return "Civitai"
    if "docs" in u or "documentation" in u:
        return "Docs"
    return "Blog"


def guess_category(title: str, body: str) -> str:
    t = (title + " " + body).lower()
    # Motion — vídeo/animación, primero para no confundir con Control
    if any(k in t for k in ["motion", "video", "animate", "animation", "i2v", "t2v", "vid2vid"]):
        return "Motion"
    # Control — controlnet, ip-adapter, pose, depth
    if any(k in t for k in ["controlnet", "control net", "ip-adapter", "ipadapter",
                              "ip adapter", "pose", "depth", "canny", "inpaint", "reference"]):
        return "Control"
    # LoRA / Adapter
    if any(k in t for k in ["lora", "lycoris", "lcm", "adapter"]):
        return "LoRA / Adapter"
    # Postproceso
    if any(k in t for k in ["upscal", "esrgan", "swinir", "restore", "enhance", "super resolution"]):
        return "Postproceso"
    # Tooling — gestores, downloaders
    if any(k in t for k in ["manager", "downloader", "installer", "hub", "sync"]):
        return "Tooling"
    # Conocimiento — papers, docs
    if any(k in t for k in ["paper", "arxiv", "doc", "guide", "tutorial", "survey"]):
        return "Conocimiento"
    # Workflow / Node
    if any(k in t for k in ["node", "custom node", "comfyui-", "workflow", "pipeline"]):
        return "Workflow / Node"
    # Generación — checkpoints, modelos base
    if any(k in t for k in ["checkpoint", "model", "flux", "sdxl", "stable diffusion", "qwen"]):
        return "Generación"
    return "Workflow / Node"  # fallback más probable para este perfil


def guess_ecosystem(title: str, body: str, url: str) -> str:
    t = (title + " " + body + " " + url).lower()
    if any(k in t for k in ["wan2", "wanvideo", "wan video", "wan2.1", " wan "]):
        return "Wan"
    if any(k in t for k in ["qwen", "qwen-vl", "qwen2"]):
        return "Qwen"
    if "flux" in t:
        return "Flux"
    if any(k in t for k in ["sdxl", "pony", "illustrious"]):
        return "SDXL"
    if any(k in t for k in ["sd 1.5", "sd1.5", "sd15", "stable-diffusion-v1"]):
        return "SD 1.5"
    if any(k in t for k in ["comfyui", "comfy ui", "comfy-ui"]):
        return "ComfyUI"
    return "Multi"


# ----------------------------
# Notion create page
# ----------------------------
def create_page(item: dict):
    url = (item.get("url") or "").strip()
    title = item["title"]

    # Aviso si el título se trunca
    if len(title) > 200:
        print(f"  AVISO: Título truncado a 200 chars: '{title[:60]}...'")

    source = item.get("source") or guess_source(url)
    category = item.get("category") or guess_category(item.get("title", ""), item.get("raw", ""))
    ecosystem = item.get("ecosystem") or guess_ecosystem(item.get("title", ""), item.get("raw", ""), url)

    properties = {
        "Name": {"title": [{"text": {"content": title[:200]}}]},
        "Category": {"select": {"name": category}},
        "Source": {"select": {"name": source}},
        "Ecosystem": {"select": {"name": ecosystem}},
        "Summary": (
            {"rich_text": [{"text": {"content": item.get("que_es", "")[:2000]}}]}
            if item.get("que_es")
            else {"rich_text": []}
        ),
        "Use case": (
            {"rich_text": [{"text": {"content": item.get("para_que", "")[:2000]}}]}
            if item.get("para_que")
            else {"rich_text": []}
        ),
        "Requirements": (
            {"rich_text": [{"text": {"content": item.get("requisitos", "")[:2000]}}]}
            if item.get("requisitos")
            else {"rich_text": []}
        ),
        "Impact": (
            {"rich_text": [{"text": {"content": item.get("cambios", "")[:2000]}}]}
            if item.get("cambios")
            else {"rich_text": []}
        ),
        "Date": {"date": {"start": datetime.now().date().isoformat()}},
        "Status": {"select": {"name": "To review"}},
        "Priority": {"select": {"name": "Low"}},
        "Signal": {"checkbox": item.get("signal", False)},
    }

    # URL solo se incluye si tiene valor (pasar None rompe la API)
    if url:
        properties["URL"] = {"url": url}

    page_payload = {
        "parent": {"database_id": DB_ID},
        "properties": properties,
    }

    # Cover de página: imagen explícita del digest > cover por categoría
    imagen = (item.get("imagen") or "").strip()
    cover_url = imagen or CATEGORY_COVERS.get(category, "")
    if cover_url:
        page_payload["cover"] = {"type": "external", "external": {"url": cover_url}}

    notion.pages.create(**page_payload)


# ----------------------------
# Parser digest.txt
# ----------------------------
def pick_field(label: str, body: str) -> str:
    """
    Extrae el valor de un campo etiquetado, soportando valores multilínea.
    Captura desde la etiqueta hasta la siguiente etiqueta conocida o fin de bloque.
    """
    known_labels = [
        "URL", "Imagen", "Qué es", "Para qué sirve", "Requisitos", "Cambios importantes",
        "Categoría", "Ecosistema", "Signal"
    ]
    # Construye lookahead con el resto de etiquetas
    other_labels = [re.escape(l) for l in known_labels if l != label]
    lookahead = "|".join(other_labels)
    pattern = rf"(?mi)^\s*{re.escape(label)}\s*:\s*(.*?)(?=^\s*(?:{lookahead})\s*:|\Z)"
    m = re.search(pattern, body, re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip()


def parse_digest(text: str):
    """
    Formato esperado:

    # 1) Título
    URL: https://...
    Qué es: ...
    Para qué sirve: ...
    Requisitos: ...
    Cambios importantes: ...
    """
    blocks = re.split(r"(?m)^\s*#\s*\d+\)\s*", text)
    items = []

    for b in blocks:
        b = b.strip()
        if not b:
            continue

        lines = b.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        items.append(
            {
                "title": title,
                "url": pick_field("URL", body),
                "imagen": pick_field("Imagen", body),
                "que_es": pick_field("Qué es", body),
                "para_que": pick_field("Para qué sirve", body),
                "requisitos": pick_field("Requisitos", body),
                "cambios": pick_field("Cambios importantes", body),
                # Campos enriquecidos por enriquecer_digest.py (opcionales)
                "category": pick_field("Categoría", body) or None,
                "ecosystem": pick_field("Ecosistema", body) or None,
                "signal": pick_field("Signal", body).lower() == "true",
                "raw": body,
            }
        )

    return items


# ----------------------------
# Archivado digest
# ----------------------------
def archive_and_clear_digest():
    digest_path = BASE_DIR / "digest.txt"
    if not digest_path.exists():
        return

    archive_dir = BASE_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived = archive_dir / f"digest_{timestamp}.txt"

    shutil.copy2(digest_path, archived)
    digest_path.write_text("", encoding="utf-8")

    print(f"Archivado: {archived.name}")


# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    digest_file = BASE_DIR / "digest.txt"
    if not digest_file.exists():
        raise SystemExit("No existe digest.txt en la carpeta del script.")

    txt = digest_file.read_text(encoding="utf-8")
    items = parse_digest(txt)

    if not items:
        raise SystemExit("No se han detectado highlights. Revisa el formato de digest.txt")

    daily_log = load_import_log()
    global_log = load_global_log()

    created = 0
    skipped = 0
    failed = []

    for it in items:
        url = (it.get("url") or "").strip()
        title = (it.get("title") or "").strip()

        if is_duplicate(url, title, daily_log, global_log):
            print(f"  Saltado (duplicado): {title[:80]}")
            skipped += 1
            continue

        try:
            create_page(it)
            mark_imported(url, title, daily_log, global_log)
            created += 1
            print(f"  Creado: {title[:80]}")
        except Exception as e:
            print(f"  ERROR al crear '{title[:80]}': {e}")
            failed.append(title)

    save_log(daily_log)
    save_log(global_log)

    print()
    print(f"Resultado: {created} creados | {skipped} duplicados saltados | {len(failed)} errores")
    if failed:
        print("Items con error:")
        for f in failed:
            print(f"  - {f}")

    archive_and_clear_digest()
