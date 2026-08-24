#!/usr/bin/env python3
"""
uni.py — motor del vault. Lee las notas de Exámenes/ y Asignaturas/ y:
  · escribe el plan de estudio (checkboxes) dentro de cada nota de examen
  · genera out/uni-estudio.ics (lo lee GNOME Calendar en vivo)
  · saca el plan de hoy por terminal / notificación

    uni ventana     ventanita de alta rápida (la abre Ctrl+Shift+Ñ)
    uni nuevo       alta de un examen: nota + asignatura + plan + calendario
    uni estado      comprueba que todas las piezas siguen vivas
    uni sync        regenera todo (incluye el índice del grafo)
    uni indice      solo rehace los nodos curso/cuatrimestre/asignatura
    uni ull         espeja el calendario oficial de exámenes de la ESIT
    uni fisica      lo mismo para la Sección de Física
    uni hoy         plan de hoy
    uni proximos    siguientes 14 días
    uni notificar   notificación de escritorio (la lanza el timer de systemd)

La fuente de verdad son las notas. Este script nunca las inventa: solo
rellena el bloque entre RAMPA:INICIO y RAMPA:FIN, conservando lo marcado.
"""

import argparse
import fcntl
import hashlib
import os
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

# Todas las sesiones se llaman igual en el calendario y en las tareas. Lo que
# cambia entre ellas es QUÉ hacer, y eso va en la descripción, no en el título.
NOMBRE = "Estudio"

# Las sesiones, en orden pedagógico. (clave, minutos, qué hacer, prioridad)
#
# La prioridad decide cuáles sobreviven cuando hay menos días que sesiones:
# la 1 no se cae nunca. Las dependencias se respetan solas — los huecos (5)
# solo entran si ya entró el barrido (3), y la corrección (4) si entró el
# simulacro (2).
SESIONES = [
    ("inventario", 30,
     "listar temas, puntuar confianza 0-3, bajar exámenes de otros años", 7),
    ("ataque", 90,
     "los 2 temas más flojos, 3 problemas de cada uno, con apuntes", 6),
    ("barrido", 90,
     "1 problema de CADA tema, cronometrado, sin apuntes — es el diagnóstico", 3),
    ("huecos", 90,
     "repasar solo lo que falló el día anterior, hasta que salga sin mirar", 5),
    ("simulacro", None,
     "examen entero de otro año, condiciones reales, sin corregir hoy", 2),
    ("correccion", 60,
     "corregir el examen del día anterior, repasar solo los errores y "
     "anotarlos en Trampas", 4),
    ("formulario", 45,
     "escribir el formulario de memoria en un folio, comparar, dormir 8h", 1),
]

# Con más días que sesiones, los de delante se llenan con temario de fondo.
FONDO = ("fondo", 60,
         "temario por bloques con apuntes: leer, resumir y 2 problemas de cada uno")

# Offsets del modo 'auto' (dias: auto) — la rampa clásica, escalada por peso.
AUTO_OFFSETS = {"inventario": 14, "ataque": 10, "barrido": 7, "huecos": 5,
                "simulacro": 3, "correccion": 2, "formulario": 1}

DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
        "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}

# Qué clase de examen es. Se elige de la lista, no se escribe.
TIPOS = ["Parcial", "Final", "Recuperación", "Test"]

# Un examen se aprueba; una entrega se entrega. La rampa sirve para los dos,
# pero el evento no se llama igual y a una entrega no le pega un «Parcial».
CLASES = ["examen", "entrega"]
ICONO = {"examen": "🎓 EXAMEN", "entrega": "📦 ENTREGA"}


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
        return [FONDO[:3]] * (n - len(SESIONES)) + [s[:3] for s in SESIONES]
    elegidas = sorted(SESIONES, key=lambda s: s[3])[:n]
    return [s[:3] for s in SESIONES if s in elegidas]


def rampa_por_peso(peso):
    """Modo 'auto': la rampa clásica, con la longitud que decide el peso."""
    if peso >= 35:
        claves = set(AUTO_OFFSETS)
    elif peso >= 15:
        claves = {"ataque", "barrido", "huecos", "simulacro", "formulario"}
    else:
        claves = {"huecos", "simulacro", "formulario"}
    return [s[:3] for s in SESIONES if s[0] in claves]


def plan_de(ex):
    """El plan concreto de un examen: [(días antes, nombre, minutos, tarea)].

    Con 'dias: N' son N sesiones, una por día, en los N días naturales
    anteriores (D-N … D-1). Si el examen está más cerca que N días, el plan se
    encoge a los días que quedan en vez de generar sesiones ya pasadas.
    """
    if ex["dias"] == "auto":
        return [(AUTO_OFFSETS[c], NOMBRE, mins, t)
                for c, mins, t in rampa_por_peso(ex["peso"])]
    n = ex["dias"]
    quedan = (ex["fecha"] - date.today()).days
    if 0 < quedan < n:
        n = quedan
    if n < 1:
        return []
    return [(n - i, NOMBRE, mins, t)
            for i, (_c, mins, t) in enumerate(sesiones_para(n))]


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
        if not fm or fm.get("tipo") not in CLASES:
            continue
        try:
            out.append({
                "ruta": p, "cuerpo": cuerpo,
                "clase": fm["tipo"],
                # Las notas viejas no llevan `titulo`; sale del nombre del fichero.
                "titulo": fm.get("titulo") or p.stem.split(" — ", 1)[-1],
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


def leer_horario():
    """Las clases fijas del bloque `horario` de cada asignatura.

    Es una lista porque una asignatura tiene varias clases a la semana, a
    distinta hora y en distinta aula. `hasta` puede ir en cada clase o una vez
    para toda la asignatura (el último día de docencia del cuatrimestre).
    """
    out = []
    if not DIR_AS.is_dir():
        return out
    for p in sorted(DIR_AS.glob("*.md")):
        fm, _ = frontmatter(p.read_text(encoding="utf-8"))
        if not fm or not fm.get("horario"):
            continue
        fin_asig = a_fecha(fm["hasta"]) if fm.get("hasta") else None
        for c in fm["horario"]:
            dia = str(c.get("dia", "")).lower()
            if dia not in DIAS:
                print(f"  ! {p.name}: día '{dia}' no válido", file=sys.stderr)
                continue
            try:
                out.append({
                    "asignatura": fm.get("nombre", p.stem), "dia": dia,
                    "hora": a_hora(c.get("hora", "08:30")),
                    "duracion": int(c.get("duracion", 60)),
                    "tipo": str(c.get("tipo", "Clase")),
                    "aula": str(c.get("aula", "")),
                    "hasta": a_fecha(c["hasta"]) if c.get("hasta") else fin_asig,
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

# Se guarda por D-N. Antes se guardaba por nombre de sesión, pero ahora todas
# se llaman «Estudio»: marcar una marcaría las cinco. Y con sesiones idénticas
# el día es justo lo que las distingue, así que la clave correcta es el número.
RE_TAREA = re.compile(r"^- \[(.)\] D-(\d+) ")


def inyectar_rampa(ex):
    """Reescribe el bloque de la rampa conservando las tareas ya marcadas."""
    texto = ex["ruta"].read_text(encoding="utf-8")

    hechas = set()
    bloque = re.search(re.escape(INICIO) + r"(.*?)" + re.escape(FIN), texto, re.S)
    if bloque:
        for linea in bloque.group(1).splitlines():
            m = RE_TAREA.match(linea.strip())
            if m and m.group(1).lower() == "x":
                hechas.add(int(m.group(2)))

    lineas = []
    for dias, nombre, mins, tarea in plan_de(ex):
        cuando = ex["fecha"] - timedelta(days=dias)
        marca = "x" if dias in hechas else " "
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
    """aviso=None deja el evento sin alarma: las clases fijas no la necesitan."""
    f = "%Y%m%dT%H%M%SZ"
    ls = ["BEGIN:VEVENT", f"UID:{uid_}",
          f"DTSTAMP:{datetime.now(ZoneInfo('UTC')).strftime(f)}",
          f"DTSTART:{inicio.strftime(f)}",
          f"DTEND:{(inicio + timedelta(minutes=minutos)).strftime(f)}",
          f"SUMMARY:{esc(titulo)}", f"DESCRIPTION:{esc(cuerpo)}"]
    if rrule:
        ls.append(f"RRULE:{rrule}")
    if aviso is not None:
        ls += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:-PT{aviso}M",
               f"DESCRIPTION:{esc(titulo)}", "END:VALARM"]
    ls.append("END:VEVENT")
    return ls


def eventos_recurrentes(bloques, titulo, cuerpo, aviso):
    """Un evento semanal por bloque, desde el próximo día que toque."""
    ls, hoy = [], date.today()
    for b in bloques:
        primero = hoy + timedelta(days=(DIAS[b["dia"]] - hoy.weekday()) % 7)
        rr = "FREQ=WEEKLY"
        if b["hasta"]:
            rr += f";UNTIL={b['hasta'].strftime('%Y%m%d')}T235959Z"
        ls += evento(uid(b["asignatura"], b["dia"], b["hora"], b.get("tipo", "")),
                     utc(primero, b["hora"]), b["duracion"],
                     titulo(b), cuerpo(b), aviso, rrule=rr)
    return ls


def construir_ics(examenes, semanal, horario=()):
    ls = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//uni//motor de estudio//ES",
          "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
          "X-WR-CALNAME:Uni — Estudio", f"X-WR-TIMEZONE:{TZ}"]
    n = 0
    for ex in examenes:
        temas = ", ".join(map(str, ex["temas"])) or "—"
        cola = ex["titulo"] if ex["clase"] == "entrega" else ex["formato"]
        ls += evento(uid(ex["asignatura"], ex["fecha"], "EXAMEN"),
                     utc(ex["fecha"], ex["hora"]), ex["duracion"],
                     f"{ICONO[ex['clase']]} — {ex['asignatura']} ({cola})",
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
    # El horario de clases NO va al calendario a propósito: son doce eventos
    # que se repiten cada semana y que ya te sabes, y llenan la vista de ruido
    # tapando lo único que hay que mirar, que son los exámenes y las sesiones
    # de estudio. Vive como tabla en la nota del cuatrimestre.

    ls += eventos_recurrentes(
        semanal, lambda b: f"📘 {b['asignatura']} — mantenimiento",
        lambda b: b["tarea"], AVISO_MIN)

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
            out.append((ex["fecha"], 0, ex["asignatura"], ICONO[ex["clase"]],
                        ex["duracion"],
                        "A entregar." if ex["clase"] == "entrega" else "Suerte."))
    return sorted(out)


# ─────────────────── alta rápida de un examen ──────────────────────

RE_INVALIDO = re.compile(r'[\\/:*?"<>|]')


def nombre_nota(x):
    """Obsidian no admite \\ / : * ? " < > | en el nombre de una nota."""
    return RE_INVALIDO.sub("-", x).strip()

PLANTILLA_ASIGNATURA = """---
nombre: {nombre}
# La hora fija semanal es la que de verdad sube la nota; la rampa solo evita
# el desastre. Descoméntalo y elige un hueco que puedas sostener 15 semanas.
# semanal:
#   dia: martes
#   hora: "18:00"
#   duracion: 60
#   tarea: "Problemas de la hoja de esta semana. Sin mirar soluciones."
#   hasta: 2026-12-18
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
    ruta = DIR_AS / f"{nombre_nota(nombre)}.md"
    if ruta.exists():
        return ruta, False
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(PLANTILLA_ASIGNATURA.format(nombre=nombre), encoding="utf-8")
    return ruta, True


def crear_examen(asignatura, titulo, fecha, dias, peso, hora, temas,
                 duracion, formato, clase="examen"):
    ruta = DIR_EX / f"{nombre_nota(f'{asignatura} — {titulo}')}.md"
    if ruta.exists():
        raise FileExistsError(ruta)
    bloque = ("\n" + "\n".join(f"  - {t}" for t in temas)) if temas else " []"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        "---\n"
        f"tipo: {clase}\n"
        f"titulo: {titulo}\n"
        f'asignatura: "[[{asignatura}]]"\n'
        f"fecha: {fecha.isoformat()}\n"
        f'hora: "{hora}"\n'
        f"formato: {formato}\n"
        f"peso: {peso}\n"
        f"dias: {dias}\n"
        # Para las estadísticas de Notas.md. `nota` se rellena después.
        "nota:\n"
        f"cuatrimestre: {' — '.join(cuatrimestre_actual() or ['?'])}\n"
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


# ─────────────── el índice que dibuja el grafo ─────────────────────
# Un PDF en una carpeta no es nodo de nada: el grafo se dibuja con [[enlaces]]
# y una carpeta no es un enlace. Esto convierte el árbol de carpetas en una
# cadena de notas enlazadas:
#
#     Curso → Curso — Cuatrimestre → Asignatura → cada archivo
#
# Solo se toca lo que hay entre los marcadores: lo que escribas fuera se queda.

IDX_INICIO = "<!-- INDICE:INICIO — lo genera uni.py; escribe fuera del bloque -->"
IDX_FIN = "<!-- INDICE:FIN -->"

DIR_CURSOS = BASE / "Cursos"

# Carpetas de la raíz que son del sistema, no cursos.
NO_CURSOS = {"Asignaturas", "Exámenes", "Ejemplos", "Plantillas", "sistema",
             "out", "__pycache__", "Cursos"}

# Bloques de la versión anterior, que metía todo en un «Materiales.md». Se
# borran al regenerar para no dejar dos índices dentro de la misma nota.
RE_LEGADO = re.compile(
    r"\n*(?:## Materiales\n)?<!-- MATERIALES:INICIO.*?MATERIALES:FIN -->\n*", re.S)


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


# Para saber cuál es el curso «actual» cuando dos tienen el mismo cuatrimestre:
# gana el más avanzado. Los que no estén aquí van al final.
ORDEN_CURSOS = ["Primero", "Segundo", "Tercero", "Cuarto", "Quinto", "Sexto"]


def periodo(hoy):
    """'segundo' de febrero a junio; 'primer' el resto (en verano, el que viene)."""
    return "segundo" if 2 <= hoy.month <= 6 else "primer"


def cuatrimestre_actual(hoy=None):
    """(curso, cuatrimestre) del periodo en curso, o None si no hay carpeta.

    Sale del calendario y de las carpetas que existan, así que al cambiar de
    cuatrimestre se actualiza solo: no hay nada que tocar a mano.
    """
    hoy = hoy or date.today()
    busco = periodo(hoy)
    vistos = {(c, q) for c, q, _a, _r in cursos() if busco in q.lower()}
    if not vistos:
        return None
    orden = {n: i for i, n in enumerate(ORDEN_CURSOS)}
    return max(vistos, key=lambda cq: (orden.get(cq[0], len(orden)), cq[0]))


def asignaturas_del_cuatrimestre(hoy=None):
    """(etiqueta, [asignaturas]) del cuatrimestre en curso."""
    act = cuatrimestre_actual(hoy)
    if not act:
        return None, []
    curso, cuatri = act
    return (f"{curso} · {cuatri}",
            [a for c, q, a, _r in cursos() if (c, q) == act and a])


DIAS_LECTIVOS = ["lunes", "martes", "miércoles", "jueves", "viernes"]


def tabla_horario(asignaturas):
    """Rejilla semanal de clases, en markdown.

    Vive aquí y no en el calendario: son clases fijas que ya te sabes, y como
    eventos semanales tapan lo único que hay que mirar de un vistazo.
    """
    clases = [c for c in leer_horario() if c["asignatura"] in asignaturas]
    if not clases:
        return ""
    filas = ["| Hora | " + " | ".join(d.capitalize() for d in DIAS_LECTIVOS) + " |",
             "|---|" + "---|" * len(DIAS_LECTIVOS)]
    for h in sorted({c["hora"] for c in clases}):
        celdas = []
        for i in range(len(DIAS_LECTIVOS)):
            hoy = [c for c in clases if c["hora"] == h and DIAS[c["dia"]] == i]
            celdas.append("<br>".join(
                f"[[{c['asignatura']}]]"
                + (f" ({c['tipo']})" if c["tipo"] else "")
                + (f" · {c['aula']}" if c["aula"] else "")
                for c in hoy) or "·")
        filas.append(f"| **{h}** | " + " | ".join(celdas) + " |")
    return "\n".join(filas)


def escribir_indice(ruta, titulo, tipo, cuerpo, encabezado):
    """Crea la nota del nodo si falta y le mete el bloque generado."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    texto = (RE_LEGADO.sub("\n\n", ruta.read_text(encoding="utf-8"))
             if ruta.exists() else f"---\ntipo: {tipo}\n---\n\n# {titulo}\n")
    ruta.write_text(poner_bloque(texto, IDX_INICIO, IDX_FIN, cuerpo, encabezado),
                    encoding="utf-8")


def indexar():
    """Un nodo por curso, por cuatrimestre y por asignatura, encadenados."""
    arbol = {}
    for curso, cuatri, asig, ruta in cursos():
        cuatris = arbol.setdefault(curso, {}).setdefault(cuatri, [])
        if asig is not None:
            cuatris.append((asig, ruta))

    n_asig = n_arch = 0
    for curso, cuatris in arbol.items():
        for cuatri, asigs in cuatris.items():
            # Las notas primero: el enlace tiene que apuntar al nombre real del
            # fichero, que no es el de la carpeta si esta lleva ':' o '?'.
            nombres = []
            for asig, ruta in asigs:
                enlaces = materiales_de(ruta)
                n_asig, n_arch = n_asig + 1, n_arch + len(enlaces)
                nota, _ = crear_asignatura(asig)
                escribir_indice(nota, asig, "asignatura",
                                "\n".join(enlaces) or "*(carpeta vacía)*",
                                "## Archivos")
                nombres.append(nota.stem)

            cuerpo = ("\n".join(f"- [[{n}]]" for n in nombres)
                      or "*(sin asignaturas todavía)*")
            rejilla = tabla_horario(set(nombres))
            if rejilla:
                cuerpo += "\n\n### Horario de clases\n\n" + rejilla
            escribir_indice(
                DIR_CURSOS / f"{nombre_nota(curso)} — {nombre_nota(cuatri)}.md",
                f"{curso} — {cuatri}", "cuatrimestre", cuerpo, "## Asignaturas")

        escribir_indice(
            DIR_CURSOS / f"{nombre_nota(curso)}.md", curso, "curso",
            "\n".join(f"- [[{nombre_nota(curso)} — {nombre_nota(c)}]]"
                      for c in cuatris)
            or "*(sin cuatrimestres todavía)*", "## Cuatrimestres")
    return len(arbol), n_asig, n_arch


def cmd_indice():
    n_cur, n_asig, n_arch = indexar()
    print(f"✓ {n_cur} cursos · {n_asig} asignaturas · {n_arch} archivos enlazados")


def a_tipo(v):
    """'parcial' · 'fin' · 'REC' → el tipo entero. Basta con el principio."""
    t = str(v).strip().lower()
    for opcion in TIPOS:
        if t and opcion.lower().startswith(t):
            return opcion
    raise argparse.ArgumentTypeError(f"tipo no entendido: {v!r} "
                                     f"(elige entre {', '.join(TIPOS)})")


def elegir_clase():
    print("\n¿Qué das de alta?")
    for i, c in enumerate(CLASES, 1):
        print(f"  {i}. {c.capitalize()}")
    while True:
        r = input(f"\n[1-{len(CLASES)}, Enter = examen]: ").strip()
        if not r:
            return CLASES[0]
        if r.isdigit() and 1 <= int(r) <= len(CLASES):
            return CLASES[int(r) - 1]
        print("  ↑ elige un número de la lista")


def elegir_tipo():
    print("\n¿Qué clase de examen es?")
    for i, t in enumerate(TIPOS, 1):
        print(f"  {i}. {t}")
    while True:
        r = input(f"\nTipo [1-{len(TIPOS)}, Enter = {TIPOS[0]}]: ").strip()
        if not r:
            return TIPOS[0]
        if r.isdigit() and 1 <= int(r) <= len(TIPOS):
            return TIPOS[int(r) - 1]
        print("  ↑ elige un número de la lista")


def elegir_asignatura():
    """Ofrece las del cuatrimestre en curso; escribirla es el último recurso."""
    etiqueta, asigs = asignaturas_del_cuatrimestre()
    if not asigs:
        return input("Asignatura: ").strip()
    print(f"\n{etiqueta}")
    for i, a in enumerate(asigs, 1):
        print(f"  {i}. {a}")
    print("  0. otra (escribirla)")
    while True:
        r = input(f"\nAsignatura [1-{len(asigs)}]: ").strip()
        if r == "0":
            return input("Asignatura: ").strip()
        if r.isdigit() and 1 <= int(r) <= len(asigs):
            return asigs[int(r) - 1]
        print("  ↑ elige un número de la lista")


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
    ap.add_argument("-f", "--tipo", type=a_tipo, default=None,
                    help=f"{' · '.join(TIPOS)} (basta el principio: -f fin)")
    ap.add_argument("-e", "--entrega", action="store_true",
                    help="es una entrega o trabajo, no un examen")
    a = ap.parse_args(argv)

    pide = not (a.asignatura and a.titulo and a.fecha)
    clase = "entrega" if a.entrega else (elegir_clase() if pide else "examen")
    asignatura = a.asignatura or elegir_asignatura()
    titulo = a.titulo or input(
        "Entrega (p. ej. Práctica 3): " if clase == "entrega"
        else "Examen (p. ej. Parcial 2): ").strip()
    # A una entrega no le pega un «Parcial»: el formato solo aplica a exámenes.
    tipo = "Entrega" if clase == "entrega" else (
        a.tipo or (elegir_tipo() if pide else TIPOS[0]))
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
                            a.duracion, tipo, clase)
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


def huella_examenes():
    """Qué notas de examen hay. Solo los nombres, no las fechas de cambio:
    el propio sync reescribe la rampa dentro de cada nota, así que mirar el
    mtime daría «ha cambiado» siempre y repetiríamos la pasada cada vez."""
    if not DIR_EX.is_dir():
        return ()
    return tuple(sorted(p.name for p in DIR_EX.glob("*.md")))


def cmd_sync():
    """Regenera todo, y repite si algo cambió mientras trabajábamos.

    El .path de systemd no encola disparos: si borras una nota mientras el
    sync anterior está en marcha, ese cambio no genera un aviso nuevo y se
    quedaría sin procesar hasta el ciclo de 15 min. Comparando la foto de
    Exámenes/ antes y después lo recogemos en la misma pasada.
    """
    # Un solo sync a la vez. `uni nuevo` lanza el suyo y el .path de systemd
    # lanza otro por la misma nota: si se solapan, los dos intentan escribir
    # los mismos eventos y CalDAV devuelve 409 Conflict. Esperamos en vez de
    # saltarnos el turno, para no perder el cambio que disparó esta pasada.
    ruta = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "uni-sync.lock"
    with open(ruta, "w") as cerrojo:
        try:
            fcntl.flock(cerrojo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("· hay otro sync en marcha; espero mi turno")
            fcntl.flock(cerrojo, fcntl.LOCK_EX)

        antes = huella_examenes()
        _sync()
        if huella_examenes() != antes:
            print("· Exámenes/ cambió durante el sync; repito")
            _sync()


def _sync():
    ex, sem, hor = leer_examenes(), leer_semanal(), leer_horario()
    if not ex:
        print("No hay notas de examen en Exámenes/ (¿frontmatter 'tipo: examen'?)")
    tot_hechas = 0
    for e in ex:
        tot_hechas += inyectar_rampa(e)
    ics, n = construir_ics(ex, sem, hor)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(ics, encoding="utf-8")
    print(f"✓ {len(ex)} exámenes · {n} sesiones · {len(hor)} clases · "
          f"{len(sem)} bloques semanales · {tot_hechas} tareas conservadas")
    print(f"✓ {SALIDA}")
    n_cur, n_asig, n_arch = indexar()
    if n_cur:
        print(f"✓ {n_cur} cursos · {n_asig} asignaturas · {n_arch} archivos enlazados")
    exportar_calendario()


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


def exportar_calendario(silencioso=False):
    """Vuelca el .ics en el calendario del sistema, si hay uno configurado.

    El destino lo fija instalar.sh dentro del comando `uni`. Sin él esto no
    hace nada: el .ics y GNOME Calendar siguen funcionando igual.
    """
    destino = os.environ.get("UNI_GCAL_CALENDARIO", "").strip()
    if not destino:
        return
    try:
        import calendario                   # perezoso: necesita EDS y GTK
        n, c, i, f = calendario.exportar(SALIDA, destino,
                                         os.environ.get("UNI_GCAL_CUENTA") or None)
        if not silencioso:
            print(f"✓ {destino}: {n} nuevos · {c} actualizados · {i} retirados"
                  + (f" · ⚠ {f} fallaron" if f else ""))
    except Exception as e:                  # nunca debe tumbar el sync
        print(f"  ! calendario «{destino}»: {e}", file=sys.stderr)


def cmd_gcal(argv):
    ap = argparse.ArgumentParser(
        prog="uni gcal",
        description="Vuelca el plan en un calendario del sistema. Si es de una "
                    "cuenta de Google conectada en GNOME, sube a Google.")
    ap.add_argument("calendario", nargs="?",
                    default=os.environ.get("UNI_GCAL_CALENDARIO"),
                    help="nombre del calendario destino")
    ap.add_argument("-c", "--cuenta", default=os.environ.get("UNI_GCAL_CUENTA"),
                    help="cuenta, si el nombre se repite en varias")
    ap.add_argument("-l", "--listar", action="store_true",
                    help="enseña los calendarios disponibles y sale")
    a = ap.parse_args(argv)

    import calendario
    if a.listar or not a.calendario:
        print("Calendarios del sistema:\n")
        for nombre, cuenta in calendario.calendarios():
            print(f"  {nombre:<38} {cuenta or ''}")
        if not a.listar:
            sys.exit("\n✗ dime a cuál: uni gcal \"Universidad\" -c tu@correo")
        return
    try:
        n, c, i, f = calendario.exportar(SALIDA, a.calendario, a.cuenta)
    except LookupError as e:
        sys.exit(f"✗ {e}")
    print(f"✓ {a.calendario}: {n} nuevos · {c} actualizados · {i} retirados"
          + (f" · ⚠ {f} fallaron" if f else ""))


# ─────────────────────── chequeo del sistema ───────────────────────
# Ayer un timer se quedó «active (elapsed)» y estuvo 21 h sin sincronizar sin
# que nada avisara. Con seis unidades, un remoto de rclone, un calendario de
# EDS y un atajo de GNOME hay demasiadas formas de fallar en silencio.

def _cmd(*args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _unidad(nombre):
    """(ok, detalle) de un timer o .path de systemd de usuario."""
    cod, estado = _cmd("systemctl", "--user", "is-active", nombre)
    if cod != 0:
        return False, f"{estado or 'inactiva'} — systemctl --user enable --now {nombre}"
    if nombre.endswith(".timer"):
        _, prox = _cmd("systemctl", "--user", "show", nombre,
                       "-p", "NextElapseUSecRealtime", "--value")
        if not prox:
            return False, "activa pero SIN próxima ejecución (timer consumido)"
        return True, f"próxima: {prox}"
    return True, estado


def cmd_estado():
    fallos = []

    def linea(ok, que, detalle=""):
        print(f"  {'✓' if ok else '✗'} {que}" + (f" — {detalle}" if detalle else ""))
        if not ok:
            fallos.append(que)

    print("\n\033[1mVault\033[0m")
    linea(SALIDA.exists(), "calendario generado",
          f"{len(leer_examenes())} exámenes · {len(leer_horario())} clases")
    if SALIDA.exists():
        edad = (datetime.now() - datetime.fromtimestamp(SALIDA.stat().st_mtime)).days
        linea(edad < 2, "el .ics está fresco", f"regenerado hace {edad} días")

    print("\n\033[1mAutomatismos\033[0m")
    for u in ("uni-hoy.timer", "uni-drive.timer", "uni-vigila.path"):
        ok, det = _unidad(u)
        linea(ok, u, det)

    print("\n\033[1mGoogle Drive\033[0m")
    cod, _ = _cmd("rclone", "version")
    if cod != 0:
        linea(False, "rclone", "no instalado")
    else:
        remoto = os.environ.get("UNI_DRIVE_REMOTO", "drive")
        _, lst = _cmd("rclone", "listremotes")
        hay = f"{remoto}:" in lst.split()
        linea(hay, f"remoto {remoto}:", "" if hay else "créalo con rclone config")
        marca = Path.home() / ".local/state/uni/drive-inicializado"
        linea(marca.exists(), "línea base de bisync",
              "" if marca.exists() else "lánzalo con uni-drive")

    print("\n\033[1mCalendario del sistema\033[0m")
    destino = os.environ.get("UNI_GCAL_CALENDARIO", "").strip()
    if not destino:
        print("  · sin calendario destino (opcional)")
    else:
        try:
            import calendario
            hay = [(n, c) for n, c in calendario.calendarios() if n == destino]
            linea(bool(hay), f"calendario «{destino}»",
                  hay[0][1] if hay else "no lo encuentro; uni gcal --listar")
        except Exception as e:
            linea(False, f"calendario «{destino}»", str(e))

    print("\n\033[1mEscritorio\033[0m")
    _, atajo = _cmd("gsettings", "get",
                    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"
                    "/org/gnome/settings-daemon/plugins/media-keys/"
                    "custom-keybindings/uni-nuevo/", "binding")
    linea(bool(atajo and atajo != "''"), "atajo de teclado",
          atajo.strip("'") or "./instalar.sh atajo")

    print()
    if fallos:
        print(f"\033[33m{len(fallos)} cosa(s) que revisar.\033[0m\n")
        sys.exit(1)
    print("\033[32mTodo en orden.\033[0m\n")


def cmd_ventana():
    """La ventanita de alta rápida. Es lo que cuelga de Ctrl+Shift+Ñ."""
    try:
        import ventana                      # perezoso: la CLI no necesita GTK
    except ImportError as e:
        sys.exit(f"✗ falta PyGObject/GTK4: {e}\n"
                 "  En Fedora: sudo dnf install python3-gobject gtk4 libadwaita")
    sys.exit(ventana.abrir(sys.modules[__name__]))


def cmd_fisica(argv):
    """Espejo del calendario oficial de Física. Vive en su propio módulo."""
    import fisica                            # perezoso: solo lo usa este comando
    sys.exit(fisica.main(argv or ["sync"]))


def cmd_ull(argv):
    """Espejo del calendario oficial de la ESIT. Vive en su propio módulo."""
    import ull                              # perezoso: solo lo usa este comando
    sys.exit(ull.main(argv or ["sync"]))


CMDS = {"sync": cmd_sync, "hoy": cmd_hoy, "proximos": cmd_proximos,
        "notificar": cmd_notificar, "ventana": cmd_ventana,
        "indice": cmd_indice, "estado": cmd_estado}

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "hoy"
    if a == "nuevo":
        cmd_nuevo(sys.argv[2:])
    elif a == "gcal":
        cmd_gcal(sys.argv[2:])
    elif a == "ull":
        cmd_ull(sys.argv[2:])
    elif a == "fisica":
        cmd_fisica(sys.argv[2:])
    elif a in CMDS:
        CMDS[a]()
    else:
        sys.exit(__doc__)
