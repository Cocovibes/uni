#!/usr/bin/env python3
"""calendario.py — vuelca out/uni-estudio.ics en un calendario del sistema.

Escribe a través de Evolution Data Server. Si el calendario elegido es de una
cuenta de Google ya conectada en GNOME, EDS sube los eventos por CalDAV y
aparecen en Google Calendar y en el móvil. No hay que autorizar nada nuevo ni
crear credenciales: se reutiliza la sesión que ya tiene el escritorio.

Los UID que genera uni.py son estables y acaban todos en @uni.local, y de ahí
salen las tres garantías:

  · reexportar actualiza los eventos en vez de duplicarlos;
  · los que ya no están en el .ics se borran del calendario;
  · nunca se toca un evento que no haya creado uni — el sufijo del UID es lo
    que distingue los nuestros del resto de tu calendario.
"""

import gi

gi.require_version("EDataServer", "1.2")
gi.require_version("ECal", "2.0")
gi.require_version("ICalGLib", "3.0")

import sys  # noqa: E402

from gi.repository import ECal, EDataServer, GLib, ICalGLib  # noqa: E402

SUFIJO = "@uni.local"
ESPERA = 30          # segundos que damos a EDS para conectar


def _cuenta_de(registro, fuente):
    """La cuenta a la que cuelga un calendario ('En este equipo', un correo…)."""
    padre = fuente.get_parent()
    if not padre:
        return None
    ref = registro.ref_source(padre)
    return ref.get_display_name() if ref else None


def calendarios():
    """[(nombre, cuenta)] de todos los calendarios que ve el sistema."""
    reg = EDataServer.SourceRegistry.new_sync(None)
    return sorted((s.get_display_name(), _cuenta_de(reg, s))
                  for s in reg.list_sources(EDataServer.SOURCE_EXTENSION_CALENDAR))


def _cliente(nombre, cuenta=None):
    reg = EDataServer.SourceRegistry.new_sync(None)
    cands = [s for s in reg.list_sources(EDataServer.SOURCE_EXTENSION_CALENDAR)
             if s.get_display_name() == nombre]
    if cuenta:
        cands = [s for s in cands if _cuenta_de(reg, s) == cuenta]
    if not cands:
        raise LookupError(f"no hay ningún calendario «{nombre}»"
                          + (f" en {cuenta}" if cuenta else ""))
    if len(cands) > 1:
        cuentas = ", ".join(sorted(_cuenta_de(reg, s) or "?" for s in cands))
        raise LookupError(f"hay varios «{nombre}» ({cuentas}); "
                          "elige uno con --cuenta")
    return ECal.Client.connect_sync(cands[0], ECal.ClientSourceType.EVENTS,
                                    ESPERA, None)


def _eventos(texto):
    """{uid: componente} de todos los VEVENT de un .ics."""
    vcal = ICalGLib.Component.new_from_string(texto)
    out, ev = {}, vcal.get_first_component(ICalGLib.ComponentKind.VEVENT_COMPONENT)
    while ev is not None:
        out[ev.get_uid()] = ev
        ev = vcal.get_next_component(ICalGLib.ComponentKind.VEVENT_COMPONENT)
    return out


def exportar(ics, nombre, cuenta=None):
    """Deja el calendario igual que el .ics. Devuelve (nuevos, cambiados, idos)."""
    cli = _cliente(nombre, cuenta)
    quiero = _eventos(ics.read_text(encoding="utf-8")) if ics.exists() else {}

    ok, hay = cli.get_object_list_sync("#t", None)
    mios = {c.get_uid() for c in (hay or []) if (c.get_uid() or "").endswith(SUFIJO)}

    # Cada evento va por su cuenta: si uno falla —red, permisos, un objeto que
    # ya no está— el resto tiene que seguir. Antes una sola excepción abortaba
    # la exportación entera y dejaba el calendario a medias sin avisar.
    nuevos = cambiados = idos = fallos = 0

    for uid, ev in quiero.items():
        try:
            if uid in mios:
                cli.modify_object_sync(ev, ECal.ObjModType.ALL,
                                       ECal.OperationFlags.NONE, None)
                cambiados += 1
            else:
                try:
                    cli.create_object_sync(ev, ECal.OperationFlags.NONE, None)
                    nuevos += 1
                except GLib.Error as e:
                    # Otro sync lo creó entre que listamos y escribimos. No es
                    # un error: el evento tiene que quedar como dice el .ics.
                    if "already exists" not in e.message.lower() \
                            and "ya existe" not in e.message.lower():
                        raise
                    cli.modify_object_sync(ev, ECal.ObjModType.ALL,
                                           ECal.OperationFlags.NONE, None)
                    cambiados += 1
        except GLib.Error as e:
            fallos += 1
            print(f"  ! no se pudo escribir {uid}: {e.message}", file=sys.stderr)

    # Un examen borrado —y con él sus sesiones de estudio— desaparece del
    # calendario, porque sus UID dejan de estar en el .ics.
    for uid in mios - set(quiero):
        try:
            cli.remove_object_sync(uid, None, ECal.ObjModType.ALL,
                                   ECal.OperationFlags.NONE, None)
            idos += 1
        except GLib.Error as e:
            if "not found" in e.message.lower() or "no encontrado" in e.message.lower():
                idos += 1          # ya no estaba: es justo lo que queríamos
            else:
                fallos += 1
                print(f"  ! no se pudo quitar {uid}: {e.message}", file=sys.stderr)

    return nuevos, cambiados, idos, fallos
