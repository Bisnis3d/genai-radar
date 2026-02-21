"""
monitor_sources.py  v4
----------------------
Monitoriza fuentes clave del ecosistema ComfyUI / GenAI y genera
un digest.txt listo para clasificar e importar a Notion.

Fuentes:
  - GitHub API (repos nuevos por query + releases de 26 repos clave)
  - HuggingFace API (modelos nuevos por tags, filtro estricto)
  - RSS de blogs de vendors
  - Civitai API (LoRAs nuevas: Flux · SDXL · Wan · Illustrious)
  - OpenModelDB (modelos upscaling via commits del repo GitHub)
  - Awesome ComfyUI (lista curada: nuevos + trending nodes por stars)

Requiere en .env:
  GITHUB_TOKEN=github_pat_...  (fine-grained o classic)
"""

import os
import re
import json
import time
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# ----------------------------
# Config
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(exist_ok=True)
SEEN_FILE   = STATE_DIR / "monitor_seen.json"
DIGEST_FILE     = BASE_DIR / "digest_raw.txt"   # clasificar antes de importar
DIGEST_IMPORT   = BASE_DIR / "digest.txt"        # este es el que importa el sistema

LOOKBACK_DAYS = 7   # Ventana de búsqueda en días
MIN_STARS_NEW = 10  # Mínimo stars para repos nuevos desconocidos
MIN_HF_LIKES  = 5   # Mínimo likes en HuggingFace
MIN_HF_DL     = 50  # Mínimo descargas en HuggingFace


# ----------------------------
# Estado (URLs ya vistas)
# ----------------------------
def load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except:
            return set()
    return set()

def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")


# ----------------------------
# HTTP helpers
# ----------------------------
def github_headers() -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h

def safe_get_json(url, headers=None, params=None, timeout=15):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 403:
            print(f"  ⚠  Rate limit o acceso denegado: {url}")
        elif r.status_code == 422:
            print(f"  ⚠  Query inválida: {url}")
        else:
            print(f"  ⚠  HTTP {r.status_code}: {url}")
        return None
    except Exception as e:
        print(f"  ⚠  Error: {e}")
        return None

def safe_get_text(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "GenAI-Radar/1.0"})
        if r.status_code == 200:
            return r.text
        print(f"  ⚠  HTTP {r.status_code}: {url}")
        return None
    except Exception as e:
        print(f"  ⚠  Error: {e}")
        return None


# ----------------------------
# Fechas
# ----------------------------
def cutoff_dt() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except:
        return None

def is_recent(date_str: str) -> bool:
    dt = parse_iso(date_str)
    return dt is not None and dt >= cutoff_dt()


# ----------------------------
# Filtros de relevancia
# ----------------------------

# Términos que indican ruido → descartar
NOISE_RE = re.compile(
    r"\b(showcase|prompt[_\-\s]?pack|style[_\-\s]?pack|art[_\-\s]?pack|"
    r"gallery|aesthetic|wallpaper|nsfw|embedding[_\-\s]?pack|"
    r"test\d*$|sandbox|dummy|placeholder|backup|personal|private)\b",
    re.IGNORECASE
)

# Términos técnicos clave → mantener
SIGNAL_RE = re.compile(
    r"\b(comfyui|controlnet|lora|lycori|lcm|flux|wan|qwen|sdxl|"
    r"sd[_\-\s]?1[_\-\s]?5|checkpoint|upscaler|ipadapter|ip[_\-\s]?adapter|"
    r"animatediff|video|motion|node|workflow|loader|pipeline|"
    r"diffusion|inpaint|outpaint|refiner|vae|clip|t5|"
    r"gguf|safetensor|hunyuan|mochi|ltx|cogvideo|wan2|"
    r"image[_\-\s]?to[_\-\s]?video|text[_\-\s]?to[_\-\s]?video)\b",
    re.IGNORECASE
)

def is_relevant(text: str) -> bool:
    if NOISE_RE.search(text):
        return False
    return bool(SIGNAL_RE.search(text))

# Nombres de repos/modelos que son claramente personales/triviales
TRIVIAL_NAME_RE = re.compile(
    r"^(test|sandbox|backup|temp|tmp|untitled|model|lora|my[_\-]|"
    r"[a-z]{1,4}\d{1,4}$)",
    re.IGNORECASE
)

def is_trivial_name(name: str) -> bool:
    short_name = name.split("/")[-1]
    return bool(TRIVIAL_NAME_RE.match(short_name))


# ----------------------------
# Anti-duplicados cross-fuente — normalización de título
# ----------------------------
_VERSION_RE    = re.compile(r"\bv?\d+[\.\d]*\b", re.IGNORECASE)
_PLATFORM_RE   = re.compile(r"\b(comfyui|huggingface|civitai|github|sdxl|flux|wan|sd ?1\.?5)\b", re.IGNORECASE)
_EMOJI_RE      = re.compile(r"[^\x00-\x7F]+")
_SPACES_RE     = re.compile(r"\s+")

def normalize_title(title: str) -> str:
    """Normaliza un título para comparación cross-fuente."""
    t = title.lower()
    t = _EMOJI_RE.sub(" ", t)          # eliminar emojis y unicode decorativo
    t = _VERSION_RE.sub(" ", t)        # eliminar números de versión
    t = _PLATFORM_RE.sub(" ", t)       # eliminar nombres de plataforma
    t = re.sub(r"[_\-\(\)\[\]:]", " ", t)  # separadores → espacio
    t = _SPACES_RE.sub(" ", t).strip()
    return t

# Set de títulos normalizados ya vistos en esta ejecución (cross-fuente)
_NORM_TITLES_SEEN: set[str] = set()

def is_cross_duplicate(title: str) -> bool:
    """Devuelve True si ya hay una entrada con título normalizado equivalente."""
    norm = normalize_title(title)
    if norm in _NORM_TITLES_SEEN:
        return True
    _NORM_TITLES_SEEN.add(norm)
    return False


# ----------------------------
# Scoring de relevancia (0-100)
# ----------------------------
_IMPACT_KEYWORDS = re.compile(
    r"\b(release|v\d|fp8|quantiz|gguf|flux|wan|qwen|hunyuan|ltx|cogvideo|"
    r"mochi|soulx|mova|lightning|turbo|feat|wrapper|trainer|xl|"
    r"ip.adapter|controlnet|animatediff|motion|video|i2v|t2v|"
    r"upscal|esrgan|restore|inpaint|refiner)\b",
    re.IGNORECASE
)

_HIGH_ECOSYSTEMS = {"Flux", "Wan", "Qwen"}
_MED_ECOSYSTEMS  = {"SDXL", "ComfyUI"}

_SOURCE_SCORE = {
    "GitHub":       30,   # release de repo conocido
    "HuggingFace":  20,
    "Civitai":      15,
    "Blog":         25,   # post de vendor = noticia relevante
    "Docs":         10,
    "OpenModelDB":  10,
}

def score_entry(e: dict) -> int:
    """
    Calcula una puntuación de relevancia 0-100 para una entrada del digest.
    Criterios:
      - Fuente                       0-30
      - Keywords de impacto          0-30  (acumulativo, max 30)
      - Ecosistema activo            0-20
      - Métricas de tracción         0-20  (stars, descargas)
    """
    score = 0
    text  = f"{e.get('title','')} {e.get('que_es','')} {e.get('cambios','')}".lower()

    # Fuente
    source = e.get("_source", "")
    score += _SOURCE_SCORE.get(source, 10)

    # Keywords de impacto (max 30)
    hits = len(_IMPACT_KEYWORDS.findall(text))
    score += min(hits * 6, 30)

    # Ecosistema
    eco = e.get("_ecosystem_hint", "")
    if eco in _HIGH_ECOSYSTEMS:
        score += 20
    elif eco in _MED_ECOSYSTEMS:
        score += 10
    else:
        score += 5

    # Tracción (stars GitHub o descargas HF/Civitai)
    traction = e.get("_traction", 0)
    if traction >= 1000:
        score += 20
    elif traction >= 200:
        score += 12
    elif traction >= 50:
        score += 6

    return min(score, 100)


# ----------------------------
# Formato digest
# ----------------------------
def format_entry(idx, title, url, que_es, para_que, requisitos, cambios, score=None) -> str:
    score_line = f"Score: {score}\n" if score is not None else ""
    return "\n".join([
        f"# {idx}) {title}",
        f"URL: {url}",
        f"Qué es: {que_es}",
        f"Para qué sirve: {para_que}",
        f"Requisitos: {requisitos}",
        f"Cambios importantes: {cambios}",
        score_line.rstrip(),
        "",
    ])


def guess_ecosystem_hint(text: str) -> str:
    """Versión ligera de guess_ecosystem para el monitor (sin importar el importador)."""
    t = text.lower()
    if any(k in t for k in ["wan2", "wanvideo", "wan video", "wan2.1", " wan "]):
        return "Wan"
    if any(k in t for k in ["qwen", "qwen2"]):
        return "Qwen"
    if "flux" in t:
        return "Flux"
    if any(k in t for k in ["sdxl", "pony", "illustrious"]):
        return "SDXL"
    if any(k in t for k in ["comfyui", "comfy"]):
        return "ComfyUI"
    return "Multi"


# ----------------------------
# FUENTE 1: GitHub — repos nuevos
# ----------------------------
GITHUB_QUERIES = [
    ("comfyui custom node", 15),
    ("comfyui workflow", 15),
    ("controlnet comfyui", 10),
    ("flux comfyui loader", 10),
    ("wan video comfyui", 10),
    ("comfyui video generation", 10),
    ("stable diffusion pipeline python", 10),
    ("animatediff comfyui", 10),
    ("comfyui upscaler node", 5),
    ("image generation comfyui tool", 10),
]

def fetch_github_repos(seen: set) -> list[dict]:
    entries = []
    cutoff_str = cutoff_dt().strftime("%Y-%m-%d")

    for query, min_stars in GITHUB_QUERIES:
        print(f"    query: '{query}'")
        data = safe_get_json(
            "https://api.github.com/search/repositories",
            headers=github_headers(),
            params={
                "q": f"{query} created:>{cutoff_str}",
                "sort": "stars",
                "order": "desc",
                "per_page": 8,
            }
        )
        if not data:
            time.sleep(2)
            continue

        for repo in data.get("items", []):
            url = repo.get("html_url", "")
            if url in seen:
                continue

            stars = repo.get("stargazers_count", 0)
            if stars < min_stars:
                continue

            name = repo.get("full_name", "")
            description = repo.get("description") or ""

            # Filtro nombre trivial
            if is_trivial_name(name):
                continue

            # Filtro relevancia
            if not is_relevant(f"{name} {description}"):
                continue

            topics = ", ".join(repo.get("topics", []))
            title = repo.get("name", name)
            entries.append({
                "title": title,
                "url": url,
                "que_es": description or f"Repositorio GitHub: {name}",
                "para_que": f"Herramienta/integración para ecosistema ComfyUI/GenAI. ⭐ {stars} stars.",
                "requisitos": "Ver README del repositorio.",
                "cambios": f"Repositorio nuevo. Topics: {topics}" if topics else "Repositorio nuevo.",
                "_source": "GitHub",
                "_ecosystem_hint": "",
                "_traction": stars,
            })
            seen.add(url)

        time.sleep(1)

    return entries


# ----------------------------
# FUENTE 2: GitHub — releases de repos clave
# ----------------------------
KEY_REPOS = [
    # ComfyUI core
    "comfyanonymous/ComfyUI",
    "ltdrdata/ComfyUI-Manager",
    # Wrappers de modelos de vídeo
    "kijai/ComfyUI-WanVideoWrapper",
    "kijai/ComfyUI-HunyuanVideoWrapper",
    "kijai/ComfyUI-CogVideoXWrapper",
    "kijai/ComfyUI-LTXVideo",
    "kijai/ComfyUI-MochiWrapper",
    "Kosinkadink/ComfyUI-AnimateDiff-Evolved",
    # Control / IP-Adapter
    "cubiq/ComfyUI_IPAdapter_plus",
    "Fannovel16/comfyui_controlnet_aux",
    # Quantización / GGUF
    "city96/ComfyUI-GGUF",
    # Tooling / nodos
    "chrisgoringe/cg-use-everywhere",
    "rgthree/rgthree-comfy",
    "pythongosssss/ComfyUI-Custom-Scripts",
    # Entrenamiento
    "kohya-ss/sd-scripts",
    "ostris/ai-toolkit",
    # Frontends alternativos
    "lllyasviel/stable-diffusion-webui-forge",
    "mcmonkeyprojects/SwarmUI",
    "AUTOMATIC1111/stable-diffusion-webui",
    # Modelos base / ecosistemas
    "black-forest-labs/flux",
    "huggingface/diffusers",
    "Wan-AI/Wan2.1",
    "QwenLM/Qwen2.5",
    # OpenModelDB (monitorizado via commits del repo)
    "OpenModelDB/open-model-database",
]

def fetch_github_releases(seen: set) -> list[dict]:
    entries = []
    for repo in KEY_REPOS:
        print(f"    repo: {repo}")

        # Intentar releases primero
        releases = safe_get_json(
            f"https://api.github.com/repos/{repo}/releases",
            headers=github_headers(),
            params={"per_page": 3}
        )

        if releases:
            for release in releases:
                url = release.get("html_url", "")
                if url in seen:
                    continue
                if not is_recent(release.get("published_at", "")):
                    continue

                tag  = release.get("tag_name", "")
                body = (release.get("body") or "")[:300].replace("\n", " ").strip()
                name = repo.split("/")[-1]

                entries.append({
                    "title": f"{name} {tag}",
                    "url": url,
                    "que_es": f"Release {tag} de {repo}.",
                    "para_que": body or f"Nueva versión de {name}.",
                    "requisitos": "Actualizar desde el repositorio o ComfyUI Manager.",
                    "cambios": body or "Ver release notes en GitHub.",
                    "_source": "GitHub",
                    "_ecosystem_hint": guess_ecosystem_hint(repo),
                    "_traction": 0,
                })
                seen.add(url)
        else:
            # Fallback: commits recientes del repo
            commits = safe_get_json(
                f"https://api.github.com/repos/{repo}/commits",
                headers=github_headers(),
                params={"per_page": 1}
            )
            if commits and len(commits) > 0:
                commit = commits[0]
                commit_date = commit.get("commit", {}).get("committer", {}).get("date", "")
                if is_recent(commit_date):
                    url = commit.get("html_url", "")
                    if url and url not in seen:
                        msg = commit.get("commit", {}).get("message", "")[:150]
                        name = repo.split("/")[-1]
                        entries.append({
                            "title": f"{name} — commit reciente",
                            "url": f"https://github.com/{repo}",
                            "que_es": f"Actividad reciente en {repo}.",
                            "para_que": msg or f"Cambios recientes en {name}.",
                            "requisitos": "git pull o actualizar desde ComfyUI Manager.",
                            "cambios": msg or "Ver commits recientes.",
                            "_source": "GitHub",
                            "_ecosystem_hint": guess_ecosystem_hint(repo),
                            "_traction": 0,
                        })
                        seen.add(f"https://github.com/{repo}")

        time.sleep(0.5)

    return entries


# ----------------------------
# FUENTE 3: HuggingFace — modelos nuevos (filtro estricto)
# ----------------------------
HF_SEARCHES = [
    # (tag, min_likes, min_downloads)
    ("controlnet",        3,  100),
    ("wan-2.1",           3,   50),
    ("wan-2.2",           3,   50),
    ("flux",              5,  200),
    ("stable-diffusion-xl", 5, 200),
    ("image-to-video",    5,  100),
    ("text-to-video",     5,  100),
    ("animatediff",       3,   50),
    ("comfyui",           3,   50),
]

def fetch_huggingface_models(seen: set) -> list[dict]:
    entries = []
    cutoff = cutoff_dt()

    for tag, min_likes, min_dl in HF_SEARCHES:
        print(f"    tag: '{tag}'")
        data = safe_get_json(
            "https://huggingface.co/api/models",
            params={
                "filter": tag,
                "sort": "lastModified",
                "direction": -1,
                "limit": 20,
                "full": "true",
            }
        )
        if not data:
            time.sleep(1)
            continue

        for model in data:
            model_id  = model.get("modelId") or model.get("id", "")
            url       = f"https://huggingface.co/{model_id}"
            if url in seen:
                continue

            # Filtro fecha
            dt = parse_iso(model.get("lastModified", ""))
            if not dt or dt < cutoff:
                continue

            # Filtro nombre trivial
            if is_trivial_name(model_id):
                continue

            downloads = model.get("downloads", 0)
            likes     = model.get("likes", 0)

            # Filtro tracción: likes O descargas suficientes
            if likes < min_likes and downloads < min_dl:
                continue

            tags_model = model.get("tags", [])
            tags_str   = " ".join(tags_model)
            text_check = f"{model_id} {tags_str}"

            # Filtro relevancia
            if not is_relevant(text_check):
                continue

            pipeline = model.get("pipeline_tag", "")
            short_name = model_id.split("/")[-1]

            entries.append({
                "title": short_name,
                "url": url,
                "que_es": f"Modelo en HuggingFace: {model_id}. Pipeline: {pipeline}.",
                "para_que": f"Modelo para pipelines de difusión/vídeo. ⬇ {downloads} descargas · ❤ {likes} likes.",
                "requisitos": "Descargar desde HuggingFace. Ver ficha del modelo.",
                "cambios": f"Tags: {', '.join(tags_model[:8])}" if tags_model else "Modelo nuevo.",
                "_source": "HuggingFace",
                "_ecosystem_hint": guess_ecosystem_hint(f"{model_id} {tags_str}"),
                "_traction": downloads,
            })
            seen.add(url)

        time.sleep(0.5)

    return entries


# ----------------------------
# FUENTE 4: RSS de vendors
# ----------------------------
RSS_FEEDS = [
    ("Black Forest Labs",  "https://blackforestlabs.ai/feed/"),
    ("Stability AI",       "https://stability.ai/feed"),
    ("HuggingFace Blog",   "https://huggingface.co/blog/feed.xml"),
    ("Qwen Blog",          "https://qwenlm.github.io/feed.xml"),
    ("ComfyUI Blog",       "https://blog.comfy.org/feed"),
]

def parse_rss_date(s: str) -> datetime | None:
    if not s:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except:
            continue
    return None

def fetch_rss_feeds(seen: set) -> list[dict]:
    entries = []
    cutoff  = cutoff_dt()

    for name, feed_url in RSS_FEEDS:
        print(f"    feed: {name}")
        text = safe_get_text(feed_url)
        if not text:
            continue

        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            print(f"    ⚠  Parse error {name}: {e}")
            continue

        ns    = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items:
            # RSS 2.0
            link        = item.findtext("link", "").strip()
            title       = item.findtext("title", "").strip()
            pub_date    = item.findtext("pubDate") or item.findtext("pubdate", "")
            description = item.findtext("description") or ""

            # Atom fallback
            if not link:
                link_el = item.find("atom:link", ns)
                if link_el is not None:
                    link = link_el.get("href", "").strip()
            if not pub_date:
                pub_date = (item.findtext("atom:updated", "", ns) or
                            item.findtext("atom:published", "", ns))
            if not description:
                description = item.findtext("atom:summary", "", ns) or ""

            if not link or link in seen:
                continue

            # Filtro fecha
            dt = parse_rss_date(pub_date)
            if dt and dt < cutoff:
                continue

            # Filtro relevancia
            if not is_relevant(f"{title} {description}"):
                continue

            desc_clean = re.sub(r"<[^>]+>", "", description)[:250].strip()

            entries.append({
                "title": title,
                "url": link,
                "que_es": f"Artículo de blog: {name}.",
                "para_que": desc_clean or f"Novedad publicada en {name}.",
                "requisitos": "N/A — artículo informativo.",
                "cambios": f"Publicado en {name}.",
                "_source": "Blog",
                "_ecosystem_hint": guess_ecosystem_hint(f"{title} {description}"),
                "_traction": 0,
            })
            seen.add(link)

    return entries


# ----------------------------
# FUENTE 5: Civitai — LoRAs nuevas (filtro estricto)
# ----------------------------
# Ecosistemas de interés — solo estos base models
CIVITAI_BASE_MODELS = {"Flux.1 S", "Flux.1 D", "SDXL 1.0", "Wan Video", "Illustrious"}
MIN_CIVITAI_DOWNLOADS = 200
MIN_CIVITAI_RATING    = 4.0  # sobre 5

def fetch_civitai_loras(seen: set) -> list[dict]:
    entries = []
    cutoff  = cutoff_dt()
    print(f"    endpoint: civitai.com/api/v1/models?types=LORA")

    params = {
        "types":   "LORA",
        "sort":    "Newest",
        "period":  "Week",
        "limit":   50,
        "nsfw":    "false",
    }

    data = safe_get_json(
        "https://civitai.com/api/v1/models",
        params=params,
        timeout=20,
    )
    if not data:
        return entries

    for model in data.get("items", []):
        url = f"https://civitai.com/models/{model.get('id', '')}"
        if url in seen:
            continue

        # Filtro fecha (usando la versión más reciente)
        versions = model.get("modelVersions", [])
        if not versions:
            continue
        latest = versions[0]
        created_at = latest.get("createdAt", "")
        dt = parse_iso(created_at)
        if not dt or dt < cutoff:
            continue

        # Filtro base model
        base_model = latest.get("baseModel", "")
        if base_model not in CIVITAI_BASE_MODELS:
            continue

        # Filtro tracción
        stats = model.get("stats", {})
        downloads = stats.get("downloadCount", 0)
        rating    = stats.get("rating", 0)
        if downloads < MIN_CIVITAI_DOWNLOADS and rating < MIN_CIVITAI_RATING:
            continue

        name        = model.get("name", "")
        description = (model.get("description") or "")
        # Limpiar HTML básico de la descripción
        description = re.sub(r"<[^>]+>", "", description)[:250].strip()

        # Filtro relevancia por nombre
        if is_trivial_name(name):
            continue

        tags     = [t.get("name", "") for t in model.get("tags", [])]
        tags_str = ", ".join(tags[:6])

        entries.append({
            "title":    name,
            "url":      url,
            "que_es":   f"LoRA en Civitai. Base model: {base_model}.",
            "para_que": description or f"LoRA para {base_model}. ⬇ {downloads} descargas · ⭐ {rating}/5.",
            "requisitos": f"Descargar desde Civitai. Compatible con {base_model}.",
            "cambios":  f"Tags: {tags_str}" if tags_str else f"Nueva LoRA. ⬇ {downloads} descargas.",
            "_source": "Civitai",
            "_ecosystem_hint": guess_ecosystem_hint(f"{name} {base_model} {tags_str}"),
            "_traction": downloads,
        })
        seen.add(url)

    return entries


# ----------------------------
# FUENTE 6: OpenModelDB — modelos nuevos vía GitHub commits
# Monitoriza el repo OpenModelDB/open-model-database y extrae
# los modelos añadidos recientemente desde los archivos JSON del repo.
# ----------------------------
def fetch_openmodeldb(seen: set) -> list[dict]:
    entries = []
    cutoff  = cutoff_dt()
    print(f"    endpoint: OpenModelDB/open-model-database commits")

    # Obtener commits recientes del repo
    commits = safe_get_json(
        "https://api.github.com/repos/OpenModelDB/open-model-database/commits",
        headers=github_headers(),
        params={"per_page": 20},
    )
    if not commits:
        return entries

    # Filtrar commits recientes
    recent_commits = []
    for commit in commits:
        date_str = commit.get("commit", {}).get("committer", {}).get("date", "")
        dt = parse_iso(date_str)
        if dt and dt >= cutoff:
            recent_commits.append(commit)

    if not recent_commits:
        print("    → Sin commits recientes en OpenModelDB")
        return entries

    # Para cada commit reciente, obtener los archivos modificados
    for commit in recent_commits[:5]:  # máx 5 commits para no abusar de la API
        sha = commit.get("sha", "")
        commit_data = safe_get_json(
            f"https://api.github.com/repos/OpenModelDB/open-model-database/commits/{sha}",
            headers=github_headers(),
        )
        if not commit_data:
            continue

        files = commit_data.get("files", [])
        for f in files:
            filename = f.get("filename", "")
            # Solo modelos nuevos (archivos en data/models/)
            if not filename.startswith("data/models/") or not filename.endswith(".json"):
                continue
            if f.get("status") not in ("added", "modified"):
                continue

            # Extraer ID del modelo del path
            model_id = filename.replace("data/models/", "").replace(".json", "")
            url = f"https://openmodeldb.info/models/{model_id}"
            if url in seen:
                continue

            # Intentar leer el JSON del modelo para obtener detalles
            raw_url = f"https://raw.githubusercontent.com/OpenModelDB/open-model-database/main/{filename}"
            model_json = safe_get_json(raw_url)

            if model_json:
                name        = model_json.get("name", model_id)
                description = (model_json.get("description") or "")[:250].strip()
                tags        = model_json.get("tags", [])
                scale       = model_json.get("scale", "")
                arch        = model_json.get("architecture", "")
                tags_str    = ", ".join(tags[:6]) if tags else ""
                scale_str   = f"{scale}x" if scale else ""
            else:
                name        = model_id
                description = ""
                tags_str    = ""
                scale_str   = ""
                arch        = ""

            entries.append({
                "title":    f"{name} ({scale_str} {arch})".strip(" ()"),
                "url":      url,
                "que_es":   f"Modelo de upscaling en OpenModelDB. Arquitectura: {arch or 'N/A'}. Escala: {scale_str or 'N/A'}.",
                "para_que": description or f"Modelo de upscaling/restauración. Tags: {tags_str}.",
                "requisitos": "Descargar desde OpenModelDB. Compatible con chaiNNer, ComfyUI upscaler.",
                "cambios":  f"Añadido recientemente. Tags: {tags_str}" if tags_str else "Modelo nuevo en OpenModelDB.",
                "_source": "OpenModelDB",
                "_ecosystem_hint": "ComfyUI",
                "_traction": 0,
            })
            seen.add(url)
            time.sleep(0.3)

    return entries

# ----------------------------
# Awesome ComfyUI (lista curada)
# ----------------------------
AWESOME_COMFYUI_URL = "https://raw.githubusercontent.com/ComfyUI-Workflow/awesome-comfyui/main/README.md"

def fetch_awesome_comfyui(seen: set) -> list[dict]:
    """
    Parsea el README de awesome-comfyui y extrae:
      - New Workflows    -> nodes añadidos recientemente al ComfyUI Manager
      - Trending Workflows -> nodes con mayor ganancia de stars (con delta visible)

    No usa API ni ventana de fechas: la lista ya viene filtrada y curada diariamente.
    Se protege contra duplicados via seen (URL del repo GitHub de cada node).
    """
    entries = []
    print(f"    endpoint: {AWESOME_COMFYUI_URL}")

    text = safe_get_text(AWESOME_COMFYUI_URL)
    if not text:
        return entries

    # Dividir README en secciones por cabeceras ##
    sections = {}
    current_section = None
    for line in text.splitlines():
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections[current_section] = []
        elif current_section is not None:
            sections[current_section].append(line)

    # Regex para entradas de lista markdown:
    # * [**Nombre**](url): descripcion
    # * [**Nombre**](url) (stars+NNN): descripcion
    ENTRY_RE = re.compile(
        r'^\*\s+\[[\*_]*([^\]]+?)[\*_]*\]\((https://github\.com/[^\)]+)\)'
        r'(?:\s+\(â­\+(\d+)\))?'
        r'(?::\s+(.+))?$'
    )

    def parse_section(section_name: str, source_tag: str, traction_base: int) -> list[dict]:
        result = []
        lines = sections.get(section_name, [])
        for line in lines:
            m = ENTRY_RE.match(line.strip())
            if not m:
                continue
            name        = m.group(1).strip()
            url         = m.group(2).strip()
            stars_delta = int(m.group(3)) if m.group(3) else 0
            description = (m.group(4) or "").strip()

            # Limpiar emojis del nombre
            name = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27BF\s]+', ' ', name).strip()

            if not name or url in seen:
                continue

            traction = traction_base + stars_delta
            que_es   = description if description else f"Custom node para ComfyUI: {name}."
            para_que = description if description else "Extiende las capacidades de ComfyUI. Ver repositorio para detalles."

            result.append({
                "title":      name,
                "url":        url,
                "que_es":     que_es[:400],
                "para_que":   para_que[:400],
                "requisitos": "Instalar via ComfyUI Manager.",
                "cambios":    f"Aparece en '{source_tag}' de awesome-comfyui." +
                              (f" Delta stars reciente: +{stars_delta}." if stars_delta else ""),
                "_source":    "AwesomeComfyUI",
                "_ecosystem_hint": "ComfyUI",
                "_traction":  traction,
            })
            seen.add(url)

        return result

    new_entries      = parse_section("New Workflows",      "New Workflows", traction_base=0)
    trending_entries = parse_section("Trending Workflows", "Trending",      traction_base=50)

    print(f"    -> {len(new_entries)} nodes nuevos en el Manager")
    print(f"    -> {len(trending_entries)} nodes trending por stars")
    entries.extend(new_entries)
    entries.extend(trending_entries)
    return entries



# ----------------------------
# Main
# ----------------------------
def main():
    print(f"\n{'='*55}")
    print(f"  GenAI Radar — Monitor de fuentes v4")
    print(f"  Ventana: últimos {LOOKBACK_DAYS} días")
    print(f"{'='*55}\n")

    seen = load_seen()
    all_entries = []

    print("📡 GitHub — repos nuevos")
    gh_repos = fetch_github_repos(seen)
    print(f"   → {len(gh_repos)} entradas")
    all_entries.extend(gh_repos)

    print("\n📡 GitHub — releases/commits de repos clave")
    gh_releases = fetch_github_releases(seen)
    print(f"   → {len(gh_releases)} entradas")
    all_entries.extend(gh_releases)

    print("\n📡 HuggingFace — modelos nuevos")
    hf_models = fetch_huggingface_models(seen)
    print(f"   → {len(hf_models)} entradas")
    all_entries.extend(hf_models)

    print("\n📡 RSS — blogs de vendors")
    rss_entries = fetch_rss_feeds(seen)
    print(f"   → {len(rss_entries)} entradas")
    all_entries.extend(rss_entries)

    print("\n📡 Civitai — LoRAs nuevas (Flux · SDXL · Wan)")
    civitai_entries = fetch_civitai_loras(seen)
    print(f"   → {len(civitai_entries)} entradas")
    all_entries.extend(civitai_entries)

    print("\n📡 OpenModelDB — modelos de upscaling nuevos")
    omdb_entries = fetch_openmodeldb(seen)
    print(f"   → {len(omdb_entries)} entradas")
    all_entries.extend(omdb_entries)

    print("\n📡 Awesome ComfyUI — nodes nuevos y trending")
    awesome_entries = fetch_awesome_comfyui(seen)
    print(f"   → {len(awesome_entries)} entradas")
    all_entries.extend(awesome_entries)

    save_seen(seen)

    if not all_entries:
        print("\n✅ No hay novedades nuevas desde la última ejecución.")
        print("   Tip: borra state/monitor_seen.json para forzar re-escaneo.\n")
        return

    # Deduplicar por URL
    seen_urls = set()
    url_deduped = []
    for e in all_entries:
        if e["url"] not in seen_urls:
            seen_urls.add(e["url"])
            url_deduped.append(e)

    # Anti-duplicados cross-fuente (título normalizado)
    _NORM_TITLES_SEEN.clear()
    unique = []
    cross_skipped = 0
    for e in url_deduped:
        if is_cross_duplicate(e["title"]):
            cross_skipped += 1
            print(f"  Cross-dup saltado: {e['title'][:70]}")
        else:
            unique.append(e)

    if cross_skipped:
        print(f"   → {cross_skipped} entradas eliminadas por duplicado cross-fuente")

    # Scoring y ordenación por relevancia
    for e in unique:
        e["_score"] = score_entry(e)
    unique.sort(key=lambda e: e["_score"], reverse=True)

    # Escribir digest
    lines = [
        format_entry(i+1, e["title"], e["url"], e["que_es"],
                     e["para_que"], e["requisitos"], e["cambios"],
                     score=e["_score"])
        for i, e in enumerate(unique)
    ]
    DIGEST_FILE.write_text("\n".join(lines).strip(), encoding="utf-8")

    print(f"\n{'='*55}")
    print(f"  ✅ Digest generado: {len(unique)} entradas")
    print(f"  → {DIGEST_FILE}")
    print(f"{'='*55}")
    print("\nPróximos pasos:")
    print("  1. Arrastra digest_raw.txt a Claude para clasificar")
    print("  2. Descarga el digest.txt que te entregue Claude")
    print("  3. Ejecuta importar_digest.bat\n")


if __name__ == "__main__":
    main()
