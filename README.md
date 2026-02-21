# GenAI Radar

**Sistema local de monitorización del ecosistema GenAI → Notion**

Detecta automáticamente novedades en modelos, herramientas y recursos de ComfyUI, Flux, Wan, SDXL y el ecosistema GenAI en general. Genera un digest clasificado e importa los resultados directamente a una base de datos Notion organizada.

![cover](docs/cover_recent.png)

---

## ¿Qué hace?

1. **Monitoriza 7 fuentes** del ecosistema GenAI en busca de novedades
2. **Puntúa y ordena** cada entrada por relevancia (scoring 0–100)
3. **Genera un digest** estructurado listo para revisar
4. **Importa a Notion** con categoría, ecosistema, fuente y prioridad automáticos
5. **Evita duplicados** mediante un sistema de estado en 3 capas
6. **Genera un dashboard HTML** con estadísticas locales sin dependencias

---

## Fuentes monitorizadas

| Fuente | Qué detecta |
|--------|-------------|
| GitHub API | Repos nuevos por query + releases de 26 repos clave |
| HuggingFace API | Modelos nuevos por tags (filtro likes + descargas) |
| RSS Vendors | Blogs de Stability AI, Black Forest Labs, Comfy Org... |
| Civitai API | LoRAs nuevas: Flux · SDXL · Wan · Illustrious |
| OpenModelDB | Modelos de upscaling vía commits del repo GitHub |
| Awesome ComfyUI | Lista curada: nuevos nodes + trending por delta de stars |

---

## Estructura del repositorio

```
genai-radar/
├── monitor_sources.py        # Monitor de fuentes (genera digest_raw.txt)
├── import_digest_to_notion.py # Importador a Notion
├── generar_dashboard.py      # Dashboard HTML local
├── cleanup.py                # Limpia entradas marcadas como Delete en Notion
├── enriquecer_digest.py      # Enriquece digest_raw con clasificación manual
│
├── digest.txt                # Digest activo (el que importa el sistema)
├── digest_ejemplo.txt        # Ejemplo con 5 entradas reales
│
├── monitor_radar.bat         # Ejecutar monitor → genera digest_raw.txt
├── editar_e_importar.bat     # Editar digest.txt + importar a Notion
├── importar_digest.bat       # Importar directamente (sin editar)
├── dashboard.bat             # Generar dashboard HTML local
│
├── .env.example              # Plantilla de variables de entorno
├── requirements.txt          # Dependencias Python
│
├── state/                    # Estado anti-duplicados (auto-generado)
│   ├── monitor_seen.json
│   ├── import_log_global.json
│   └── import_log_YYYYMMDD.json
│
└── archive/                  # Historial de digests importados (auto-generado)
```

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tuusuario/genai-radar.git
cd genai-radar
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configurar credenciales

Copia el archivo de ejemplo y rellena tus credenciales:

```bash
cp .env.example .env
```

Edita `.env`:

```env
# Token de GitHub (necesario para el monitor de fuentes)
# Genera uno en: https://github.com/settings/tokens
GITHUB_TOKEN=github_pat_...

# Token de integración de Notion
# Genera uno en: https://www.notion.so/my-integrations
NOTION_TOKEN=secret_...

# ID de tu base de datos GenAI Radar en Notion
# Lo encontrarás en la URL de la base de datos
NOTION_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4. Crear la base de datos en Notion

La base de datos debe tener este schema exacto:

| Campo | Tipo | Valores |
|-------|------|---------|
| Name | Title | — |
| Category | Select | Generación · Control · Motion · LoRA / Adapter · Postproceso · Workflow / Node · Tooling · Conocimiento |
| Ecosystem | Select | Flux · Wan · Qwen · SDXL · SD 1.5 · ComfyUI · Multi |
| Source | Select | GitHub · HuggingFace · Vendor · Blog · Docs · Civitai |
| Status | Select | To review · Watchlist · Tested · Archived · Delete |
| Priority | Select | Low · Medium · High · Strategic |
| URL | URL | — |
| Summary | Text | — |
| Use case | Text | — |
| Requirements | Text | — |
| Impact | Text | — |
| Date | Date | — |
| Signal | Checkbox | — |

Después **comparte la base de datos con tu integración** de Notion (botón "Connect to" en la esquina superior derecha de la base de datos).

---

## Uso diario

### Paso 1 — Detectar novedades

```bash
monitor_radar.bat   # Windows
# o directamente:
python monitor_sources.py
```

Genera `digest_raw.txt` con las novedades encontradas ordenadas por score.

### Paso 2 — Revisar y clasificar

Abre `digest_raw.txt`, revisa las entradas y mueve al `digest.txt` las que quieras importar. Puedes ajustar manualmente el título, categoría o cualquier campo.

### Paso 3 — Importar a Notion

```bash
importar_digest.bat   # Importa directamente
# o:
editar_e_importar.bat # Abre el editor primero, luego importa
```

### Paso 4 — Dashboard (opcional)

```bash
dashboard.bat
# o:
python generar_dashboard.py
```

Abre `dashboard.html` en el navegador con estadísticas de tu base de datos.

---

## Formato del digest

Cada entrada en `digest.txt` sigue este formato:

```
# Título de la entrada
URL: https://...
Qué es: Descripción breve del recurso.
Para qué sirve: Casos de uso principales.
Requisitos: Hardware, modelos o dependencias necesarias.
Cambios importantes: Novedades respecto a versiones anteriores.
```

Consulta `digest_ejemplo.txt` para ver 5 entradas reales completas.

---

## Sistema de scoring

Cada entrada detectada por el monitor recibe una puntuación 0–100:

| Criterio | Peso | Descripción |
|----------|------|-------------|
| Fuente | 0–30 | GitHub oficial > HuggingFace > Vendors > Civitai |
| Keywords | 0–30 | Presencia de términos clave del ecosistema |
| Ecosistema | 0–20 | Flux · Wan · Qwen tienen mayor peso actualmente |
| Tracción | 0–20 | Stars, likes, descargas, delta de trending |

---

## Requisitos

- Python 3.10+
- Windows (los `.bat` son para Windows; en macOS/Linux ejecuta los `.py` directamente)
- Cuenta de Notion con integración propia
- Token de GitHub (gratuito, solo lectura)

---

## Licencia

MIT — úsalo, modifícalo y compártelo libremente.

---

## Contribuciones

Pull requests bienvenidos. Las áreas más útiles para contribuir:

- Nuevas fuentes de monitorización
- Mejoras en las heurísticas de categorización
- Soporte para otros gestores de conocimiento (Obsidian, Airtable...)
- Scripts de instalación para macOS/Linux
