# Panel

Lo único que tienes que mirar. Aquí solo hay **obligaciones reales**: exámenes,
prácticas y entregas con fecha oficial. Nada de tareas inventadas.

## Surtidor

Una fila por obligación. Pincha en la cabecera de cualquier columna para
reordenar: por lo que falta, por dificultad, por peso o por asignatura.

```dataview
TABLE WITHOUT ID
  file.link AS "Qué",
  asignatura AS "Asignatura",
  dateformat(date(fecha), "EEE dd/MM") AS "Cuándo",
  (date(fecha) - date(today)).days AS "Faltan",
  choice(dificultad, "🔴🔴🔴🔴🔴", "") AS "Dif.",
  peso AS "%",
  formato AS "Tipo"
FROM "Exámenes"
WHERE date(fecha) >= date(today)
SORT date(fecha) ASC
```

### Por dificultad

Lo más caro primero, sin mirar el calendario. Para decidir qué atacas hoy
cuando todo está lejos.

```dataview
TABLE WITHOUT ID
  file.link AS "Qué",
  asignatura AS "Asignatura",
  dificultad AS "Dif.",
  peso AS "%",
  dateformat(date(fecha), "dd/MM") AS "Cuándo",
  (date(fecha) - date(today)).days AS "Faltan"
FROM "Exámenes"
WHERE date(fecha) >= date(today)
SORT dificultad DESC, peso DESC, date(fecha) ASC
```

### Esta semana

```dataview
TABLE WITHOUT ID
  file.link AS "Qué",
  dateformat(date(fecha), "EEE dd/MM HH:mm") AS "Cuándo",
  dificultad AS "Dif.",
  peso AS "%"
FROM "Exámenes"
WHERE date(fecha) >= date(today) AND date(fecha) <= date(today) + dur(7 days)
SORT date(fecha) ASC
```

### Ya pasados, sin nota

Lo que hiciste y no apuntaste. [[Notas]] tiene las estadísticas.

```dataview
TABLE WITHOUT ID
  file.link AS "Qué",
  dateformat(date(fecha), "dd/MM/yyyy") AS "Cuándo"
FROM "Exámenes"
WHERE date(fecha) < date(today) AND !nota
SORT date(fecha) DESC
```

## Fechas oficiales de la ESIT

Las de la ESIT viven en su propio calendario (**Uni — Exámenes ULL**, naranja),
aparte del tuyo. `uni ull ver` las lista; el timer las revisa cada lunes y avisa
si mueven alguna.

## Asignaturas

```dataview
LIST
FROM "Asignaturas"
SORT file.name ASC
```

---

## Cómo se usa

1. **Algo nuevo con fecha** → **Ctrl + Shift + Ñ**, rellenar y Guardar.
   En terminal: `uni nuevo "Ingeniería Térmica" "Parcial 2" 13/11`
2. Aparece en el calendario del sistema y en el surtidor de aquí arriba.

**`dificultad: 1-5`** en el frontmatter ordena el surtidor. Si la dejas vacía
se estima desde el `peso`, solo para que la columna no salga en blanco — la
buena es la que pongas tú.

Este sistema **no inventa tareas**. No hay rampa de estudio, ni bloques
semanales, ni horario de clases: si no tiene fecha oficial, no está aquí.
