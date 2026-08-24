#!/usr/bin/env python3
"""
ull.py — espeja el calendario OFICIAL de exámenes de la ESIT (ULL) en un
calendario propio, aparte del de estudio.

    ull sync            baja los .docx, regenera out/uni-ull.ics y avisa si cambió
    ull sync --forzar   escribe aunque la cosecha parezca sospechosa
    ull ver             enseña por terminal los exámenes que detecta
    ull diff            solo dice si hay cambios respecto a la última vez

Está pensado para correr solo en un timer semanal, así que lo importante no
es que funcione hoy sino que FALLE RUIDOSAMENTE el día que la ESIT cambie
algo. De ahí las cuatro defensas:

  · las columnas se leen POR NOMBRE de cabecera, no por posición, así que
    añadir o mover una columna no hace que se lea la de al lado;
  · una tabla sin cabecera reconocible se ignora entera y se reporta;
  · NUNCA se escribe un calendario vacío ni uno que pierda más de la mitad de
    los exámenes: se deja el anterior (viejo pero correcto) y se avisa;
  · el id de la carpeta de Drive se resuelve desde la página de la ESIT; el
    id a fuego es solo la red de seguridad.

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
import time as _time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

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


def normalizar(texto):
    """Sin acentos, minúsculas, sin espacios de sobra. Para comparar cabeceras."""
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(plano.lower().split())


# Cabecera del .docx → clave interna. Se busca POR NOMBRE, no por posición: si
# la ESIT añade una columna o las reordena, esto sigue funcionando en vez de
# leer en silencio la columna equivocada, que es el fallo que no se ve venir.
COLUMNAS = {
    "dia": "dia", "fecha": "fecha", "curso": "curso", "c": "cuatri",
    "cuatrimestre": "cuatri", "asignatura": "asignatura", "hora": "hora",
    "aula": "aula", "observaciones": "obs", "observacion": "obs",
}
# Sin estas no hay examen que valga; si falta una, la tabla no es lo que creemos.
IMPRESCINDIBLES = {"fecha", "curso", "asignatura", "hora"}


def mapear_cabecera(celdas):
    """{clave: índice} si esta fila es la cabecera de la tabla; si no, None."""
    mapa = {}
    for i, c in enumerate(celdas):
        clave = COLUMNAS.get(normalizar(c))
        if clave and clave not in mapa:
            mapa[clave] = i
    return mapa if IMPRESCINDIBLES <= set(mapa) else None


# ─────────────────────────── descarga ──────────────────────────────

RE_CARPETA = re.compile(r"drive\.google\.com/drive/folders/([A-Za-z0-9_-]{20,})")


def carpeta_de_la_pagina(timeout=15):
    """El id de la carpeta de Drive, leído de la página de la ESIT.

    Tener el id a fuego es la fragilidad más tonta: el día que la ESIT cuelgue
    otra carpeta, el sistema seguiría bajando la del año pasado sin quejarse.
    La página sí es estable, así que se pregunta ahí y el id fijo queda solo
    como red de seguridad si la web no responde o cambia de formato.
    """
    try:
        pet = urllib.request.Request(PAGINA, headers={"User-Agent": "uni/1.0"})
        with urllib.request.urlopen(pet, timeout=timeout) as r:
            html = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    ids = RE_CARPETA.findall(html)
    # Si hay varias, no adivinamos: nos quedamos con la fija conocida.
    return ids[0] if len(set(ids)) == 1 else None


def resolver_carpeta():
    """(id, de_dónde_salió). UNI_ULL_CARPETA manda siempre."""
    if os.environ.get("UNI_ULL_CARPETA"):
        return os.environ["UNI_ULL_CARPETA"], "variable de entorno"
    v = carpeta_de_la_pagina()
    if v and v != CARPETA:
        return v, "página de la ESIT (¡cambió respecto a la conocida!)"
    if v:
        return v, "página de la ESIT"
    return CARPETA, "id fijo (la página no respondió)"


def descargar(destino, intentos=3):
    """Copia los .docx de la carpeta pública con el rclone ya configurado.

    Reintenta: esto lo dispara un timer semanal, y morir por un corte de red
    de tres segundos significaría enterarse del cambio de fecha una semana
    tarde.
    """
    if not shutil_which("rclone"):
        raise RuntimeError(
            "falta rclone, que es quien baja los .docx.\n"
            "  sudo dnf install rclone  &&  rclone config")
    remoto = os.environ.get("UNI_DRIVE_REMOTO", "drive")
    carpeta, origen = resolver_carpeta()

    ultimo = ""
    for n in range(1, intentos + 1):
        r = subprocess.run(
            ["rclone", "copy", "--drive-root-folder-id", carpeta,
             f"{remoto}:", str(destino), "--include", "*.docx",
             "--timeout", "60s", "--retries", "1"],
            capture_output=True, text=True)
        if r.returncode == 0:
            break
        ultimo = (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]
        ultimo = ultimo[0]
        if n < intentos:
            _time.sleep(3 * n)
    else:
        raise RuntimeError(
            f"rclone falló {intentos} veces (carpeta {carpeta}, {origen}).\n"
            f"  último error: {ultimo}\n"
            f"  ¿sigue existiendo la carpeta? {PAGINA}")

    docs = sorted(destino.glob("*.docx"))
    if not docs:
        raise RuntimeError(
            f"la carpeta {carpeta} ({origen}) no tiene ningún .docx.\n"
            f"  ¿La movió la ESIT, o cambió a PDF? Míralo en:\n  {PAGINA}")
    return docs


def shutil_which(x):
    from shutil import which
    return which(x)


# ─────────────────────────── parseo ────────────────────────────────

def celdas(tr):
    return [" ".join("".join(t.text or "" for t in tc.iter(W + "t")).split())
            for tc in tr.findall(W + "tc")]


def parsear(ruta):
    """(exámenes, incidencias) de un .docx de la ESIT.

    Localiza la CABECERA de cada tabla y lee por nombre de columna. Si una
    tabla no tiene cabecera reconocible se ignora entera y se anota: mejor
    decir «esta tabla no la entiendo» que leer la columna de al lado.

    Tolerante fila a fila (una fila rara se salta), pero las incidencias se
    devuelven para que quien llame decida si el resultado es de fiar.
    """
    try:
        xml = zipfile.ZipFile(ruta).read("word/document.xml")
        raiz = ET.fromstring(xml)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        return [], [f"{ruta.name}: no es un .docx legible ({e})"]

    out, incidencias, tablas = [], [], 0
    for tbl in raiz.iter(W + "tbl"):
        filas = list(tbl.iter(W + "tr"))
        mapa, fecha = None, None
        for tr in filas:
            c = celdas(tr)
            if mapa is None:                       # aún buscando la cabecera
                mapa = mapear_cabecera(c)
                continue
            tablas += 1 if len(out) == 0 else 0

            def celda(clave, por_defecto=""):
                i = mapa.get(clave)
                return c[i].strip() if i is not None and i < len(c) else por_defecto

            m = RE_FECHA.match(celda("fecha"))
            if m:                                   # arrastra la fecha
                d, mes, a = (int(x) for x in m.groups())
                try:
                    fecha = date(a, mes, d)
                except ValueError:
                    incidencias.append(f"{ruta.name}: fecha imposible {celda('fecha')}")
                    fecha = None
            if fecha is None or celda("curso") != CURSO:
                continue
            hora = celda("hora")
            if not re.match(r"^\d{1,2}:\d{2}$", hora):
                continue
            asig = celda("asignatura")
            if not asig:
                incidencias.append(f"{ruta.name}: fila {fecha} {hora} sin asignatura")
                continue
            out.append({
                "fecha": fecha.isoformat(),
                "hora": hora if len(hora) == 5 else f"0{hora}",
                "asignatura": asig,
                "aula": celda("aula"),
                "obs": celda("obs"),
                "cuatri": celda("cuatri"),
            })
        if mapa is None and filas:
            incidencias.append(
                f"{ruta.name}: una tabla de {len(filas)} filas sin cabecera "
                f"reconocible (¿cambió el formato?)")
    return out, incidencias


def examenes():
    """(exámenes, incidencias) del curso, de todos los meses, sin duplicados."""
    with tempfile.TemporaryDirectory() as tmp:
        docs = descargar(Path(tmp))
        vistos, out, incidencias = set(), [], []
        for d in docs:
            exs, inc = parsear(d)
            incidencias += inc
            if not exs:
                incidencias.append(f"{d.name}: 0 exámenes del curso {CURSO}")
            for e in exs:
                clave = (e["fecha"], e["hora"], e["asignatura"], e["obs"])
                if clave in vistos:
                    continue
                vistos.add(clave)
                out.append(e)
    out.sort(key=lambda e: (e["fecha"], e["hora"], e["asignatura"]))
    return out, incidencias


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

def _sin_dtstamp(texto):
    """El .ics sin las marcas de generación: lo que de verdad importa."""
    return [l for l in texto.splitlines() if not l.startswith("DTSTAMP:")]


def escribir_si_cambia(nuevo):
    """Reescribe el .ics SOLO si cambió algo de fondo.

    DTSTAMP lleva la hora de generación, así que reescribir a lo bruto cambia
    las 44 líneas en cada pasada. Como este fichero SÍ se versiona (es la URL
    a la que se suscribe el móvil), eso llenaría el historial de commits que
    no dicen nada. Comparando sin DTSTAMP, un `sync` sin novedades no toca el
    fichero y git no ve nada.
    """
    if SALIDA.exists() and \
            _sin_dtstamp(SALIDA.read_text(encoding="utf-8")) == _sin_dtstamp(nuevo):
        return False
    SALIDA.write_text(nuevo, encoding="utf-8")
    return True


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


class CosechaSospechosa(RuntimeError):
    """El parseo salió tan raro que NO se toca el calendario."""


def revisar_cosecha(exs, previos, incidencias, forzar=False):
    """Freno de mano: negarse a pisar el calendario con una cosecha dudosa.

    El fallo peligroso de esto no es un traceback, es el SILENCIO: si la ESIT
    cambia el formato del .docx, el parseo devuelve cero filas, se escribe un
    .ics vacío y el calendario de exámenes se queda en blanco sin que nadie se
    entere. Un examen que desaparece sin avisar es mucho peor que un error.

    Así que: cero exámenes no se escribe nunca, y una caída de más de la mitad
    respecto a lo que había tampoco. Se avisa y se deja el .ics anterior — que
    estará viejo, pero es correcto. `--forzar` es la salida cuando la caída es
    real (un curso que de verdad se queda sin exámenes).
    """
    if forzar:
        return
    detalle = ("\n  " + "\n  ".join(incidencias)) if incidencias else ""
    if not exs:
        raise CosechaSospechosa(
            f"0 exámenes del curso {CURSO}: NO toco el calendario.\n"
            f"  El .ics anterior se queda como estaba.{detalle}\n"
            f"  Míralo en: {PAGINA}\n"
            f"  Si de verdad no hay exámenes: uni ull sync --forzar")
    if previos and len(exs) < len(previos) / 2:
        raise CosechaSospechosa(
            f"de {len(previos)} exámenes a {len(exs)}: caída sospechosa, "
            f"NO toco el calendario.{detalle}\n"
            f"  Si el cambio es real: uni ull sync --forzar")


# ──────────────────────────── comandos ─────────────────────────────

def cmd_sync(avisar=True, forzar=False):
    exs, incidencias = examenes()
    previos = leer_estado()
    revisar_cosecha(exs, previos, incidencias, forzar)

    nuevos, fuera, movidos = comparar(previos, exs)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    escribir_si_cambia(construir_ics(exs))
    guardar_estado(exs)

    print(f"✓ {len(exs)} exámenes del curso {CURSO} · {SALIDA}")
    for i in incidencias:
        print(f"  ! {i}", file=sys.stderr)
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
    exs, incidencias = examenes()
    for i in incidencias:
        print(f"  ! {i}", file=sys.stderr)
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
    exs, _inc = examenes()
    nuevos, fuera, movidos = comparar(leer_estado(), exs)
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
            return cmd_sync(avisar="--sin-aviso" not in argv,
                            forzar="--forzar" in argv)
        if cmd == "ver":
            return cmd_ver()
        if cmd == "diff":
            return cmd_diff()
    except CosechaSospechosa as e:
        # Esto SÍ se grita: el calendario se ha quedado sin actualizar.
        print(f"✗ {e}", file=sys.stderr)
        subprocess.run(
            ["notify-send", "-a", "Uni", "-u", "critical",
             "⚠️ Calendario de exámenes SIN actualizar",
             str(e).splitlines()[0]], check=False)
        return 1
    except RuntimeError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"Orden desconocida: {cmd}. Usa sync | ver | diff.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
