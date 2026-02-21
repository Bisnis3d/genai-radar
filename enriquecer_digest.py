"""
enriquecer_digest.py
--------------------
Revisa interactivamente el digest_raw.txt generado por monitor_sources.py
y construye el digest.txt final listo para importar a Notion.

Flujo de uso:
  1. Ejecuta monitor_radar.bat  →  genera digest_raw.txt
  2. Ejecuta este script        →  revisa entrada a entrada
  3. Ejecuta importar_digest.bat →  importa digest.txt a Notion

Controles por entrada:
  [A] Aceptar    — pasa al digest.txt tal cual
  [E] Editar     — abre en el editor del sistema, luego pasa
  [D] Descartar  — descarta sin guardar
  [S] Salir      — guarda lo aceptado hasta ahora y termina
"""

import os
import re
import sys
import tempfile
import subprocess
from pathlib import Path

# ----------------------------
# Rutas
# ----------------------------
BASE_DIR    = Path(__file__).resolve().parent
RAW_FILE    = BASE_DIR / "digest_raw.txt"
IMPORT_FILE = BASE_DIR / "digest.txt"

EDITOR = os.environ.get("EDITOR", "notepad" if sys.platform == "win32" else "nano")


# ----------------------------
# Colores ANSI
# ----------------------------
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"
    WHITE  = "\033[97m"

def enable_ansi_windows():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            pass

enable_ansi_windows()


# ----------------------------
# Parser
# ----------------------------
BLOCK_SEP = re.compile(r"^\s*#\s*\d+\)", re.MULTILINE)

def parse_blocks(text: str) -> list:
    positions = [m.start() for m in BLOCK_SEP.finditer(text)]
    if not positions:
        return []
    blocks = []
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks

def extract_title(block: str) -> str:
    first_line = block.split("\n")[0]
    return re.sub(r"^#\s*\d+\)\s*", "", first_line).strip()

def extract_field(block: str, field: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(field)}:\s*(.+?)(?=\n[A-ZÁÉÍÓÚÑa-z\w ]+:|$)",
        re.MULTILINE | re.DOTALL
    )
    m = pattern.search(block)
    return m.group(1).strip() if m else ""

def renumber_blocks(blocks: list, offset: int = 0) -> list:
    renumbered = []
    for i, block in enumerate(blocks, offset + 1):
        block = re.sub(r"^#\s*\d+\)", f"# {i})", block)
        renumbered.append(block)
    return renumbered


# ----------------------------
# Editor externo
# ----------------------------
def open_in_editor(block: str) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(block)
        tmp_path = f.name
    try:
        if sys.platform == "win32":
            subprocess.run(["start", "/wait", EDITOR, tmp_path], shell=True)
        else:
            subprocess.run([EDITOR, tmp_path])
    except Exception as e:
        print(f"{C.RED}No se pudo abrir el editor: {e}{C.RESET}")
        return block
    edited = Path(tmp_path).read_text(encoding="utf-8")
    Path(tmp_path).unlink(missing_ok=True)
    return edited.strip()


# ----------------------------
# Display
# ----------------------------
SEP = C.GRAY + "─" * 68 + C.RESET

def print_block(block: str, index: int, total: int):
    title   = extract_title(block)
    url     = extract_field(block, "URL")
    que_es  = extract_field(block, "Qué es")
    sirve   = extract_field(block, "Para qué sirve")
    req     = extract_field(block, "Requisitos")
    cambios = extract_field(block, "Cambios importantes")

    def trunc(s, n=110):
        return s[:n] + "..." if len(s) > n else s

    print(f"\n{SEP}")
    print(f"  {C.CYAN}{C.BOLD}[{index}/{total}]{C.RESET}  {C.WHITE}{C.BOLD}{title}{C.RESET}")
    print(SEP)
    if url:
        print(f"  {C.GRAY}URL:{C.RESET}             {C.YELLOW}{url}{C.RESET}")
    if que_es:
        print(f"  {C.GRAY}Qué es:{C.RESET}          {trunc(que_es)}")
    if sirve:
        print(f"  {C.GRAY}Para qué sirve:{C.RESET}  {trunc(sirve)}")
    if req:
        print(f"  {C.GRAY}Requisitos:{C.RESET}      {trunc(req, 90)}")
    if cambios:
        print(f"  {C.GRAY}Cambios:{C.RESET}         {trunc(cambios)}")
    print()

def print_prompt():
    print(
        f"  {C.GREEN}[A]{C.RESET} Aceptar   "
        f"{C.YELLOW}[E]{C.RESET} Editar   "
        f"{C.RED}[D]{C.RESET} Descartar   "
        f"{C.GRAY}[S]{C.RESET} Salir"
    )
    print(f"  {C.BOLD}> {C.RESET}", end="", flush=True)

def print_summary(accepted, edited, discarded, total):
    print(f"\n{SEP}")
    print(f"  {C.BOLD}Sesión completada{C.RESET}")
    print(f"  {C.GREEN}✓ Aceptadas:{C.RESET}   {accepted}")
    print(f"  {C.YELLOW}✎ Editadas:{C.RESET}    {edited}")
    print(f"  {C.RED}✗ Descartadas:{C.RESET} {discarded}")
    print(f"  {C.GRAY}Total revisadas: {accepted + edited + discarded} / {total}{C.RESET}")
    print(f"{SEP}\n")


# ----------------------------
# Main
# ----------------------------
def main():
    print(f"\n{C.BOLD}{C.CYAN}  GenAI Radar — Revisor de digest{C.RESET}")
    print(f"  {C.GRAY}{RAW_FILE.name}  →  {IMPORT_FILE.name}{C.RESET}\n")

    if not RAW_FILE.exists():
        print(f"{C.RED}ERROR: No se encontró {RAW_FILE.name}{C.RESET}")
        print(f"  Ejecuta primero {C.YELLOW}monitor_radar.bat{C.RESET} para generarlo.")
        sys.exit(1)

    raw_text = RAW_FILE.read_text(encoding="utf-8")
    blocks = parse_blocks(raw_text)

    if not blocks:
        print(f"{C.YELLOW}digest_raw.txt está vacío o sin entradas válidas.{C.RESET}")
        sys.exit(0)

    total = len(blocks)
    print(f"  {C.WHITE}{total} entradas encontradas{C.RESET}")

    # ¿Añadir o sobreescribir digest.txt existente?
    mode = "w"
    existing_count = 0
    if IMPORT_FILE.exists():
        existing_blocks = parse_blocks(IMPORT_FILE.read_text(encoding="utf-8"))
        existing_count = len(existing_blocks)
        if existing_count:
            print(f"\n  {C.YELLOW}digest.txt ya contiene {existing_count} entradas.{C.RESET}")
            print(f"  {C.GREEN}[A]{C.RESET} Añadir al final   {C.RED}[S]{C.RESET} Sobreescribir   {C.GRAY}[C]{C.RESET} Cancelar")
            print(f"  {C.BOLD}> {C.RESET}", end="", flush=True)
            try:
                choice = input().strip().upper()
            except (KeyboardInterrupt, EOFError):
                sys.exit(0)
            if choice == "C" or choice == "":
                print("Cancelado.")
                sys.exit(0)
            elif choice == "A":
                mode = "a"
            else:
                mode = "w"
                existing_count = 0

    accepted_blocks = []
    stats = {"accepted": 0, "edited": 0, "discarded": 0}

    for i, block in enumerate(blocks, 1):
        print_block(block, i, total)
        print_prompt()

        try:
            choice = input().strip().upper()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.GRAY}Interrumpido.{C.RESET}")
            break

        if choice == "A":
            accepted_blocks.append(block)
            stats["accepted"] += 1
            print(f"  {C.GREEN}✓ Aceptada{C.RESET}")

        elif choice == "E":
            print(f"  {C.YELLOW}Abriendo editor...{C.RESET}")
            edited_block = open_in_editor(block)
            accepted_blocks.append(edited_block)
            stats["edited"] += 1
            print(f"  {C.YELLOW}✎ Editada y aceptada{C.RESET}")

        elif choice == "S":
            print(f"  {C.GRAY}Saliendo...{C.RESET}")
            break

        else:
            stats["discarded"] += 1
            print(f"  {C.RED}✗ Descartada{C.RESET}")

    # Guardar
    total_saved = stats["accepted"] + stats["edited"]
    if accepted_blocks:
        renumbered = renumber_blocks(accepted_blocks, offset=existing_count)
        output_text = "\n\n".join(renumbered) + "\n"

        with open(IMPORT_FILE, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n\n" + output_text)
            else:
                f.write(output_text)

        print(f"\n  {C.GREEN}✓ {total_saved} entradas guardadas en {IMPORT_FILE.name}{C.RESET}")
    else:
        print(f"\n  {C.GRAY}No se guardaron entradas.{C.RESET}")

    print_summary(stats["accepted"], stats["edited"], stats["discarded"], total)

    if total_saved:
        print(f"  Siguiente paso: {C.YELLOW}importar_digest.bat{C.RESET}\n")


if __name__ == "__main__":
    main()
