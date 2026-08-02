---
nombre: Cálculo II
curso: 2
semanal:
  dia: martes
  hora: "18:00"
  duracion: 60
  tarea: "Problemas de la hoja de esta semana. Sin mirar soluciones."
  hasta: 2026-12-18
---

# Cálculo II

Ejemplo de nota de asignatura. **Va en `Asignaturas/`.**

El bloque `semanal` del frontmatter es opcional, y es la parte que más nota da a
largo plazo: crea un evento **recurrente** en el calendario hasta la fecha
`hasta`. Cramming en D-7 recupera un examen; esta hora semanal es la que hace
que no haya nada que recuperar.

| Clave | Valor |
|-------|-------|
| `dia` | `lunes`…`domingo` (con o sin tilde). |
| `hora` | `HH:MM`, hora local. |
| `duracion` | Minutos. |
| `tarea` | Texto del evento. |
| `hasta` | Última semana. Normalmente el fin del cuatrimestre. |

Materiales: ruta o enlace a los apuntes y hojas de problemas.

## Exámenes

```dataview
TABLE WITHOUT ID file.link AS "Examen", fecha AS "Fecha", peso AS "Peso %"
FROM "Exámenes"
WHERE tipo = "examen" AND contains(string(asignatura), "Cálculo II")
SORT fecha ASC
```

## Trampas
Errores que ya he cometido. Una línea cada uno, en cuanto pasan. Releer esta
sección antes de cada examen — es la lista de lo que va a volver a fallar.

-

## Dudas para clase

-
