# Panel

Lo único que tienes que mirar. Si algo no sale aquí, no toca hoy.

## Hoy y atrasado

```tasks
not done
due before tomorrow
sort by due
short mode
```

## Próximos 7 días

```tasks
not done
due after today
due before in 8 days
sort by due
short mode
```

## Cuenta atrás

```dataview
TABLE WITHOUT ID
  file.link AS "Examen",
  asignatura AS "Asignatura",
  fecha AS "Fecha",
  peso AS "Peso %",
  date(fecha) - date(today) AS "Falta"
FROM "Exámenes"
WHERE tipo = "examen" AND date(fecha) >= date(today)
SORT fecha ASC
```

## Asignaturas

```dataview
LIST
FROM "Asignaturas"
SORT file.name ASC
```

---

## Cómo se usa

1. **Un examen nuevo** → nota en `Exámenes/` (plantilla `Examen`), pon `fecha` y `peso`.
2. Terminal: `uni sync`.
3. El plan de estudio aparece solo dentro de la nota del examen, en el calendario
   del sistema, y a las 08:30 como notificación.

Marcar `[x]` una tarea es seguro: `uni sync` conserva lo hecho.

`peso` manda: ≥ 35 % → rampa completa (D-14…D-1) · 15-34 % → D-10,7,5,3,1 · < 15 % → D-5,3,1.
