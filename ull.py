#!/usr/bin/env python3
"""
ull.py — espeja el calendario OFICIAL de exámenes de la ESIT (ULL) en un
calendario propio, aparte del de estudio.

    ull sync        baja los .docx, regenera out/uni-ull.ics y avisa si cambió
    ull ver         enseña por terminal los exámenes que detecta
    ull diff        solo dice si hay cambios respecto a la última vez

La ESIT no publica un .ics: cuelga un puñado de .docx en una carpeta pública
de Google Drive, uno por mes de exámenes (enero, marzo, mayo, junio, julio).
Cada uno lleva UNA tabla con la misma cabecera:

    Día | Fecha | Curso | C | Asignatura | Hora | Aula | Observaciones

«C» NO es la convocatoria: es el CUATRIMESTRE al que pertenece la asignatura
(C1 = las del primer cuatrimestre, C2 = las del segundo). La convocatoria la
marca el MES del fichero. Las celdas «Día» y «Fecha» solo se rellenan en la
primera fila de cada jornada, así que hay que arrastrarlas hacia abajo.

Esto es un ESPEJO DE SOLO LECTURA: no escribe notas en Exámenes/ ni toca el
calendario de estudio. Si quieres plan de estudio para un examen, lo das de
alta tú (Ctrl+Shift+Ñ) y uni.py hace su trabajo como siempre.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import uni

BASE = Path(__file__).resolve().parent
SALIDA = BASE / "out" / "uni-ull.ics"

# Carpeta pública de Drive enlazada desde «Horarios y Calendario Exámenes» de
# la ESIT. Si la ESIT la cambia de sitio, se sobreescribe sin tocar el código:
#   UNI_ULL_CARPETA=<id> ull sync
CARPETA = os.environ.get(
    "UNI_ULL_CARPETA", "1HvtgGFGCO-aGBCucm4zr3Es3xlFgcCa5")
PAGINA = ("https://www.ull.es/grados/ingenieria-electronica-industrial-"
          "automatica/informacion-academica/horarios-y-calendario-examenes/")

# Solo interesa tu curso. Se cambia sin tocar el código: UNI_ULL_CURSO=3
CURSO = os.environ.get("UNI_ULL_CURSO", "2")

# El estado es de la máquina, no del vault: no se sincroniza con Drive ni con
# git. Sirve para saber QUÉ cambió desde la última vez.
ESTADO = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) \
    / "uni" / "ull-examenes.json"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RE_FECHA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
DURACION_DEF = 120          # la ESIT no publica duración; 2 h es lo típico
AVISO_MIN = 120

# La ESIT escribe las asignaturas EN MAYÚSCULAS. str.title() las destroza en
# castellano ("Mecánica De Máquinas", "Automatización Y Control"): las
# partículas van en minúscula salvo al principio.
MINUSCULAS = {"y", "e", "o", "u", "de", "del", "la", "las", "el", "los",
              "en", "a", "al", "con", "por", "para"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def bonito(texto):
    """'AUTOMATIZACIÓN Y CONTROL' → 'Automatización y Control'."""
    palabras = texto.lower().split()
    return " ".join(p if i and p in MINUSCULAS else p.capitalize()
                    for i, p in enumerate(palabras))


# ─────────────────────────── descarga ──────────────────────────────

def descargar(destino):
    """Copia los .docx de la carpeta pública con el rclone ya configurado."""
    remoto = os.environ.get("UNI_DRIVE_REMOTO", "drive")
    r = subprocess.run(
        ["rclone", "copy", "--drive-root-folder-id", CARPETA,
         f"{remoto}:", str(destino), "--include", "*.docx"],
        capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"rclone falló: {r.stderr.strip() or r.stdout.strip()}")
    docs = sorted(destino.glob("*.docx"))
    if not docs:
        raise RuntimeError(
            f"la carpeta {CARPETA} no tiene .docx. ¿La movió la ESIT?\n  {PAGINA}")
    return docs


# ─────────────────────────── parseo ────────────────────────────────

def celdas(tr):
    return [" ".join("".join(t.text or "" for t in tc.iter(W + "t")).split())
            for tc in tr.findall(W + "tc")]


def parsear(ruta):
    """[(fecha, hora, asignatura, aula, obs, cuatri)] de un .docx de la ESIT.

    Tolerante a propósito: si una fila no encaja, se salta en vez de reventar.
    Un calendario a medias es más útil que un traceback en un timer semanal.
    """
    raiz = ET.fromstring(zipfile.ZipFile(ruta).read("word/document.xml"))
    out, fecha = [], None
    for tbl in raiz.iter(W + "tbl"):
        for tr in tbl.iter(W + "tr"):
            c = celdas(tr)
            if len(c) < 7:
                continue
            m = RE_FECHA.match(c[1])
            if m:                                   # arrastra la fecha
                d, mes, a = (int(x) for x in m.groups())
                try:
                    fecha = date(a, mes, d)
                except ValueError:
                    fecha = None
            if fecha is None or c[2] != CURSO:
                continue
            if not re.match(r"^\d{1,2}:\d{2}$", c[5]):
                continue
            out.append({
                "fecha": fecha.isoformat(),
                "hora": c[5] if len(c[5]) == 5 else f"0{c[5]}",
                "asignatura": c[4].strip(),
                "aula": c[6].strip(),
                "obs": (c[7].strip() if len(c) > 7 else ""),
                "cuatri": c[3].strip(),
            })
    return out


def examenes():
    """Todos los exámenes del curso, de todos los meses, sin duplicados."""
    with tempfile.TemporaryDirectory() as tmp:
        docs = descargar(Path(tmp))
        vistos, out = set(), []
        for d in docs:
            for e in parsear(d):
                clave = (e["fecha"], e["hora"], e["asignatura"], e["obs"])
                if clave in vistos:
                    continue
                vistos.add(clave)
                out.append(e)
    return sorted(out, key=lambda e: (e["fecha"], e["hora"], e["asignatura"]))


# ──────────────────────────── ICS ──────────────────────────────────

def titulo(e):
    extra = f" ({e['obs']})" if e["obs"] else ""
    return f"📝 {bonito(e['asignatura'])}{extra}"


def construir_ics(exs):
    ls = ["BEGIN:VCALENDAR", "VERSION:2.0",
          "PRODID:-//uni//examenes oficiales ULL//ES",
          "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
          "X-WR-CALNAME:Uni — Exámenes ULL", f"X-WR-TIMEZONE:{uni.TZ}"]
    for e in exs:
        inicio = uni.utc(date.fromisoformat(e["fecha"]), e["hora"])
        cuerpo = " · ".join(x for x in (
            f"Aula: {e['aula']}" if e["aula"] else "",
            f"Cuatrimestre {e['cuatri']}" if e["cuatri"] else "",
            e["obs"], "Fuente: calendario oficial ESIT") if x)
        ls += uni.evento(uni.uid("ull", e["fecha"], e["hora"], e["asignatura"],
                                 e["obs"]),
                         inicio, DURACION_DEF, titulo(e), cuerpo, AVISO_MIN)
    ls.append("END:VCALENDAR")
    return "\r\n".join(uni.plegar(x) for x in ls) + "\r\n"


# ────────────────────────── cambios ────────────────────────────────

def leer_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def guardar_estado(exs):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(exs, ensure_ascii=False, indent=1),
                      encoding="utf-8")


def etiqueta(e):
    return (f"{date.fromisoformat(e['fecha']):%d/%m/%Y} {e['hora']} · "
            f"{bonito(e['asignatura'])}"
            + (f" ({e['obs']})" if e["obs"] else ""))


def comparar(viejo, nuevo):
    """(añadidos, quitados, movidos) — movido = misma asignatura, otra fecha."""
    def clave(e):
        return (e["fecha"], e["hora"], e["asignatura"], e["obs"])

    v, n = {clave(e): e for e in viejo}, {clave(e): e for e in nuevo}
    fuera = [v[k] for k in v.keys() - n.keys()]
    dentro = [n[k] for k in n.keys() - v.keys()]

    # Si una asignatura sale y entra con otra fecha, es un cambio de fecha, no
    # un examen nuevo: decirlo así evita el susto de «me han borrado el examen».
    movidos, resto_fuera, resto_dentro = [], [], list(dentro)
    for e in fuera:
        par = next((x for x in resto_dentro
                    if x["asignatura"] == e["asignatura"] and x["obs"] == e["obs"]),
                   None)
        if par:
            resto_dentro.remove(par)
            movidos.append((e, par))
        else:
            resto_fuera.append(e)
    return resto_dentro, resto_fuera, movidos


def resumen(nuevos, fuera, movidos):
    ls = []
    for e in nuevos:
        ls.append(f"+ NUEVO   {etiqueta(e)}")
    for e in fuera:
        ls.append(f"- QUITADO {etiqueta(e)}")
    for a, b in movidos:
        ls.append(f"~ MOVIDO  {bonito(a['asignatura'])}: "
                  f"{date.fromisoformat(a['fecha']):%d/%m} {a['hora']} → "
                  f"{date.fromisoformat(b['fecha']):%d/%m} {b['hora']}")
    return ls


# ──────────────────────────── comandos ─────────────────────────────

def cmd_sync(avisar=True):
    exs = examenes()
    nuevos, fuera, movidos = comparar(leer_estado(), exs)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(construir_ics(exs), encoding="utf-8")
    guardar_estado(exs)

    print(f"✓ {len(exs)} exámenes del curso {CURSO} · {SALIDA}")
    cambios = resumen(nuevos, fuera, movidos)
    if not cambios:
        print("· sin cambios respecto a la última comprobación")
        return 0
    print("\n".join(cambios))
    if avisar:
        subprocess.run(
            ["notify-send", "-a", "Uni", "-u", "critical",
             "📝 Cambios en el calendario de exámenes",
             "\n".join(cambios[:8])], check=False)
    return 0


def cmd_ver():
    exs = examenes()
    if not exs:
        print(f"No hay exámenes del curso {CURSO}.")
        return 0
    mes = None
    for e in exs:
        f = date.fromisoformat(e["fecha"])
        if (f.year, f.month) != mes:
            mes = (f.year, f.month)
            print(f"\n── {MESES[f.month - 1].upper()} {f.year} ──")
        print(f"  {DIAS[f.weekday()]} {f:%d/%m}  {e['hora']}  C{e['cuatri']}  "
              f"{bonito(e['asignatura']):48} {e['aula']} {e['obs']}")
    print(f"\n{len(exs)} exámenes del curso {CURSO}.")
    return 0


def cmd_diff():
    nuevos, fuera, movidos = comparar(leer_estado(), examenes())
    cambios = resumen(nuevos, fuera, movidos)
    print("\n".join(cambios) if cambios else "· sin cambios")
    return 1 if cambios else 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "sync"
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    try:
        if cmd == "sync":
            return cmd_sync(avisar="--sin-aviso" not in argv)
        if cmd == "ver":
            return cmd_ver()
        if cmd == "diff":
            return cmd_diff()
    except RuntimeError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"Orden desconocida: {cmd}. Usa sync | ver | diff.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
