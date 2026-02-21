"""
cleanup.py
----------
Archiva (mueve a papelera) todos los registros de GenAI Radar
cuyo campo Status = "Delete".

Flags opcionales:
  --dry-run  Muestra qué borraría sin aplicar cambios

Uso:
  python cleanup.py
  python cleanup.py --dry-run
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_ID        = os.getenv("NOTION_DB_ID")

if not NOTION_TOKEN or not DB_ID:
    raise SystemExit("Faltan variables de entorno: NOTION_TOKEN y/o NOTION_DB_ID")

HEADERS = {
    "Authorization":  f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type":   "application/json",
}

DRY_RUN = "--dry-run" in sys.argv

if DRY_RUN:
    print("⚠  Modo DRY-RUN: no se aplicarán cambios.\n")


def get_delete_pages() -> list:
    """Devuelve todos los registros con Status = Delete."""
    pages  = []
    cursor = None
    while True:
        body = {
            "page_size": 100,
            "filter": {
                "property": "Status",
                "select": {"equals": "Delete"}
            }
        }
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/databases/{DB_ID}/query",
            headers=HEADERS,
            json=body,
        ).json()
        pages.extend(r.get("results", []))
        if not r.get("has_more"):
            break
        cursor = r["next_cursor"]
    return pages


def archive_page(page_id: str):
    r = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=HEADERS,
        json={"archived": True},
    )
    r.raise_for_status()


def main():
    print("Buscando entradas marcadas como Delete...")
    pages = get_delete_pages()

    if not pages:
        print("✅ No hay entradas para eliminar.\n")
        return

    print(f"Encontradas: {len(pages)} entradas\n")

    deleted = 0
    errors  = 0

    for page in pages:
        page_id     = page["id"]
        title_parts = page["properties"].get("Name", {}).get("title", [])
        title       = title_parts[0]["plain_text"] if title_parts else "(sin título)"

        if DRY_RUN:
            print(f"  [DRY] Archivaría: {title[:80]}")
        else:
            try:
                archive_page(page_id)
                deleted += 1
                print(f"  🗑  Archivado: {title[:80]}")
            except Exception as e:
                errors += 1
                print(f"  ❌ Error en '{title[:80]}': {e}")

    if not DRY_RUN:
        print(f"""
--- Resumen cleanup ---
Archivados: {deleted}
Errores:    {errors}
""")


if __name__ == "__main__":
    main()
