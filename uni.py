#!/usr/bin/env python3
"""
uni.py — motor del vault. Lee las notas de Exámenes/ y Asignaturas/ y:
  · escribe el plan de estudio (checkboxes) dentro de cada nota de examen
  · genera out/uni-estudio.ics (lo lee GNOME Calendar en vivo)
  · saca el plan de hoy por terminal / notificación

    uni ventana     ventanita de alta rápida (la abre Ctrl+Shift+Ñ)
    uni nuevo       alta de un examen: nota + asignatura + plan + calendario
    uni sync        regenera todo (incluye el índice de materiales)
    uni materiales  solo reenlaza los materiales de las asignaturas
    uni hoy         plan de hoy
    uni proximos    siguientes 14 días
    uni notificar   notificación de escritorio (la lanza el timer de systemd)

La fuente de verdad son las notas. Este script nunca las inventa: solo
rellena el bloque entre RAMPA:INICIO y RAMPA:FIN, conservando lo marcado.
"""

import argparse
import hashlib
import re
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

BASE = Path(__file__).resolve().parent
DIR_EX = BASE / "Exámenes"
DIR_AS = BASE / "Asignaturas"
SALIDA = BASE / "out" / "uni-estudio.ics"
TZ = ZoneInfo("Atlantic/Canary")
HORA_ESTUDIO = "17:00"
AVISO_MIN = 30

INICIO = "<!-- RAMPA:INICIO — lo genera uni.py; los [x] se conservan -->"
FIN = "<!-- RAMPA:FIN -->"

# Cuántos días de estudio se planifican si la nota no dice otra cosa.
DIAS_ESTUDIO_DEF = 5

# Las sesiones, en orden pedagógico. (clave, nombre, minutos, qué hacer, prioridad)
#
# La prioridad decide cuáles sobreviven cuando hay menos días que sesiones:
# la 1 no se cae nunca. Las dependencias se respetan solas — "Huecos" (5) solo
# entra si ya entró "Barrido" (3), y "Corrección" (4) si entró "Simulacro" (2).
SESIONES = [
    ("inventario", "Inventario", 30,
     "listar temas, puntuar confianza 0-3, bajar exámenes de otros años", 7),
    ("ataque", "Ataque a lo peor", 90,
     "los 2 temas más flojos, 3 problemas de cada uno, con apuntes", 6),
    ("barrido", "Barrido a libro cerrado", 90,
     "1 problema de CADA tema, cronometrado, sin apuntes — es el diagnóstico", 3),
    ("huecos", "Huecos", 90,
     "solo lo que falló en el barrido, hasta que salga sin mirar", 5),
    ("simulacro", "Simulacro", None,
     "examen entero de otro año, condiciones reales, sin corregir hoy", 2),
    ("correccion", "Corrección", 60,
     "corregir el simulacro, repasar solo los errores, anotarlos en Trampas", 4),
    ("formulario", "Formulario de memoria", 45,
     "escribir el formulario de memoria en un folio, comparar, dormir 8h", 1),
]

# Con más días que sesiones, los de delante se llenan con temario de fondo.
FONDO = ("fondo", "Estudio de fondo", 60,
         "temario por bloques con apuntes: leer, resumir y 2 problemas de cada uno")

# Offsets del modo 'auto' (dias: auto) — la rampa clásica, escalada por peso.
AUTO_OFFSETS = {"inventario": 14, "ataque": 10, "barrido": 7, "huecos": 5,
                "simulacro": 3, "correccion": 2, "formulario": 1}

DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
        "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}


def a_dias(v):
    """5 · '5' · '5 dias' · '1 semana' · 'auto' → 5 | 'auto'."""
    if v is None or v == "":
        return DIAS_ESTUDIO_DEF
    if isinstance(v, bool):
        raise ValueError(f"'dias' no entendido: {v!r}")
    if isinstance(v, int):
        return max(1, v)
    t = str(v).strip().lower()
    if t in ("auto", "peso"):
        return "auto"
    m = re.match(r"(\d+)\s*(?:sem|semana|semanas)\b", t)
    if m:
        return max(1, int(m.group(1)) * 7)
    m = re.match(r"(\d+)", t)
    if m:
        return max(1, int(m.group(1)))
    raise ValueError(f"'dias' no entendido: {v!r} "
                     "(un número, '1 semana' o 'auto')")


def sesiones_para(n):
    """Exactamente n sesiones, una por día, en orden pedagógico."""
    if n >= len(SESIONES):
        extra = n - len(SESIONES)
        fondo = [(FONDO[0], f"{FONDO[1]} ({i + 1}/{extra})", FONDO[2], FONDO[3])
                 for i in range(extra)]
        return fondo + [s[:4] for s in SESIONES]
    elegidas = sorted(SESIONES, key=lambda s: s[4])[:n]
    return [s[:4] for s in SESIONES if s in elegidas]


def rampa_por_peso(peso):
    """Modo 'auto': la rampa clásica, con la longitud que decide el peso."""
    if peso >= 35:
        claves = set(AUTO_OFFSETS)
    elif peso >= 15:
        claves = {"ataque", "barrido", "huecos", "simulacro", "formulario"}
    else:
        claves = {"huecos", "simulacro", "formulario"}
    return [s[:4] for s in SESIONES if s[0] in claves]


def plan_de(ex):
    """El plan concreto de un examen: [(días antes, nombre, minutos, tarea)].

    Con 'dias: N' son N sesiones, una por día, en los N días naturales
    anteriores (D-N … D-1). Si el examen está más cerca que N días, el plan se
    encoge a los días que quedan en vez de generar sesiones ya pasadas.
    """
    if ex["dias"] == "auto":
        return [(AUTO_OFFSETS[c], nom, mins, t)
                for c, nom, mins, t in rampa_por_peso(ex["peso"])]
    n = ex["dias"]
    quedan = (ex["fecha"] - date.today()).days
    if 0 < quedan < n:
        n = quedan
    if n < 1:
        return []
    return [(n - i, nom, mins, t)
            for i, (_c, nom, mins, t) in enumerate(sesiones_para(n))]


# ───────────────────────── leer las notas ──────────────────────────

RE_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def frontmatter(texto):
    m = RE_FM.match(texto)
    if not m:
        return None, texto
    try:
        return yaml.safe_load(m.group(1)) or {}, texto[m.end():]
    except yaml.YAMLError as e:
        print(f"  ! frontmatter inválido: {e}", file=sys.stderr)
        return None, texto


def limpiar_enlace(v):
    """'[[Cálculo II]]' -> 'Cálculo II'"""
    if not isinstance(v, str):
        return v
    m = re.match(r"\[\[([^\]|]+)(\|.*)?\]\]", v.strip())
    return m.group(1).strip() if m else v.strip()


def a_fecha(v):
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    return date.fromisoformat(str(v))


def leer_examenes():
    out = []
    if not DIR_EX.is_dir():
        return out
    for p in sorted(DIR_EX.glob("*.md")):
        fm, cuerpo = frontmatter(p.read_text(encoding="utf-8"))
        if not fm or fm.get("tipo") != "examen":
            continue
        try:
            out.append({
                "ruta": p, "cuerpo": cuerpo,
                "asignatura": limpiar_enlace(fm.get("asignatura", p.stem)),
                "fecha": a_fecha(fm["fecha"]),
                "hora": str(fm.get("hora", "09:00")),
                "formato": fm.get("formato", "examen"),
                "peso": int(fm.get("peso", 20)),
                "dias": a_dias(fm.get("dias")),
                "temas": fm.get("temas") or [],
                "duracion": int(fm.get("duracion_examen", 120)),
            })
        except (KeyError, ValueError) as e:
            print(f"  ! {p.name}: {e}", file=sys.stderr)
    return out


def leer_semanal():
    out = []
    if not DIR_AS.is_dir():
        return out
    for p in sorted(DIR_AS.glob("*.md")):
        fm, _ = frontmatter(p.read_text(encoding="utf-8"))
        if not fm or not fm.get("semanal"):
            continue
        s = fm["semanal"]
        dia = str(s.get("dia", "")).lower()
        if dia not in DIAS:
            print(f"  ! {p.name}: día '{dia}' no válido", file=sys.stderr)
            continue
        out.append({"asignatura": fm.get("nombre", p.stem), "dia": dia,
                    "hora": str(s.get("hora", "18:00")),
                    "duracion": int(s.get("duracion", 60)),
                    "tarea": s.get("tarea", "Problemas de la semana."),
                    "hasta": a_fecha(s["hasta"]) if s.get("hasta") else None})
    return out


# ──────────────── escribir la rampa dentro de la nota ──────────────

# Se guarda por NOMBRE de sesión, no por D-N: con 'dias' variable los offsets
# se mueven, y lo hecho debe sobrevivir tanto a cambiar la fecha del examen
# como a cambiar la ventana de estudio.
RE_TAREA = re.compile(r"^- \[(.)\] D-\d+ · ([^—]+) —")


def inyectar_rampa(ex):
    """Reescribe el bloque de la rampa conservando las tareas ya marcadas."""
    texto = ex["ruta"].read_text(encoding="utf-8")

    hechas = set()
    bloque = re.search(re.escape(INICIO) + r"(.*?)" + re.escape(FIN), texto, re.S)
    if bloque:
        for linea in bloque.group(1).splitlines():
            m = RE_TAREA.match(linea.strip())
            if m and m.group(1).lower() == "x":
                hechas.add(m.group(2).strip())

    lineas = []
    for dias, nombre, mins, tarea in plan_de(ex):
        cuando = ex["fecha"] - timedelta(days=dias)
        marca = "x" if nombre in hechas else " "
        dur = mins or ex["duracion"]
        lineas.append(f"- [{marca}] D-{dias} · {nombre} — {tarea} "
                      f"({dur} min) 📅 {cuando.isoformat()}")
    nuevo = INICIO + "\n" + "\n".join(lineas) + "\n" + FIN

    if bloque:
        texto = texto[:bloque.start()] + nuevo + texto[bloque.end():]
    else:
        texto = texto.rstrip() + "\n\n## Plan de estudio\n" + nuevo + "\n"
    ex["ruta"].write_text(texto, encoding="utf-8")
    return len(hechas)


# ───────────────────────────── ICS ─────────────────────────────────

def esc(t):
    return (str(t).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def plegar(linea):
    if len(linea) <= 70:
        return linea
    trozos, resto = [linea[:70]], linea[70:]
    while resto:
        trozos.append(" " + resto[:69])
        resto = resto[69:]
    return "\r\n".join(trozos)


def uid(*p):
    return hashlib.sha1("|".join(map(str, p)).encode()).hexdigest()[:20] + "@uni.local"


def utc(dia, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(dia, time(h, m), tzinfo=TZ).astimezone(ZoneInfo("UTC"))


def evento(uid_, inicio, minutos, titulo, cuerpo, aviso, rrule=None):
    f = "%Y%m%dT%H%M%SZ"
    ls = ["BEGIN:VEVENT", f"UID:{uid_}",
          f"DTSTAMP:{datetime.now(ZoneInfo('UTC')).strftime(f)}",
          f"DTSTART:{inicio.strftime(f)}",
          f"DTEND:{(inicio + timedelta(minutes=minutos)).strftime(f)}",
          f"SUMMARY:{esc(titulo)}", f"DESCRIPTION:{esc(cuerpo)}"]
    if rrule:
        ls.append(f"RRULE:{rrule}")
    ls += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:-PT{aviso}M",
           f"DESCRIPTION:{esc(titulo)}", "END:VALARM", "END:VEVENT"]
    return ls


def construir_ics(examenes, semanal):
    ls = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//uni//motor de estudio//ES",
          "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
          "X-WR-CALNAME:Uni — Estudio", f"X-WR-TIMEZONE:{TZ}"]
    n = 0
    for ex in examenes:
        temas = ", ".join(map(str, ex["temas"])) or "—"
        ls += evento(uid(ex["asignatura"], ex["fecha"], "EXAMEN"),
                     utc(ex["fecha"], ex["hora"]), ex["duracion"],
                     f"🎓 EXAMEN — {ex['asignatura']} ({ex['formato']}, {ex['peso']}%)",
                     f"Temas: {temas}", 60)
        for dias, nombre, mins, tarea in plan_de(ex):
            cuando = ex["fecha"] - timedelta(days=dias)
            if cuando < date.today():
                continue
            ls += evento(uid(ex["asignatura"], ex["fecha"], dias),
                         utc(cuando, HORA_ESTUDIO), mins or ex["duracion"],
                         f"D-{dias} · {ex['asignatura']} — {nombre}",
                         f"{tarea}\n\nTemas: {temas}\nExamen: {ex['fecha']} "
                         f"({ex['peso']}% de la nota)", AVISO_MIN)
            n += 1
    for b in semanal:
        hoy = date.today()
        primero = hoy + timedelta(days=(DIAS[b["dia"]] - hoy.weekday()) % 7)
        rr = "FREQ=WEEKLY"
        if b["hasta"]:
            rr += f";UNTIL={b['hasta'].strftime('%Y%m%d')}T235959Z"
        ls += evento(uid(b["asignatura"], b["dia"], b["hora"]),
                     utc(primero, b["hora"]), b["duracion"],
                     f"📘 {b['asignatura']} — mantenimiento", b["tarea"],
                     AVISO_MIN, rrule=rr)
    ls.append("END:VCALENDAR")
    return "\r\n".join(plegar(x) for x in ls) + "\r\n", n


# ─────────────────────────── comandos ──────────────────────────────

def agenda(examenes, desde, hasta):
    out = []
    for ex in examenes:
        for dias, nombre, mins, tarea in plan_de(ex):
            cuando = ex["fecha"] - timedelta(days=dias)
            if desde <= cuando <= hasta:
                out.append((cuando, dias, ex["asignatura"], nombre,
                            mins or ex["duracion"], tarea))
        if desde <= ex["fecha"] <= hasta:
            out.append((ex["fecha"], 0, ex["asignatura"], "🎓 EXAMEN",
                        ex["duracion"], "Suerte."))
    return sorted(out)


# ─────────────────── alta rápida de un examen ──────────────────────

RE_INVALIDO = re.compile(r'[\\/:*?"<>|]')

PLANTILLA_ASIGNATURA = """---
nombre: {nombre}
---

# {nombre}

Materiales: ruta o enlace a los apuntes y hojas de problemas.

## Exámenes

```dataview
TABLE WITHOUT ID file.link AS "Examen", fecha AS "Fecha", peso AS "Peso %"
FROM "Exámenes"
WHERE tipo = "examen" AND contains(string(asignatura), "{nombre}")
SORT fecha ASC
```

## Trampas
Errores que ya he cometido. Una línea cada uno, en cuanto pasan. Releer esta
sección antes de cada examen.

-

## Dudas para clase

-
"""


def a_fecha_flexible(t):
    """'2026-11-13' · '13/11' · '13-11-2026' → date. Sin año, la próxima vez."""
    t = str(t).strip()
    try:
        return date.fromisoformat(t)
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", t)
    if not m:
        raise ValueError(f"fecha no entendida: {t!r} (usa AAAA-MM-DD o DD/MM)")
    dia, mes, anio = int(m.group(1)), int(m.group(2)), m.group(3)
    if anio:
        a = int(anio)
        return date(a + 2000 if a < 100 else a, mes, dia)
    hoy = date.today()
    f = date(hoy.year, mes, dia)
    return f if f >= hoy else date(hoy.year + 1, mes, dia)


def a_hora(t):
    """'9:00' · '09:00' → '09:00'. Se valida al escribirla, no al sincronizar."""
    t = str(t).strip() or "09:00"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
    if not m or not (0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60):
        raise ValueError(f"hora no entendida: {t!r} (usa HH:MM)")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def crear_asignatura(nombre):
    """Crea Asignaturas/<nombre>.md si falta, para que el [[enlace]] resuelva."""
    ruta = DIR_AS / f"{RE_INVALIDO.sub('-', nombre)}.md"
    if ruta.exists():
        return ruta, False
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(PLANTILLA_ASIGNATURA.format(nombre=nombre), encoding="utf-8")
    return ruta, True


def crear_examen(asignatura, titulo, fecha, dias, peso, hora, temas,
                 duracion, formato):
    ruta = DIR_EX / f"{RE_INVALIDO.sub('-', f'{asignatura} — {titulo}').strip()}.md"
    if ruta.exists():
        raise FileExistsError(ruta)
    bloque = ("\n" + "\n".join(f"  - {t}" for t in temas)) if temas else " []"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        "---\n"
        "tipo: examen\n"
        f'asignatura: "[[{asignatura}]]"\n'
        f"fecha: {fecha.isoformat()}\n"
        f'hora: "{hora}"\n'
        f"formato: {formato}\n"
        f"peso: {peso}\n"
        f"dias: {dias}\n"
        f"temas:{bloque}\n"
        f"duracion_examen: {duracion}\n"
        "---\n"
        f"\n# {asignatura} — {titulo}\n"
        "\n## Exámenes de otros años\n\n-\n"
        "\n## Simulacro\n"
        "| Fecha | Nota | Qué falló |\n"
        "|-------|------|-----------|\n"
        "|       |      |           |\n",
        encoding="utf-8")
    return ruta


# ──────────── índice de materiales (lo que llena el grafo) ─────────
# Los PDFs de las asignaturas no son nodos de nada hasta que una nota los
# enlaza. Esto recorre Curso/Cuatrimestre/Asignatura/ y escribe esos enlaces
# dentro de la nota de cada asignatura, más un índice que las une.
#
# Solo se toca lo que hay entre los marcadores: lo que escribas fuera se queda.

MAT_INICIO = "<!-- MATERIALES:INICIO — lo genera uni.py; escribe fuera del bloque -->"
MAT_FIN = "<!-- MATERIALES:FIN -->"

INDICE = BASE / "Materiales.md"

# Carpetas de la raíz que son del sistema, no cursos.
NO_CURSOS = {"Asignaturas", "Exámenes", "Ejemplos", "Plantillas", "sistema",
             "out", "__pycache__"}


def cursos():
    """[(curso, cuatrimestre, asignatura, ruta)] leído del árbol de carpetas.

    Espera Curso/Cuatrimestre/Asignatura/. Lo que cuelgue a otra profundidad
    no se indexa: sin una convención fija no hay forma de saber qué es una
    asignatura y qué una subcarpeta suya.
    """
    out = []
    for curso in sorted(p for p in BASE.iterdir() if p.is_dir()
                        and not p.name.startswith(".")
                        and p.name not in NO_CURSOS):
        for cuatri in sorted(q for q in curso.iterdir() if q.is_dir()):
            asigs = sorted(a for a in cuatri.iterdir() if a.is_dir())
            # Un cuatrimestre aún sin asignaturas también sale en el índice:
            # es el que estás preparando.
            out.append((curso.name, cuatri.name, None, None))
            out += [(curso.name, cuatri.name, a.name, a) for a in asigs]
    return out


def poner_bloque(texto, inicio, fin, cuerpo, encabezado=""):
    """Sustituye el bloque delimitado, o lo añade al final si no estaba."""
    nuevo = inicio + "\n" + cuerpo + "\n" + fin
    m = re.search(re.escape(inicio) + r".*?" + re.escape(fin), texto, re.S)
    if m:
        return texto[:m.start()] + nuevo + texto[m.end():]
    return texto.rstrip() + "\n\n" + (encabezado + "\n" if encabezado else "") \
        + nuevo + "\n"


def materiales_de(carpeta):
    """Enlaces a todo lo que cuelga de la carpeta de una asignatura."""
    ls = []
    for f in sorted(carpeta.rglob("*")):
        if f.is_dir() or f.name.startswith("."):
            continue
        rel = f.relative_to(BASE).as_posix()
        sub = f.parent.relative_to(carpeta).as_posix()
        etiqueta = f.stem if sub == "." else f"{sub}/{f.stem}"
        ls.append(f"- [[{rel}|{etiqueta}]]")
    return ls


def indexar_materiales():
    """Enlaza los materiales desde las notas de asignatura y arma el índice."""
    arbol, n_arch, n_asig = {}, 0, 0
    for curso, cuatri, asig, ruta in cursos():
        cuatris = arbol.setdefault(curso, {}).setdefault(cuatri, [])
        if asig is None:                      # cuatrimestre aún vacío
            continue
        cuatris.append(asig)
        n_asig += 1

        enlaces = materiales_de(ruta)
        n_arch += len(enlaces)
        nota, _ = crear_asignatura(asig)
        cuerpo = "\n".join(enlaces) if enlaces else "*(carpeta vacía)*"
        nota.write_text(
            poner_bloque(nota.read_text(encoding="utf-8"),
                         MAT_INICIO, MAT_FIN, cuerpo, "## Materiales"),
            encoding="utf-8")

    if not arbol:
        return 0, 0

    lineas = []
    for curso, cuatris in arbol.items():
        lineas.append(f"\n## {curso}")
        for cuatri, asigs in cuatris.items():
            lineas.append(f"\n### {cuatri}\n")
            lineas += [f"- [[{a}]]" for a in asigs] or ["*(sin asignaturas todavía)*"]
    cuerpo = "\n".join(lineas).strip()

    viejo = INDICE.read_text(encoding="utf-8") if INDICE.exists() else \
        "# Materiales\n\nÍndice de las carpetas de cada curso. Lo genera\n" \
        "`uni sync`: si añades un PDF, aparece solo.\n"
    INDICE.write_text(poner_bloque(viejo, MAT_INICIO, MAT_FIN, cuerpo),
                      encoding="utf-8")

    return n_asig, n_arch


def cmd_materiales():
    n_asig, n_arch = indexar_materiales()
    print(f"✓ {n_asig} asignaturas · {n_arch} materiales enlazados")


def cmd_nuevo(argv):
    ap = argparse.ArgumentParser(
        prog="uni nuevo", add_help=True,
        description="Alta de un examen: crea la nota, la asignatura si falta, "
                    "escribe el plan y sincroniza el calendario.")
    ap.add_argument("asignatura", nargs="?", help='p. ej. "Cálculo Diferencial"')
    ap.add_argument("titulo", nargs="?", help='p. ej. "Parcial 2"')
    ap.add_argument("fecha", nargs="?", help="AAAA-MM-DD o DD/MM")
    ap.add_argument("-d", "--dias", default=None,
                    help=f"días de estudio previos (def. {DIAS_ESTUDIO_DEF}; "
                         "vale '1 semana' y 'auto' = según el peso)")
    ap.add_argument("-p", "--peso", type=int, default=30, help="%% de la nota (def. 30)")
    ap.add_argument("-o", "--hora", default="09:00", help="hora del examen (def. 09:00)")
    ap.add_argument("-t", "--temas", default="", help="separados por comas")
    ap.add_argument("-m", "--duracion", type=int, default=120,
                    help="minutos de examen (def. 120)")
    ap.add_argument("-f", "--formato", default=None,
                    help="parcial, final… (def. el título)")
    a = ap.parse_args(argv)

    pide = not (a.asignatura and a.titulo and a.fecha)
    asignatura = a.asignatura or input("Asignatura: ").strip()
    titulo = a.titulo or input("Examen (p. ej. Parcial 2): ").strip()
    fecha_txt = a.fecha or input("Fecha (AAAA-MM-DD o DD/MM): ").strip()
    dias_txt = a.dias
    if pide and dias_txt is None:
        dias_txt = input(f"Días de estudio [{DIAS_ESTUDIO_DEF}]: ").strip() or None
    if not (asignatura and titulo and fecha_txt):
        sys.exit("Faltan datos: asignatura, examen y fecha.")

    try:
        fecha, dias = a_fecha_flexible(fecha_txt), a_dias(dias_txt)
        hora = a_hora(a.hora)
    except ValueError as e:
        sys.exit(f"✗ {e}")
    if fecha < date.today():
        sys.exit(f"✗ esa fecha ya pasó ({fecha:%d/%m/%Y}).")

    # La asignatura se crea DESPUÉS del examen: si el examen ya existía, no
    # queremos dejar una nota de asignatura huérfana.
    try:
        ruta = crear_examen(asignatura, titulo, fecha, dias, a.peso, hora,
                            [t.strip() for t in a.temas.split(",") if t.strip()],
                            a.duracion, a.formato or titulo)
    except FileExistsError as e:
        sys.exit(f"✗ ya existe {Path(e.args[0]).name} — edítala o usa otro título.")
    ruta_as, nueva = crear_asignatura(asignatura)

    if nueva:
        print(f"✓ asignatura nueva → {ruta_as.name}")
    print(f"✓ {ruta.name}  ·  {fecha:%a %d/%m/%Y}  ·  {dias} días de estudio\n")

    plan = plan_de({"fecha": fecha, "dias": dias, "peso": a.peso,
                    "duracion": a.duracion})
    for d, nombre, mins, _t in plan:
        cuando = fecha - timedelta(days=d)
        print(f"   D-{d:<2} {cuando:%a %d/%m}  {nombre}  ({mins or a.duracion} min)")
    print()
    cmd_sync()


def cmd_sync():
    ex, sem = leer_examenes(), leer_semanal()
    if not ex:
        print("No hay notas de examen en Exámenes/ (¿frontmatter 'tipo: examen'?)")
    tot_hechas = 0
    for e in ex:
        tot_hechas += inyectar_rampa(e)
    ics, n = construir_ics(ex, sem)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(ics, encoding="utf-8")
    print(f"✓ {len(ex)} exámenes · {n} sesiones · {len(sem)} bloques semanales"
          f" · {tot_hechas} tareas ya hechas conservadas")
    print(f"✓ {SALIDA}")
    n_asig, n_arch = indexar_materiales()
    if n_asig:
        print(f"✓ {n_asig} asignaturas · {n_arch} materiales enlazados")


def cmd_hoy():
    hoy = date.today()
    items = agenda(leer_examenes(), hoy, hoy)
    if not items:
        print("Hoy no hay nada. Descansa o adelanta.")
        return
    print(f"── {hoy:%A %d/%m} " + "─" * 30)
    for _, d, asig, nombre, mins, tarea in items:
        cab = f"{asig} — {nombre}" if d == 0 else f"D-{d} · {asig} — {nombre}"
        print(f"\n  {cab}  ({mins} min)\n    {tarea}")


def cmd_proximos():
    hoy = date.today()
    items = agenda(leer_examenes(), hoy, hoy + timedelta(days=14))
    if not items:
        print("Nada en los próximos 14 días.")
        return
    actual = None
    for cuando, d, asig, nombre, mins, _ in items:
        if cuando != actual:
            actual = cuando
            print(f"\n{'HOY' if cuando == hoy else format(cuando, '%a %d/%m')}")
        print(f"   {asig:<22} {nombre if d == 0 else f'D-{d} · {nombre}'}  ({mins} min)")


def cmd_notificar():
    hoy = date.today()
    items = agenda(leer_examenes(), hoy, hoy)
    if not items:
        return
    cuerpo = "\n".join(
        (f"{a} — {n}" if d == 0 else f"D-{d} · {a} — {n}") + f"  ({m} min)"
        for _, d, a, n, m, _t in items)
    subprocess.run(["notify-send", "-a", "Uni",
                    "-u", "critical" if any(d <= 1 for _, d, *_ in items) else "normal",
                    "📚 Plan de hoy", cuerpo], check=False)


def cmd_ventana():
    """La ventanita de alta rápida. Es lo que cuelga de Ctrl+Shift+Ñ."""
    try:
        import ventana                      # perezoso: la CLI no necesita GTK
    except ImportError as e:
        sys.exit(f"✗ falta PyGObject/GTK4: {e}\n"
                 "  En Fedora: sudo dnf install python3-gobject gtk4 libadwaita")
    sys.exit(ventana.abrir(sys.modules[__name__]))


CMDS = {"sync": cmd_sync, "hoy": cmd_hoy, "proximos": cmd_proximos,
        "notificar": cmd_notificar, "ventana": cmd_ventana,
        "materiales": cmd_materiales}

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "hoy"
    if a == "nuevo":
        cmd_nuevo(sys.argv[2:])
    elif a in CMDS:
        CMDS[a]()
    else:
        sys.exit(__doc__)
