#!/usr/bin/env python3
"""ventana.py — la ventanita de alta rápida (GTK4 + libadwaita).

No tiene lógica propia: pide los mismos datos que `uni nuevo` y llama a las
mismas funciones de uni.py. Se abre con `uni ventana`, que es lo que cuelga del
atajo de teclado (Ctrl+Shift+Ñ).

Recibe el módulo uni por parámetro en vez de importarlo, para no montar un
import circular ni una segunda copia del motor.
"""

from datetime import date, timedelta

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

APP_ID = "org.uni.AltaExamen"
OTRA = "Otra…"


class Alta:
    def __init__(self, app, uni):
        self.uni = uni
        self.win = Adw.ApplicationWindow(application=app, title="Examen nuevo")
        self.win.set_default_size(440, -1)

        self.btn_cancelar = Gtk.Button(label="Cancelar")
        self.btn_cancelar.connect("clicked", lambda *_: self.win.close())
        self.btn_guardar = Gtk.Button(label="Guardar")
        self.btn_guardar.add_css_class("suggested-action")
        self.btn_guardar.connect("clicked", lambda *_: self.guardar())

        cabecera = Adw.HeaderBar()
        cabecera.pack_start(self.btn_cancelar)
        cabecera.pack_end(self.btn_guardar)

        self.caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                            margin_top=12, margin_bottom=12,
                            margin_start=12, margin_end=12)
        marco = Gtk.ScrolledWindow(child=self.caja, propagate_natural_height=True,
                                   max_content_height=620,
                                   hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.toasts = Adw.ToastOverlay(child=marco)

        vista = Adw.ToolbarView()
        vista.add_top_bar(cabecera)
        vista.set_content(self.toasts)
        self.win.set_content(vista)

        self._formulario()

        teclas = Gtk.EventControllerKey()
        teclas.connect("key-pressed", self._tecla)
        self.win.add_controller(teclas)
        self.win.present()

    # ───────────────────────── formulario ──────────────────────────

    def _formulario(self):
        grupo = Adw.PreferencesGroup()

        # La asignatura se elige, no se escribe: las del cuatrimestre en curso
        # salen del calendario y de las carpetas, así que al cambiar de
        # cuatrimestre la lista cambia sola.
        etiqueta, self.asigs = self.uni.asignaturas_del_cuatrimestre()
        self.f_asig = Adw.ComboRow(title="Asignatura")
        self.f_asig.set_subtitle(etiqueta or "sin cuatrimestre en curso")
        self.f_asig.set_model(Gtk.StringList.new(self.asigs + [OTRA]))
        self.f_asig.connect("notify::selected", self._cambia_asignatura)

        # Solo se muestra si eliges «Otra…».
        self.f_otra = Adw.EntryRow(title="¿Cuál?", visible=not self.asigs)

        self.f_examen = Adw.EntryRow(title="Examen (p. ej. Parcial 2)")
        self.f_fecha = Adw.EntryRow(title="Fecha (DD/MM o AAAA-MM-DD)")
        self.f_fecha.add_suffix(self._boton_calendario())

        self.f_tipo = Adw.ComboRow(title="Tipo")
        self.f_tipo.set_model(Gtk.StringList.new(self.uni.TIPOS))

        self.f_dias = Adw.SpinRow.new_with_range(1, 30, 1)
        self.f_dias.set_title("Días de estudio")
        self.f_dias.set_subtitle("una sesión por día, D-N … D-1")
        self.f_dias.set_value(self.uni.DIAS_ESTUDIO_DEF)

        for f in (self.f_asig, self.f_otra, self.f_examen, self.f_tipo,
                  self.f_fecha, self.f_dias):
            grupo.add(f)

        mas = Adw.ExpanderRow(title="Más opciones")
        self.f_hora = Adw.EntryRow(title="Hora del examen")
        self.f_hora.set_text("09:00")
        self.f_temas = Adw.EntryRow(title="Temas (separados por comas)")
        self.f_duracion = Adw.SpinRow.new_with_range(30, 300, 15)
        self.f_duracion.set_title("Duración del examen")
        self.f_duracion.set_subtitle("minutos")
        self.f_duracion.set_value(120)
        # Aquí abajo porque casi nunca se sabe el peso exacto, y con `dias`
        # explícito ya no decide nada: solo manda si pones `dias: auto`.
        self.f_peso = Adw.SpinRow.new_with_range(0, 100, 5)
        self.f_peso.set_title("Peso")
        self.f_peso.set_subtitle("% de la nota, si lo sabes")
        self.f_peso.set_value(30)
        for f in (self.f_hora, self.f_temas, self.f_duracion, self.f_peso):
            mas.add_row(f)
        grupo.add(mas)

        self.caja.append(grupo)

        # Enter en cualquier campo = Guardar.
        for f in (self.f_otra, self.f_examen, self.f_fecha,
                  self.f_hora, self.f_temas):
            f.connect("entry-activated", lambda *_: self.guardar())
        (self.f_otra if self.f_otra.get_visible() else self.f_examen).grab_focus()

    def _cambia_asignatura(self, *_):
        """El campo libre solo aparece si has elegido «Otra…»."""
        self.f_otra.set_visible(self.asignatura() is None)
        if self.f_otra.get_visible():
            self.f_otra.grab_focus()

    def asignatura(self):
        """La elegida en el desplegable, o None si toca escribirla."""
        if not self.asigs:
            return None
        sel = self.f_asig.get_selected()
        return None if sel >= len(self.asigs) else self.asigs[sel]

    def _boton_calendario(self):
        cal = Gtk.Calendar()
        usar = Gtk.Button(label="Usar esta fecha")
        usar.add_css_class("suggested-action")
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       margin_top=6, margin_bottom=6,
                       margin_start=6, margin_end=6)
        caja.append(cal)
        caja.append(usar)
        pop = Gtk.Popover(child=caja)
        boton = Gtk.MenuButton(icon_name="x-office-calendar-symbolic",
                               popover=pop, valign=Gtk.Align.CENTER)
        boton.add_css_class("flat")

        def elegir(*_):
            d = cal.get_date()
            self.f_fecha.set_text(f"{d.get_year():04d}-{d.get_month():02d}-"
                                  f"{d.get_day_of_month():02d}")
            pop.popdown()

        usar.connect("clicked", elegir)
        return boton

    # ─────────────────────────── guardar ───────────────────────────

    def guardar(self):
        asig = self.asignatura() or self.f_otra.get_text().strip()
        examen = self.f_examen.get_text().strip()
        fecha_txt = self.f_fecha.get_text().strip()
        if not (asig and examen and fecha_txt):
            return self._aviso("Faltan la asignatura, el examen o la fecha.")
        try:
            fecha = self.uni.a_fecha_flexible(fecha_txt)
            hora = self.uni.a_hora(self.f_hora.get_text())
        except ValueError as e:
            return self._aviso(str(e))
        if fecha < date.today():
            return self._aviso(f"Esa fecha ya pasó ({fecha:%d/%m/%Y}).")

        dias = int(self.f_dias.get_value())
        peso = int(self.f_peso.get_value())
        duracion = int(self.f_duracion.get_value())
        temas = [t.strip() for t in self.f_temas.get_text().split(",") if t.strip()]

        tipo = self.uni.TIPOS[self.f_tipo.get_selected()]
        try:
            self.uni.crear_examen(asig, examen, fecha, dias, peso, hora,
                                  temas, duracion, tipo)
        except FileExistsError:
            return self._aviso(f"Ya existe «{asig} — {examen}».")
        except OSError as e:
            return self._aviso(f"No se pudo escribir la nota: {e}")
        self.uni.crear_asignatura(asig)
        self.uni.cmd_sync()
        self._resumen(asig, examen, fecha, dias, peso, duracion)

    def _aviso(self, texto):
        self.toasts.add_toast(Adw.Toast(title=texto, timeout=4))

    def _resumen(self, asig, examen, fecha, dias, peso, duracion):
        """Ya está guardado: enseñar qué se ha metido en el calendario."""
        plan = self.uni.plan_de({"fecha": fecha, "dias": dias, "peso": peso,
                                 "duracion": duracion})
        while (hijo := self.caja.get_first_child()) is not None:
            self.caja.remove(hijo)

        grupo = Adw.PreferencesGroup(
            title=f"✓ {asig} — {examen}",
            description=f"{fecha:%A %d/%m/%Y} · {peso}% · {len(plan)} sesiones "
                        f"en el calendario")
        for d, nombre, mins, tarea in plan:
            cuando = fecha - timedelta(days=d)
            fila = Adw.ActionRow(
                title=f"D-{d} · {cuando:%a %d/%m} — {nombre}",
                subtitle=f"{tarea} ({mins or duracion} min)")
            fila.set_subtitle_lines(2)
            grupo.add(fila)
        self.caja.append(grupo)

        self.btn_guardar.set_visible(False)
        self.btn_cancelar.set_label("Cerrar")
        self.btn_cancelar.add_css_class("suggested-action")
        self.btn_cancelar.grab_focus()

    def _tecla(self, _ctrl, keyval, _code, _estado):
        if keyval == Gdk.KEY_Escape:
            self.win.close()
            return True
        return False


def abrir(uni):
    """Punto de entrada desde `uni ventana`."""
    app = Adw.Application(application_id=APP_ID,
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda a: Alta(a, uni))
    return app.run([])
