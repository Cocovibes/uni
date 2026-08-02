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

1. Examen nuevo → nota en `Exámenes/` con la plantilla. Rellenas `fecha` y
   `peso`. Nada más.
2. `uni sync`.
3. Ya está.

```yaml
---
tipo: examen
asignatura: "[[Cálculo II]]"
fecha: 2026-11-13
peso: 40                 # % de la nota → decide cuánta rampa se genera
temas: [Series, Derivadas parciales]
duracion_examen: 120
---
```

**La fuente de verdad son las notas.** No hay base de datos, ni YAML aparte, ni
estado escondido. Lo que dice el frontmatter es lo que hay.

## La rampa

Recordar "estudia 7 días antes" no sirve de nada si el día 7 no sabes qué hacer.
Cada sesión tiene una acción concreta:

| Día  | Sesión                  | Para qué |
|------|-------------------------|----------|
| D-14 | Inventario              | Medir qué sabes. Bajar exámenes de otros años. |
| D-10 | Ataque a lo peor        | Los 2 temas más flojos, con apuntes. |
| D-7  | Barrido a libro cerrado | **El diagnóstico.** 1 problema por tema, cronometrado, sin apuntes. |
| D-5  | Huecos                  | Solo lo que falló en D-7. |
| D-3  | Simulacro               | Examen entero de otro año, condiciones reales. |
| D-2  | Corrección              | Solo los errores del simulacro → a *Trampas*. |
| D-1  | Formulario de memoria   | Escribirlo en un folio de cero. Dormir 8 h. |

El `peso` escala la rampa: **≥ 35 %** → completa · **15-34 %** → D-10,7,5,3,1 ·
**< 15 %** → D-5,3,1. Un test que vale el 10 % no merece dos semanas.

Las sesiones ya pasadas no se generan. Marcar `[x]` es seguro: `uni sync`
conserva lo hecho **aunque muevas la fecha del examen**.

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
- activa el timer de usuario de systemd para el aviso de las 08:30;
- enlaza el `.ics` con GNOME Calendar vía Evolution Data Server;
- si Obsidian es flatpak, le da acceso a la carpeta del vault.

Después: abre la carpeta como vault en Obsidian. Se abre en **Panel**.

```
uni            plan de hoy
uni proximos   siguientes 14 días
uni sync       regenera notas + calendario
```

**Zona horaria:** `uni.py` la fija en `TZ = ZoneInfo("Atlantic/Canary")`.
Cámbiala si no vives en Canarias. Los eventos se escriben en UTC ya convertidos,
con el horario de verano bien resuelto por `zoneinfo`.

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
instalar.sh         instalación sin sudo, idempotente
sistema/            unidades de systemd, fuente de EDS, wrapper de `uni`
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
