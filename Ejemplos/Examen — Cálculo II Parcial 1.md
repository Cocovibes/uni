---
tipo: examen
asignatura: "[[Cálculo II]]"
fecha: 2026-11-13
hora: "09:00"
formato: parcial
peso: 40
dias: 5
temas:
  - Series
  - Derivadas parciales
  - Integrales múltiples
duracion_examen: 120
---

# Cálculo II — Parcial 1

Ejemplo de nota de examen. **Va en `Exámenes/`.** Normalmente no hace falta
escribirla a mano: `uni nuevo "Cálculo II" "Parcial 1" 13/11` la crea igual. El
frontmatter de arriba es todo lo que hay: `fecha` es lo único obligatorio.

| Clave | Para qué |
|-------|----------|
| `tipo: examen` | Sin esto `uni.py` ignora la nota. |
| `fecha` | `AAAA-MM-DD`. De aquí cuelga toda la rampa. |
| `dias` | Días de estudio previos → **una sesión por día**. Def. 5. `auto` = manda el `peso`. |
| `formato` | `Parcial`, `Final`, `Recuperación` o `Test`. Se elige de una lista, no se escribe. |
| `peso` | % de la nota final, **opcional**: casi nunca se sabe exacto. Solo decide algo con `dias: auto`. |
| `hora` | Hora del examen. Solo para el evento del calendario. |
| `temas` | Aparecen en la descripción de cada sesión. |
| `duracion_examen` | Minutos. También es la duración del simulacro. |

## Exámenes de otros años
Enlaces o rutas a los PDF. Conseguirlos es la primera tarea de la rampa.

-

## Simulacro
| Fecha | Nota | Qué falló |
|-------|------|-----------|
|       |      |           |

## Plan de estudio

Este bloque **no se escribe a mano**. `uni sync` lo genera entre los dos
marcadores HTML y lo reescribe cada vez, conservando lo que hayas marcado con
`[x]` aunque muevas la fecha del examen:

```md
<!-- RAMPA:INICIO -->
- [x] D-5 · Barrido a libro cerrado — 1 problema de CADA tema, cronometrado, sin apuntes — es el diagnóstico (90 min) 📅 2026-11-08
- [ ] D-4 · Huecos — solo lo que falló en el barrido, hasta que salga sin mirar (90 min) 📅 2026-11-09
- [ ] D-3 · Simulacro — examen entero de otro año, condiciones reales, sin corregir hoy (120 min) 📅 2026-11-10
- [ ] D-2 · Corrección — corregir el simulacro, repasar solo los errores, anotarlos en Trampas (60 min) 📅 2026-11-11
- [ ] D-1 · Formulario de memoria — escribir el formulario de memoria en un folio, comparar, dormir 8h (45 min) 📅 2026-11-12
<!-- RAMPA:FIN -->
```

Eso es con `dias: 5`. Con `dias: 7` salen las 7 sesiones, una por día; con
`dias: 3`, solo Barrido, Simulacro y Formulario. Lo marcado con `[x]` se guarda
**por nombre de sesión**, así que sobrevive a cambiar `dias` o la fecha.

Aquí va dentro de un bloque de código a propósito, y los marcadores están
**abreviados**: los de verdad llevan un comentario más largo. Así esta nota de
ejemplo se puede copiar a `Exámenes/` sin que `uni sync` escriba el plan dentro
del bloque de código, donde las tareas quedarían inertes. Si la nota no tiene
marcadores, `uni.py` añade la sección al final ya bien puesta.
