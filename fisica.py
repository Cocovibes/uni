#!/usr/bin/env python3
"""
fisica.py — espeja el calendario OFICIAL de exámenes de la Sección de Física
(ULL) en un calendario propio, aparte del de estudio.

    uni fisica sync   baja el PDF, regenera out/uni-fisica.ics y dice qué cambió
    uni fisica ver    enseña por terminal los exámenes que detecta
    uni fisica diff   solo dice si hay cambios respecto a la última vez

Hermano de ull.py, que hace lo mismo para la ESIT. Van separados porque cada
centro publica su calendario de una forma distinta y no comparten ni una línea
de parseo: la ESIT cuelga .docx con una tabla de columnas fijas; Física cuelga
UN PDF con una rejilla visual por semanas.

Cómo es el PDF, que es lo que manda aquí:

    CONVOCATORIA DE ENERO 2027 (8 - 19 enero)      ← de aquí sale el AÑO
                            ENERO                   ← y de aquí el MES
     Hora   LUNES 11   Aula   Hora   MARTES 12   Aula   …   ← cabecera de semana
    9:00    F.QUIM.   11/12   9:00    TERMO      13/14  …   ← una fila por hora

`pdftotext -layout` conserva las columnas alineadas, así que la cabecera de
cada semana sirve de plantilla: dónde empieza cada «Hora» marca dónde empieza
el bloque de ese día, y el número que acompaña al nombre del día da la fecha.

EL CURSO NO SE PUEDE LEER. En el PDF, que una asignatura sea de 1º o de 2º lo
dice el COLOR de la celda, y el color no sobrevive a la extracción de texto:
el único texto es «1º Y 2º GRADUADO EN FÍSICA», que agrupa dos cursos. Por eso
esto no filtra por curso sino por TUS asignaturas: cada nota de Asignaturas/
declara con qué nombre la llama el calendario oficial,

    oficial: "M. MAT. IV"

y solo se espejan los exámenes que casen con una de esas. Sale mejor que
adivinar el curso: si te queda una asignatura de otro año, también aparece.

Es un ESPEJO DE SOLO LECTURA: no escribe notas en Exámenes/ ni toca el
calendario de estudio. Para tener plan de estudio, das el examen de alta tú
(Ctrl+Shift+Ñ) y uni.py hace su trabajo como siempre.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from datetime import date
from pathlib import Path

import uni

BASE = Path(__file__).resolve().parent
SALIDA = BASE / "out" / "uni-fisica.ics"

# El PDF enlazado desde «Horarios y Calendario Exámenes» de Física. Si la ULL
# lo cambia de sitio se sobreescribe sin tocar el código:
#   UNI_FIS_PDF=<id de Drive> uni fisica sync
PDF = os.environ.get("UNI_FIS_PDF", "1f3J_qkSfDWqEjTNko_cSah7bJlgfJx6E")
PAGINA = ("https://www.ull.es/grados/fisica/informacion-academica/"
          "horarios-y-calendario-examenes/")

ESTADO = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) \
    / "uni" / "fisica-examenes.json"

DURACION_DEF = 120          # el PDF no publica duración; 2 h es lo típico
AVISO_MIN = 120

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
         "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
         "octubre": 10, "noviembre": 11, "diciembre": 12}
DIAS = "LUNES|MARTES|MIERCOLES|MIÉRCOLES|JUEVES|VIERNES|SABADO|SÁBADO|DOMINGO"

RE_CONVO = re.compile(r"CONVOCATORIA DE\s+([A-ZÑÁÉÍÓÚ\-]+)\s+(\d{4})", re.I)
RE_MES = re.compile(r"^\s*(" + "|".join(MESES) + r")\s*$", re.I)
RE_CABECERA = re.compile(r"\bHora\b.*\b(?:" + DIAS + r")\b", re.I)
RE_DIA = re.compile(r"\b(" + DIAS + r")\s+(\d{1,2})\b", re.I)
RE_HORA = re.compile(r"^(\d{1,2}):(\d{2})$")
RE_HORA_EN_LINEA = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def normalizar(s):
    """'M. MAT. IV' y 'M.MAT IV' → 'MMATIV'. El PDF no es consistente."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s.upper())


# ─────────────────────────── descarga ──────────────────────────────

def descargar(destino):
    """Baja el PDF público de Drive. No necesita rclone ni credenciales."""
    url = f"https://drive.google.com/uc?export=download&id={PDF}"
    r = subprocess.run(["curl", "-fsSL", url, "-o", str(destino)],
                       capture_output=True, text=True)
    if r.returncode or not destino.exists() or destino.stat().st_size < 1024:
        raise RuntimeError(f"no se pudo bajar el PDF ({PDF}). ¿Lo movió la ULL?"
                           f"\n  {PAGINA}")
    with destino.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise RuntimeError("lo que baja de Drive no es un PDF; probablemente "
                               f"el fichero dejó de ser público.\n  {PAGINA}")
    return destino


def texto(pdf):
    r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("pdftotext falló. En Fedora: sudo dnf install poppler-utils")
    return r.stdout


# ─────────────────────────── parseo ────────────────────────────────

def columnas(cabecera):
    """[(inicio, fin, día del mes, meses a sumar)] de una cabecera de semana.

    Cada día ocupa un bloque «Hora … NOMBRE nn … Aula». El inicio de cada
    «Hora» marca dónde empieza su bloque y dónde acaba el anterior.

    Una semana puede cruzar el cambio de mes —«LUNES 28 … JUEVES 1»— y el PDF
    solo etiqueta el mes al principio del bloque. Los días van en orden, así
    que si uno es menor que el anterior es que empezó el mes siguiente.
    """
    inicios = [m.start() for m in re.finditer(r"\bHora\b", cabecera, re.I)]
    out, previo, salto = [], 0, 0
    for i, ini in enumerate(inicios):
        fin = inicios[i + 1] if i + 1 < len(inicios) else len(cabecera) + 500
        m = RE_DIA.search(cabecera[ini:fin])
        if not m:
            continue
        dia = int(m.group(2))
        if dia < previo:
            salto = 1
        previo = dia
        out.append((ini, fin, dia, salto))
    return out


def parsear(txt):
    """[{fecha, hora, asignatura, aula}] de todo el PDF.

    Tolerante a propósito: una fila que no encaje se salta en vez de reventar.
    Un calendario a medias es más útil que un traceback en un timer semanal.
    """
    anio, mes, cols, out = None, None, [], []
    for linea in txt.splitlines():
        m = RE_CONVO.search(linea)
        if m:
            anio, cols = int(m.group(2)), []
            # «JUNIO-JULIO» abre dos meses; el mes real lo dan las etiquetas
            # de cada semana, así que aquí solo nos quedamos con el año.
            continue
        m = RE_MES.match(linea)
        if m:
            mes = MESES[m.group(1).lower()]
            continue
        if RE_CABECERA.search(linea):
            cols = columnas(linea)
            continue
        if not cols or anio is None or mes is None:
            continue

        # El ancla es la HORA, no el offset de la cabecera. Cortar por las
        # posiciones exactas de «Hora» parecía natural pero parte tokens: un
        # 15:00 desplazado un carácter se leía como 5:00. Buscando las horas y
        # asignando cada una a la columna que la contiene, un desajuste de uno
        # o dos caracteres deja de importar.
        horas = list(RE_HORA_EN_LINEA.finditer(linea))
        for i, m in enumerate(horas):
            hasta = horas[i + 1].start() if i + 1 < len(horas) else len(linea)
            partes = linea[m.end():hasta].split()
            if not partes:
                continue
            # La columna MÁS CERCANA, no la primera que contenga la posición:
            # la hora de una fila cae un par de caracteres a la izquierda de su
            # «Hora» de cabecera, y con rangos «el primero que contiene» se
            # asignaba a la columna anterior — todo un día antes.
            ini, _fin, dia, salto = min(cols, key=lambda c: abs(m.start() - c[0]))
            if abs(m.start() - ini) > 15:      # demasiado lejos: no es una celda
                continue
            mes_real, anio_real = mes + salto, anio
            if mes_real > 12:
                mes_real, anio_real = 1, anio + 1
            # El aula es el último campo y son solo dígitos y barras (11/12, 12).
            aula = partes[-1] if re.fullmatch(r"[\d/]+", partes[-1]) else ""
            nombre = " ".join(partes[:-1] if aula else partes)
            if not nombre:
                continue
            try:
                f = date(anio_real, mes_real, dia)
            except ValueError:
                continue
            out.append({"fecha": f.isoformat(),
                        "hora": f"{int(m.group(1)):02d}:{m.group(2)}",
                        "asignatura": nombre, "aula": aula})
    return out


# ───────────────────── qué asignaturas son mías ────────────────────

def alias():
    """{alias normalizado: nombre de la asignatura} desde Asignaturas/."""
    out = {}
    if not uni.DIR_AS.is_dir():
        return out
    for p in sorted(uni.DIR_AS.glob("*.md")):
        fm, _ = uni.frontmatter(p.read_text(encoding="utf-8"))
        if not fm or not fm.get("oficial"):
            continue
        nombre = fm.get("nombre", p.stem)
        vals = fm["oficial"]
        for v in (vals if isinstance(vals, list) else [vals]):
            out[normalizar(v)] = nombre
    return out


def mios(todos, mapa):
    """Solo los exámenes de tus asignaturas, con el nombre bueno puesto."""
    out, vistos = [], set()
    for e in todos:
        nombre = mapa.get(normalizar(e["asignatura"]))
        if not nombre:
            continue
        clave = (e["fecha"], e["hora"], nombre)
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append(dict(e, asignatura=nombre))
    return sorted(out, key=lambda e: (e["fecha"], e["hora"], e["asignatura"]))


# ──────────────────────────── ICS ──────────────────────────────────

def construir_ics(exs):
    ls = ["BEGIN:VCALENDAR", "VERSION:2.0",
          "PRODID:-//uni//examenes oficiales Fisica ULL//ES",
          "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
          "X-WR-CALNAME:Uni — Exámenes oficiales", f"X-WR-TIMEZONE:{uni.TZ}"]
    for e in exs:
        cuerpo = " · ".join(x for x in (
            f"Aula: {e['aula']}" if e["aula"] else "",
            "Fuente: calendario oficial de la Sección de Física") if x)
        ls += uni.evento(
            uni.uid("fisica", e["fecha"], e["hora"], e["asignatura"]),
            uni.utc(date.fromisoformat(e["fecha"]), e["hora"]),
            DURACION_DEF, f"📝 {e['asignatura']}", cuerpo, AVISO_MIN)
    ls.append("END:VCALENDAR")
    return "\r\n".join(uni.plegar(x) for x in ls) + "\r\n"


# ────────────────────────── cambios ────────────────────────────────

def cambios(exs):
    """Qué ha cambiado respecto a la última pasada. [] la primera vez."""
    if not ESTADO.exists():
        return None
    try:
        antes = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    clave = lambda e: (e["asignatura"], e["fecha"], e["hora"], e["aula"])  # noqa: E731
    a, b = {clave(e) for e in antes}, {clave(e) for e in exs}
    return [("+", k) for k in sorted(b - a)] + [("−", k) for k in sorted(a - b)]


def guardar(exs):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(exs, ensure_ascii=False, indent=1),
                      encoding="utf-8")


# ─────────────────────────── comandos ──────────────────────────────

def recoger():
    mapa = alias()
    if not mapa:
        sys.exit("✗ ninguna asignatura declara `oficial:` en su frontmatter.\n"
                 "  Añade el nombre con el que la llama el calendario oficial,\n"
                 '  por ejemplo:  oficial: "M. MAT. IV"')
    with tempfile.TemporaryDirectory() as tmp:
        pdf = descargar(Path(tmp) / "examenes.pdf")
        todos = parsear(texto(pdf))
    return todos, mios(todos, mapa)


def main(argv):
    orden = (argv or ["sync"])[0]
    if orden not in ("sync", "ver", "diff"):
        sys.exit(__doc__)

    todos, exs = recoger()
    if orden == "ver":
        print(f"\n{len(exs)} exámenes tuyos (de {len(todos)} en el PDF)\n")
        for e in exs:
            f = date.fromisoformat(e["fecha"])
            aula = f" · aula {e['aula']}" if e["aula"] else ""
            print(f"  {f:%a %d/%m/%Y}  {e['hora']}  {e['asignatura']}{aula}")
        return 0

    delta = cambios(exs)
    if orden == "diff":
        if delta is None:
            print("Primera vez: no hay con qué comparar.")
        elif not delta:
            print("Sin cambios.")
        else:
            for signo, (asig, f, h, aula) in delta:
                print(f"  {signo} {asig} — {f} {h}" + (f" · {aula}" if aula else ""))
        return 0

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(construir_ics(exs), encoding="utf-8")
    guardar(exs)
    print(f"✓ {len(exs)} exámenes oficiales · {SALIDA}")
    if delta:
        print("  ¡Ojo, la ULL ha cambiado algo!")
        for signo, (asig, f, h, aula) in delta:
            print(f"    {signo} {asig} — {f} {h}" + (f" · {aula}" if aula else ""))
    return 0
