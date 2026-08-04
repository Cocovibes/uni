# uni — vault de estudio con fricción cero

Un vault de Obsidian que **es a la vez el motor del calendario**. Apuntas la
fecha de un examen y aparece solo, sin tocar nada más:

- el **plan de estudio** escrito dentro de la propia nota del examen, como
  tareas con fecha;
- los mismos eventos en el **calendario del sistema** (GNOME Calendar, enlazado
  en vivo — no es una importación);
- una **notificación de escritorio a las 08:30** con lo que toca hoy.

La idea es que no haya que mantener nada. El sistema te dice qué hacer; tú solo
marcas `[x]`.

---

## El bucle entero

**Ctrl + Shift + Ñ**, desde donde estés. Se abre una ventanita, rellenas
asignatura / examen / fecha, le das a **Guardar** y ya está: la nota del examen
creada, la nota de la asignatura también si no existía (para que el `[[enlace]]`
no quede roto), el plan de estudio escrito dentro, y las sesiones en el
calendario del sistema. La ventana te enseña qué ha programado y se cierra.

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
uni nuevo "Física Básica 1" Final 2026-06-10 --dias "1 semana" \
          --temas "Magnetostática,Inducción" --peso 60
```

| Opción | Para qué | Def. |
|--------|----------|------|
| `--dias` | días de estudio previos. Vale `5`, `"1 semana"`, `auto` | **5** |
| `--peso` | % de la nota final | 30 |
| `--hora` | hora del examen | 09:00 |
| `--temas` | separados por comas | — |
| `--duracion` | minutos de examen | 120 |
| `--formato` | parcial, final… | el título |

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
dias: 5                  # días de estudio previos → 5 eventos, uno por día
temas: [Series, Derivadas parciales]
duracion_examen: 120
---
```

## La rampa

Recordar "estudia 5 días antes" no sirve de nada si el día 5 no sabes qué hacer.
`dias: N` genera **N sesiones, una por día**, en los N días naturales anteriores
al examen (D-N … D-1), y cada una tiene una acción concreta:

| Sesión                  | Para qué |
|-------------------------|----------|
| Inventario              | Medir qué sabes. Bajar exámenes de otros años. |
| Ataque a lo peor        | Los 2 temas más flojos, con apuntes. |
| Barrido a libro cerrado | **El diagnóstico.** 1 problema por tema, cronometrado, sin apuntes. |
| Huecos                  | Solo lo que falló en el barrido. |
| Simulacro               | Examen entero de otro año, condiciones reales. |
| Corrección              | Solo los errores del simulacro → a *Trampas*. |
| Formulario de memoria   | Escribirlo en un folio de cero. Dormir 8 h. |

Con menos días que sesiones se caen las menos rentables primero, **respetando
las dependencias** (Huecos nunca entra sin Barrido; Corrección nunca sin
Simulacro):

| `dias` | Plan |
|--------|------|
| 1 | Formulario |
| 2 | Simulacro · Formulario |
| 3 | Barrido · Simulacro · Formulario |
| 4 | Barrido · Simulacro · Corrección · Formulario |
| **5** *(def.)* | Barrido · Huecos · Simulacro · Corrección · Formulario |
| 7 | la rampa entera, un día cada una |
| >7 | la rampa entera + *Estudio de fondo* en los días de delante |

Si el examen está **más cerca** que la ventana pedida, el plan se encoge a los
días que quedan en vez de generar sesiones ya pasadas.

`dias: auto` vuelve al modo antiguo, en el que manda el `peso` y las sesiones se
reparten con hueco entre ellas: **≥ 35 %** → D-14,10,7,5,3,2,1 · **15-34 %** →
D-10,7,5,3,1 · **< 15 %** → D-5,3,1.

Marcar `[x]` es seguro: `uni sync` conserva lo hecho **aunque muevas la fecha
del examen o cambies `dias`** — lo hecho se guarda por nombre de sesión, no por
el número de día.

Aparte de la rampa, las notas de `Asignaturas/` pueden llevar un bloque
`semanal` que crea un evento recurrente. Esa hora fija es la que de verdad
sube la nota; la rampa solo evita el desastre.

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
- si rclone ya está configurado, activa el timer de sincronización con Drive;
- enlaza el `.ics` con GNOME Calendar vía Evolution Data Server;
- si Obsidian es flatpak, le da acceso a la carpeta del vault.

Después: abre la carpeta como vault en Obsidian. Se abre en **Panel**.

```
Ctrl+Shift+Ñ   la ventanita de alta rápida
uni            plan de hoy
uni nuevo      alta de un examen (nota + asignatura + plan + calendario)
uni ventana    la misma ventanita, a mano
uni proximos   siguientes 14 días
uni sync       regenera notas + calendario + índice del grafo
uni indice     solo rehace los nodos curso/cuatrimestre/asignatura
uni-drive      sincroniza con Google Drive (si lo has configurado)
```

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
