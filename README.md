# uni — vault de estudio con fricción cero

Un vault de Obsidian que **es a la vez el motor del calendario**. Apuntas la
fecha de un examen y aparece solo, sin tocar nada más:

- el evento en el **calendario del sistema** (GNOME Calendar, enlazado en vivo
  — no es una importación);
- una fila en el **surtidor** del Panel, ordenable por dificultad, por lo que
  falta o por peso;
- una **notificación de escritorio a las 08:30** con lo que toca hoy.

**El sistema no inventa tareas.** Solo hay obligaciones con fecha oficial:
exámenes, prácticas y entregas. Si no lo ha puesto la ESIT o un profesor, no
está aquí.

---

## El bucle entero

**Ctrl + Shift + Ñ**, desde donde estés. Se abre una ventanita, rellenas
asignatura / examen / fecha, le das a **Guardar** y ya está: la nota del examen
creada, la nota de la asignatura también si no existía (para que el `[[enlace]]`
no quede roto), y el evento en el calendario del sistema.

**La asignatura no se escribe, se elige.** El desplegable trae las del
cuatrimestre en curso, que sale de dos cosas que ya existen: el mes de hoy y
las carpetas de `Curso/Cuatrimestre/`. Septiembre-enero → primer cuatrimestre,
febrero-junio → segundo, verano → el que viene; y si dos cursos tienen ese
cuatrimestre, gana el más avanzado. Al cambiar de cuatrimestre la lista cambia
sola — no hay nada que configurar ni ninguna lista que mantener. Queda `Otra…`
para lo que se salga del plan.

`uni nuevo` sin argumentos ofrece la misma lista numerada en la terminal.

Lo mismo desde la terminal, si prefieres:

```bash
uni nuevo "Cálculo II" "Parcial 2" 13/11
```

Sin argumentos (`uni nuevo` a secas) los pregunta uno a uno.

```bash
uni nuevo "Ingeniería Térmica" Final 2027-06-11 \
          --temas "Ciclos,Transferencia de calor" --peso 60
```

| Opción | Para qué | Def. |
|--------|----------|------|
| `--tipo` | `Parcial` · `Final` · `Recuperación` · `Test`. Basta el principio: `-f fin` | Parcial |
| `--hora` | hora del examen | 09:00 |
| `--temas` | separados por comas | — |
| `--duracion` | minutos de examen | 120 |
| `--peso` | % de la nota final | 30 |
| `--entrega` | es un trabajo, no un examen | — |

El **tipo** se elige de una lista, nunca se escribe. El **peso** vive en «Más
opciones» a propósito: rara vez se sabe el porcentaje exacto, y no sale en el
título del evento. Sí se usa para **estimar la dificultad** mientras no la
pongas a mano.

La fecha admite `AAAA-MM-DD` y `DD/MM` (sin año = la próxima vez que ocurra).

**La fuente de verdad son las notas.** No hay base de datos, ni YAML aparte, ni
estado escondido. Lo que dice el frontmatter es lo que hay — y se puede editar a
mano en cualquier momento; `uni sync` recoge el cambio.

```yaml
---
tipo: examen
asignatura: "[[Cálculo II]]"
fecha: 2026-11-13
peso: 40
dificultad: 4            # 1-5, opcional; vacío = estimada desde el peso
temas: [Series, Derivadas parciales]
duracion_examen: 120
---
```

## Entregas

Lo mismo vale para un trabajo: en la ventana, el selector de arriba cambia de
**Examen** a **Entrega**; en la terminal, `uni nuevo -e`. El evento sale como
`📦 ENTREGA — Asignatura (Práctica 3)` y el tipo (Parcial/Final) desaparece,
que a una entrega no le pega.

## El surtidor

`Panel.md` es una vista tipo base de datos sobre `Exámenes/`: una fila por
obligación, y las cabeceras de Dataview reordenan por lo que falta, por
dificultad, por peso o por asignatura. Hay tres cortes hechos —próximas,
por dificultad y esta semana— más las pasadas a las que les falta la nota.

**`dificultad: 1-5`** manda si la pones; si la dejas vacía se estima desde el
`peso` (≥50 → 5, ≥35 → 4, ≥20 → 3, resto 2) solo para que la columna no salga
en blanco. La buena es la tuya: hay asignaturas de 20 % que cuestan más que un
final de 50 %.

## Instalación

```bash
git clone https://github.com/Cocovibes/uni.git ~/uni
cd ~/uni && ./instalar.sh
```

Sin sudo. El instalador es idempotente y hace:

- comprueba `python3` + PyYAML;
- baja los 3 plugins de Obsidian **verificando el `id` del manifest** (ver abajo);
- instala el comando `uni` en `~/.local/bin`;
- registra **Ctrl+Shift+Ñ** como atajo de GNOME para la ventanita de alta rápida
  (`./instalar.sh atajo` para solo eso; `UNI_ATAJO='<Control><Shift>e'` para
  cambiar la tecla);
- activa el timer de usuario de systemd para el aviso de las 08:30;
- activa un `.path` que vigila `Exámenes/`: crear o borrar una nota se procesa
  en segundos, sin esperar al siguiente sync;
- si rclone ya está configurado, activa el timer de sincronización con Drive;
- enlaza el `.ics` con GNOME Calendar vía Evolution Data Server;
- si Obsidian es flatpak, le da acceso a la carpeta del vault.

Después: abre la carpeta como vault en Obsidian. Se abre en **Panel**.

```
Ctrl+Shift+Ñ   la ventanita de alta rápida
uni            plan de hoy
uni nuevo      alta de un examen (nota + asignatura + calendario)
uni ventana    la misma ventanita, a mano
uni proximos   siguientes 14 días
uni sync       regenera notas + calendario + índice del grafo
uni indice     solo rehace los nodos curso/cuatrimestre/asignatura
uni estado     comprueba que todas las piezas siguen vivas
uni ull        espeja el calendario oficial de exámenes de la ESIT
uni fisica     lo mismo para la Sección de Física
uni-drive      sincroniza con Google Drive (si lo has configurado)
```

## Exámenes oficiales de Física

`uni fisica sync` espeja el calendario OFICIAL de la Sección de Física en un
calendario propio (morado), aparte del de estudio. Hermano de `uni ull`, que
hace lo mismo para la ESIT — van separados porque cada centro publica de una
forma distinta y no comparten una línea de parseo: la ESIT cuelga `.docx` con
una tabla de columnas fijas; Física cuelga **un PDF** con una rejilla visual.
Solo necesita `curl` y `pdftotext`: ni rclone ni credenciales.

**El curso no se puede leer del PDF.** Que una asignatura sea de 1º o de 2º lo
dice el COLOR de la celda, y el color no sobrevive a la extracción de texto —
el único texto es «1º Y 2º GRADUADO EN FÍSICA», que agrupa dos cursos. Por eso
no se filtra por curso sino por TUS asignaturas: cada nota declara con qué
nombre la llama el calendario oficial,

```yaml
oficial: "M. MAT. IV"
```

y solo se espejan las que casen. Sale mejor que adivinar el curso: si te queda
una asignatura de otro año, también aparece. Sin ninguna `oficial:`, el paso
del instalador se salta solo.

```
uni fisica ver    los exámenes que detecta
uni fisica diff   qué ha cambiado desde la última vez
uni fisica sync   regenera out/uni-fisica.ics (lo hace el timer los lunes)
```

Dos cosas que costó acertar en el parseo, y que están comentadas en el código:
el ancla de cada celda es la HORA y no el offset de la cabecera (cortar por
columnas partía un `15:00` en `5:00`), y hay semanas que cruzan el cambio de
mes —«LUNES 28 … JUEVES 1»— sin que el PDF vuelva a etiquetarlo.

## Notas y estadísticas

Pon `nota: 6.5` en el frontmatter de un examen y [[Notas]] se rellena solo:
media por asignatura ordenada **de peor a mejor** (dónde flojeas), suspensos y
raspados, media por cuatrimestre, y los exámenes ya pasados a los que se te
olvidó ponerles nota.

## Exámenes oficiales de la ESIT

La ESIT no publica un `.ics`: cuelga un puñado de `.docx` en una carpeta
pública de Drive, uno por mes de exámenes. `uni ull` los baja, los parsea y
escribe **`out/uni-ull.ics`**, que se enlaza con GNOME Calendar como un
calendario aparte, **«Uni — Exámenes ULL»** (naranja), hermano del rojo de
estudio.

Es un **espejo de solo lectura**: no escribe notas en `Exámenes/` ni toca tu
plan de estudio. Las fechas oficiales las pone la ESIT; el plan de estudio lo
decides tú dando el examen de alta con Ctrl+Shift+Ñ.

```
uni ull        baja, regenera el .ics y avisa si algo cambió
uni ull ver    lista por terminal los exámenes detectados
uni ull diff   solo dice si hay cambios (sale 1 si los hay)
```

El calendario del curso se publica **entero de una vez**, así que el timer
semanal (`uni-ull.timer`, lunes 09:00) no busca exámenes nuevos: busca
**rectificaciones**. Si la ESIT mueve una fecha o cambia un aula, salta una
notificación diciendo exactamente qué se movió. Cuando una asignatura sale de
una fecha y entra en otra, lo reporta como `~ MOVIDO`, no como un examen
borrado y otro nuevo.

Solo mira tu curso (`2` por defecto) y todas las convocatorias. Se cambia sin
tocar el código:

```bash
UNI_ULL_CURSO=3 uni ull ver          # otro curso
UNI_ULL_CARPETA=<id> uni ull         # si la ESIT mueve la carpeta de Drive
```

Ojo con la columna **`C`** del `.docx`: no es la convocatoria, es el
**cuatrimestre** de la asignatura. La convocatoria la marca el mes del fichero.

`out/uni-ull.ics` es la **única excepción** del `.gitignore` de `out/`: se
versiona a propósito para tener una URL estable a la que suscribirse desde el
móvil. Son fechas ya públicas. `uni-estudio.ics` no se publica nunca.

## El grafo

Un PDF suelto en una carpeta no es nodo de nada: el grafo de Obsidian se
dibuja con los `[[enlaces]]`, y una carpeta no es un enlace. Por eso `uni sync`
recorre `Curso/Cuatrimestre/Asignatura/` y convierte ese árbol en notas
enlazadas — una por curso y una por cuatrimestre en `Cursos/`, y los archivos
colgando de la nota de cada asignatura:

```
Primero ─→ Primero — Segundo Cuatrimestre ─→ CC2 ─→ tema4.pdf
                                          ─→ FB1 ─→ …
Segundo ─→ Segundo — Primer Cuatrimestre  ─→ (vacío hasta septiembre)

Examen ──→ Asignatura        (por el frontmatter `asignatura:`)
```

Los cuatrimestres llevan el curso en el nombre porque «Primer Cuatrimestre»
se repite en cada año y en Obsidian los nombres de nota son únicos.

Como todo lo que genera este motor, va entre marcadores
(`MATERIALES:INICIO`/`FIN`): lo que escribas fuera se conserva.

Para verlos hay que decirle a Obsidian que enseñe los adjuntos —
`.obsidian/graph.json` con `showAttachments: true`, y `showUnsupportedFiles`
en `app.json` para que `.xlsx`, `.docx` y `.zip` existan siquiera.

Se reindexa solo: en el `uni sync` diario de las 08:30, y después de cada
sincronización con Drive, para que el material que baje de la nube quede
enlazado sin esperar al día siguiente.

**Zona horaria:** `uni.py` la fija en `TZ = ZoneInfo("Atlantic/Canary")`.
Cámbiala si no vives en Canarias. Los eventos se escriben en UTC ya convertidos,
con el horario de verano bien resuelto por `zoneinfo`.

## Google Drive (opcional)

El vault sigue viviendo en local — Obsidian lo necesita así — y `rclone bisync`
lo sincroniza en las dos direcciones cada 15 min contra una carpeta de Drive.

```bash
sudo dnf install rclone
rclone config                                    # remoto 'drive', tipo: drive
UNI_DRIVE_CARPETA=Universidad ./instalar.sh drive
uni-drive                                        # primer sync
```

El remoto y la carpeta se fijan **al instalar** (`UNI_DRIVE_REMOTO`,
`UNI_DRIVE_CARPETA`; por defecto `drive:Obsidian/universidad`). El timer se
activa solo si ambos existen ya.

Antes de un sync dudoso, `uni-drive --dry-run` dice qué haría sin tocar nada
— cualquier argumento extra se le pasa tal cual a rclone.

**Si la carpeta de Drive ya tiene contenido**, mira primero si las estructuras
coinciden: `rclone check . drive:CARPETA --filter-from sistema/drive.filtros`.
`--resync` fusiona en superconjunto, así que dos árboles con el mismo contenido
en rutas distintas acaban duplicados en ambos lados. Alinear las rutas antes
sale mucho más barato que limpiarlo después.

**No se sincroniza todo**, y es a propósito (`sistema/drive.filtros`):

| Fuera | Por qué |
|-------|---------|
| `.git/` | Un syncer copiándolo a medias corrompe el repo. El historial ya lo lleva git. |
| `workspace.json`, `graph.json`, `appearance.json` | Se reescriben al mover un panel. Conflictos a cambio de nada. |
| `out/` | El `.ics` lo regenera `uni sync` y Evolution lo lee en local. |

Si los dos lados tocan el mismo archivo gana el más reciente (`--conflict-resolve
newer`) y el otro se conserva renombrado: no se pierde nada en silencio. Hay un
freno de mano en `--max-delete 25`, que aborta si algo pretende borrar más de un
cuarto del vault.

Si bisync se atasca (pasa si matas un ciclo a medias): `uni-drive --resync`.

**Para el móvil esto no sirve.** Obsidian en Android no trabaja contra Drive,
necesita archivos locales. Para eso hace falta otra cosa (Obsidian Sync, o un
remoto git con un cliente que lo soporte).

## Google Calendar (opcional)

El `.ics` lo lee GNOME Calendar en local, pero eso no sale del portátil. Para
que los exámenes lleguen a Google —y con ellos al móvil— hay un exportador que
escribe por **Evolution Data Server**, aprovechando la cuenta de Google que ya
tienes conectada en GNOME. No hace falta crear credenciales ni autorizar nada
nuevo: si el calendario destino es de una cuenta conectada, EDS lo sube por
CalDAV.

```bash
uni gcal --listar                       # qué calendarios ve el sistema
UNI_GCAL_CALENDARIO='Universidad' UNI_GCAL_CUENTA='tu@correo' \
  ./instalar.sh comando                 # fija el destino
```

El destino se graba dentro del propio comando `uni`, no en cada unidad de
systemd: así lo heredan por igual la terminal, la ventanita del atajo y los
timers. A partir de ahí cada `uni sync` lo mantiene al día. Sin destino
configurado el exportador no hace nada.

Los UID que genera `uni.py` son estables y acaban en `@uni.local`, y de ahí
salen las tres garantías que hacen esto seguro sobre un calendario que ya usas:

- reexportar **actualiza** los eventos en vez de duplicarlos;
- un examen borrado, o una sesión que ya no toca, **desaparece** del calendario;
- **nunca se toca un evento que no haya creado uni** — el sufijo del UID es lo
  que distingue los nuestros del resto.

Mover la fecha de un examen cambia sus UID, así que se ve como «5 nuevos y 5
retirados» en vez de «5 actualizados». El resultado es el mismo y no quedan
duplicados.

## Plugins

Se instalan desde el repo canónico que indica el
[registro oficial de Obsidian](https://github.com/obsidianmd/obsidian-releases),
en una versión fijada, y **se comprueba que el `id` del manifest descargado sea
el esperado**:

| Plugin | Release | Para qué |
|--------|---------|----------|
| [Dataview](https://github.com/blacksmithgu/obsidian-dataview) | 0.5.70 | Tablas del Panel y cuenta atrás |
| [Tasks](https://github.com/obsidian-tasks-group/obsidian-tasks) | 8.3.0 | "Hoy y atrasado", tareas con fecha |
| [Calendar](https://github.com/liamcain/obsidian-calendar-plugin) | 1.5.10 | Vista de mes en la barra lateral |

Esa comprobación no es teatro. Dos candidatos cayeron por ella:

- **Calendar**: la release marcada como `latest` en GitHub era `2.0.0-beta.2`,
  etiquetada `prerelease=false` por error, y publicada bajo **otro id**
  (`calendar-beta`). Por eso la versión va fijada a la 1.5.10 estable.
- **Full Calendar**: la URL del registro redirige a `community-archive/`.
  Archivado, sin un commit desde noviembre de 2024. Descartado.

Y un tercer detalle: la release **0.5.70 de Dataview empaqueta un
`manifest.json` que sigue diciendo `0.5.68`**. Obsidian muestra por tanto una
versión que no es la que corre. Por eso el instalador lleva el tag y la versión
declarada en campos separados.

También se descarta **Templater** a propósito, aunque sea el plugin más
descargado: ejecuta JavaScript arbitrario desde tus notas, y el plugin
*Templates* del núcleo cubre este flujo.

El código de los plugins **no se redistribuye aquí** — lo baja `instalar.sh` de
sus repos originales.

## Qué hay en el repo

```
Panel.md            el único sitio que hay que mirar
Plantillas/         plantilla de examen (plugin Templates del núcleo)
Ejemplos/           una nota de examen y una de asignatura, comentadas
uni.py              el motor (stdlib + PyYAML)
ventana.py          la ventanita de alta rápida (GTK4 + libadwaita)
instalar.sh         instalación sin sudo, idempotente
sistema/            unidades de systemd, fuente de EDS, wrappers, filtros de Drive
.obsidian/          configuración del vault (sin estado local ni plugins)
```

`Exámenes/` y `Asignaturas/` van vacías **a propósito**: ahí van tus datos y
están en el `.gitignore`, igual que `out/` (el `.ics` generado) y el
`workspace.json` de Obsidian. Este repo publica el funcionamiento, no los
exámenes de nadie.

## Detalles que costaron encontrar

- `Persistent=true` **solo tiene efecto sobre `OnCalendar=`**. Un timer con
  `OnBootSec=`/`OnUnitActiveSec=` que se reinicie cuando ambos disparadores ya
  han vencido se queda en `active (elapsed)` con `Trigger: n/a` — activo, pero
  sin próxima ejecución y sin volver a dispararse nunca. Por eso el timer de
  Drive es `OnCalendar=*:0/15`.
- La fuente de EDS necesita la sección **`[Local Backend]`, con espacio**. Con
  `[Local]` se ignora en silencio y GNOME se crea un calendario vacío propio.
- `CustomFile` es un `GFile`: exige URI `file://`, no una ruta pelada.
- El flatpak de Obsidian solo ve `~/Documents` y `~/Downloads`. Sin
  `flatpak override --user --filesystem=…` el vault directamente no se puede abrir.
- `notify-send` desde `systemd --user` necesita
  `DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus`.
- El `.ics` se genera cumpliendo RFC 5545 a mano: CRLF, plegado de líneas y
  UIDs estables (derivados de asignatura + fecha), para que reimportarlo
  actualice los eventos en vez de duplicarlos.

## Licencia

MIT.
