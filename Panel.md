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

Tus notas y dónde flojeas: [[Notas]].

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

Cada curso es una nota en `Cursos/`, enlazada a sus cuatrimestres, y cada
cuatrimestre a sus asignaturas. Los archivos cuelgan de la nota de cada
asignatura. Lo rehace `uni sync`: si dejas un PDF en la carpeta de una
asignatura, aparece solo.

---

## Cómo se usa

1. **Un examen nuevo** → **Ctrl + Shift + Ñ**, rellenar y Guardar.
   En terminal: `uni nuevo "Cálculo Diferencial" "Parcial 2" 13/11`
   (o `uni nuevo` a secas y te lo pregunta). También vale la plantilla `Examen`
   en `Exámenes/` + `uni sync`.
2. El plan de estudio aparece solo dentro de la nota del examen, en el calendario
   del sistema, y a las 08:30 como notificación.

Marcar `[x]` una tarea es seguro: `uni sync` conserva lo hecho.

`dias` manda: **N días de estudio → N sesiones, una por día** (D-N…D-1). Por
defecto **5**. `--dias "1 semana"` para la rampa entera; `dias: auto` para el
modo antiguo en el que mandaba el `peso`.
