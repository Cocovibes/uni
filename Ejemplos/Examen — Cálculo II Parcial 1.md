---
tipo: examen
asignatura: "[[Cálculo II]]"
fecha: 2026-11-13
hora: "09:00"
formato: parcial
peso: 40
temas:
  - Series
  - Derivadas parciales
  - Integrales múltiples
duracion_examen: 120
---

# Cálculo II — Parcial 1

Ejemplo de nota de examen. **Va en `Exámenes/`.** El frontmatter de arriba es
todo lo que hay que rellenar: `fecha` y `peso` son los únicos obligatorios en la
práctica.

| Clave | Para qué |
|-------|----------|
| `tipo: examen` | Sin esto `uni.py` ignora la nota. |
| `fecha` | `AAAA-MM-DD`. De aquí cuelga toda la rampa. |
| `peso` | % de la nota final. Decide cuántas sesiones se generan. |
| `hora` | Hora del examen. Solo para el evento del calendario. |
| `temas` | Aparecen en la descripción de cada sesión. |
| `duracion_examen` | Minutos. También es la duración del simulacro de D-3. |

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
- [x] D-14 · Inventario — listar temas, puntuar confianza 0-3, bajar exámenes de otros años (30 min) 📅 2026-10-30
- [ ] D-10 · Ataque a lo peor — los 2 temas más flojos, 3 problemas de cada uno, con apuntes (90 min) 📅 2026-11-03
- [ ] D-7 · Barrido a libro cerrado — 1 problema de CADA tema, cronometrado, sin apuntes — es el diagnóstico (90 min) 📅 2026-11-06
- [ ] D-5 · Huecos — solo lo que falló en D-7, hasta que salga sin mirar (90 min) 📅 2026-11-08
- [ ] D-3 · Simulacro — examen entero de otro año, condiciones reales, sin corregir hoy (120 min) 📅 2026-11-10
- [ ] D-2 · Corrección — corregir el simulacro, repasar solo los errores, anotarlos en Trampas (60 min) 📅 2026-11-11
- [ ] D-1 · Formulario de memoria — escribir el formulario de memoria en un folio, comparar, dormir 8h (45 min) 📅 2026-11-12
<!-- RAMPA:FIN -->
```

Aquí va dentro de un bloque de código a propósito, y los marcadores están
**abreviados**: los de verdad llevan un comentario más largo. Así esta nota de
ejemplo se puede copiar a `Exámenes/` sin que `uni sync` escriba el plan dentro
del bloque de código, donde las tareas quedarían inertes. Si la nota no tiene
marcadores, `uni.py` añade la sección al final ya bien puesta.
