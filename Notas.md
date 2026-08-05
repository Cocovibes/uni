# Notas

Dónde estás flojeando. Se rellena solo: pon `nota: 6.5` en el frontmatter de
una nota de examen y aparece aquí.

## Dónde flojeas

De peor a mejor media. Las de arriba son las que piden horas.

```dataview
TABLE WITHOUT ID
  rows.asignatura[0] AS "Asignatura",
  round(average(rows.nota), 2) AS "Media",
  min(rows.nota) AS "Peor",
  max(rows.nota) AS "Mejor",
  length(rows) AS "Pruebas"
FROM "Exámenes"
WHERE nota AND tipo = "examen"
GROUP BY asignatura
SORT average(rows.nota) ASC
```

## Suspensos y aprobados raspados

Lo que hay que recuperar, y lo que casi.

```dataview
TABLE WITHOUT ID
  file.link AS "Prueba", asignatura AS "Asignatura",
  fecha AS "Fecha", nota AS "Nota",
  choice(nota < 5, "❌ suspenso", "⚠️ raspado") AS "Estado"
FROM "Exámenes"
WHERE nota AND nota < 6
SORT nota ASC
```

## Todo, por fecha

```dataview
TABLE WITHOUT ID
  fecha AS "Fecha", asignatura AS "Asignatura",
  file.link AS "Prueba", formato AS "Tipo", nota AS "Nota"
FROM "Exámenes"
WHERE nota
SORT fecha DESC
```

## Media por cuatrimestre

```dataview
TABLE WITHOUT ID
  rows.cuatrimestre[0] AS "Cuatrimestre",
  round(average(rows.nota), 2) AS "Media",
  length(rows) AS "Pruebas"
FROM "Exámenes"
WHERE nota AND cuatrimestre
GROUP BY cuatrimestre
SORT rows.cuatrimestre[0] ASC
```

## Pendientes de nota

Exámenes ya hechos sin calificación apuntada. Si esta lista crece, el resto
de tablas mienten.

```dataview
TABLE WITHOUT ID
  fecha AS "Fecha", asignatura AS "Asignatura", file.link AS "Prueba"
FROM "Exámenes"
WHERE !nota AND date(fecha) < date(today)
SORT fecha DESC
```

---

Los errores concretos van en la sección **Trampas** de cada asignatura, que es
texto libre y no se puede agregar aquí. Esta tabla te dice *qué* asignatura
mirar; las Trampas te dicen *qué* falló dentro.
