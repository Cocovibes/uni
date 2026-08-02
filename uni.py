#!/usr/bin/env python3
"""
uni.py — motor del vault. Lee las notas de Exámenes/ y Asignaturas/ y:
  · escribe el plan de estudio (checkboxes) dentro de cada nota de examen
  · genera out/uni-estudio.ics (lo lee GNOME Calendar en vivo)
  · saca el plan de hoy por terminal / notificación

    uni sync        regenera todo
    uni hoy         plan de hoy
    uni proximos    siguientes 14 días
    uni notificar   notificación de escritorio (la lanza el timer de systemd)

La fuente de verdad son las notas. Este script nunca las inventa: solo
rellena el bloque entre RAMPA:INICIO y RAMPA:FIN, conservando lo marcado.
"""

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

# (días antes, nombre, minutos, qué hacer)
RAMPA = [
    (14, "Inventario", 30,
     "listar temas, puntuar confianza 0-3, bajar exámenes de otros años"),
    (10, "Ataque a lo peor", 90,
     "los 2 temas más flojos, 3 problemas de cada uno, con apuntes"),
    (7, "Barrido a libro cerrado", 90,
     "1 problema de CADA tema, cronometrado, sin apuntes — es el diagnóstico"),
    (5, "Huecos", 90,
     "solo lo que falló en D-7, hasta que salga sin mirar"),
    (3, "Simulacro", None,
     "examen entero de otro año, condiciones reales, sin corregir hoy"),
    (2, "Corrección", 60,
     "corregir el simulacro, repasar solo los errores, anotarlos en Trampas"),
    (1, "Formulario de memoria", 45,
     "escribir el formulario de memoria en un folio, comparar, dormir 8h"),
]

DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
        "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}


def rampa_para(peso):
    if peso >= 35:
        return RAMPA
    if peso >= 15:
        return [s for s in RAMPA if s[0] in (10, 7, 5, 3, 1)]
    return [s for s in RAMPA if s[0] in (5, 3, 1)]


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
    for dias, nombre, mins, tarea in rampa_para(ex["peso"]):
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
        for dias, nombre, mins, tarea in rampa_para(ex["peso"]):
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
        for dias, nombre, mins, tarea in rampa_para(ex["peso"]):
            cuando = ex["fecha"] - timedelta(days=dias)
            if desde <= cuando <= hasta:
                out.append((cuando, dias, ex["asignatura"], nombre,
                            mins or ex["duracion"], tarea))
        if desde <= ex["fecha"] <= hasta:
            out.append((ex["fecha"], 0, ex["asignatura"], "🎓 EXAMEN",
                        ex["duracion"], "Suerte."))
    return sorted(out)


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


CMDS = {"sync": cmd_sync, "hoy": cmd_hoy, "proximos": cmd_proximos,
        "notificar": cmd_notificar}

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "hoy"
    if a not in CMDS:
        sys.exit(__doc__)
    CMDS[a]()
