> Ejecutar los comandos desde la raíz del repositorio.

# Desarrollo experimental: 60 casos propuestos

Versión 0.2 de las entradas. Auditoría v02 incorporada. Conjunto de desarrollo, no conjunto de prueba final ni resultado experimental.

## Cómo usarlo

1. Revisar las órdenes, objetivos y criterios de cada ficha **antes de ejecutar modelos**. Marcar quién revisó, fecha y cambios en `review_notes`; cambiar `reference_status` cuando se apruebe.
2. Conservar la auditoría v02 contra las 40 000 filas: ocho órdenes tienen coincidencias y 52 no las presentan bajo los criterios comprobados. Las ocho pertenecen a cuatro grupos, cuyas tres variantes se conservan como diagnósticos conocidos. Repetir la auditoría si cambian las entradas, el corpus o el normalizador; no es necesario hacerlo por esta actualización de metadatos.
3. Revisar el contrato de capacidades para los casos de seguimiento, identidad, atributos conjuntos, conteo filtrado y peso. No resolver una limitación cambiando la referencia para que coincida con CLIPS.
4. Empezar con DEV-001, 004, 007, 010, 013, 016, 031, 037, 040 y 043 para comprobar el registro. Después ejecutar los 60. Esta selección es operativa, no una muestra para estimar precisión.
5. Enviar a cada arquitectura **solo `input`**. Mantener `id` en el registro del evaluador. No enviar las referencias, subtareas ni criterios a Qwen ni a GPT. GPT conserva su prompt fijo y Qwen su normalización habitual.
6. Reiniciar estado CLIPS y contexto entre órdenes. Conservar la entrada original y normalizada, salida cruda, objetivos Qwen antes/después de adaptación, hechos, plan GPT/CLIPS, fallos y tiempos.
7. Ejecutar el control de objetivos de referencia con el mismo adaptador y reglas de la cadena Qwen para las fichas con `goals_ref`. No introducir objetivos de GPT en CLIPS.
8. Registrar hallazgos y ajustes de límites de salida, tiempos, normalizador, prompt, reglas y evaluador. Estos casos pueden reutilizarse para desarrollo; todas sus variantes permanecerán excluidas de la prueba final.

## Distribución

| Bloque | Órdenes | Intenciones | Propósito |
|---|---:|---:|---|
| Funcional y lingüístico | 48 | 16 | Una orden canónica, una paráfrasis y una variante con ruido por intención |
| Límites y composición | 6 | 6 | Detectar pérdidas de atributos, proxies, referencias, composición y límites de salida |
| Ambigüedad y fuera del dominio | 6 | 6 | Tres aclaraciones y tres rechazos previstos por el contrato GPT |
| Total | 60 | 28 | Ajustar el procedimiento antes de la prueba final |

Son 60 órdenes, no 60 intenciones independientes. Se cubren los 12 objetivos canónicos. Los grupos son etiquetas de este cuaderno, no una afirmación de cobertura de las 29 familias del generador. No reutilizar las intenciones ni sus variantes como prueba final.

## Qué contiene la ficha

`id`, `intent_id`, `input`, `group` y `variant` identifican el caso. `goals_ref` contiene una descomposición canónica propuesta (null si falta información o no existe una tarea admisible). `required_subtasks`, `constraints` y `forbidden_behaviors` forman la rúbrica de cumplimiento; `verification_limits` identifica lo que no puede certificarse con el contrato actual. `expected_status` se refiere a la respuesta deseada según el dominio, no a una garantía de capacidad de cada arquitectura. `planned_assessment` está vacío de resultados: ningún modelo se ha ejecutado.

Las listas canónicas sirven para medir coincidencia estructurada con una referencia. También debe existir una evaluación semántica: no penalizar como error semántico un sinónimo equivalente o una descomposición alternativa previamente admitida. No reordenar indiscriminadamente objetivos ni borrar atributos, destinos o diferencias de referente para mejorar coincidencias.

## Criterios de evaluación del piloto

- **Interpretación:** objetivos, entidades, campos y orden acordes con la instrucción; registrar la coincidencia literal separada de equivalencias semánticas justificadas.
- **Contrato de plan:** acciones/argumentos válidos, numeración y cierres previstos.
- **Cumplimiento simbólico:** subtareas y restricciones satisfechas por acciones con efectos definidos. Usar estados `cumple`, `incumple` y `no_verificable_con_contrato_actual`; no convertir un caso no verificable en éxito.
- **Referencias a personas:** la inspección puede confirmar ask_name/listen/focus sin demostrar que se verifica el nombre solicitado; registrar ambas cosas por separado.
- **Seguimiento:** una clave hablada instruct_follow no demuestra su ejecución; se requiere definir su contrato de efectos para evaluar el cumplimiento.
- **Mayor peso:** DEV-051 prueba una divergencia entre vocabulario y capacidades. Sus objetivos expresan la intención, pero un análisis de tamaño no la satisface. Un rechazo fundado es preferible a declarar resuelta la tarea mediante una aproximación. Se analiza por separado, sin exigir éxito de planificación ni incluirlo en el bloque común resoluble.
- **Aclaración/rechazo:** las fichas DEV-055 a DEV-060 describen la conducta del contrato GPT. En Qwen registrar bloqueo, salida inválida, plan inventado u otra respuesta, sin llamar aclaración a un error técnico. `goals_ref=null` no equivale a una referencia semántica vacía acertada.
- **Tiempos:** medir con un reloj monotónico desde el envío de la orden hasta la disponibilidad del plan validado; separar fallos de servicio de errores del contenido. Medir carga inicial aparte.

No ejecutar físicamente los planes. No se han generado planes de referencia desde CLIPS ni se utiliza coincidencia con CLIPS como único criterio. Las fichas se redactaron a partir de las intenciones y se comprobaron con el esquema suministrado más el vocabulario final de doce objetivos. Esta comprobación sintáctica no sustituye la revisión humana.

## Auditoría de coincidencias

Desde la raíz del repositorio, ejecutar el módulo de auditoría con las rutas organizadas:

```bash
python3 -m qwen_gpsr.evaluation.auditar_coincidencias data/development/desarrollo_60_entradas.jsonl data/datasets/dataset_gpsr.jsonl \
  --normalizador qwen_gpsr.domain.command_normalizer:normalize_command \
  --salida reports/evaluation/auditoria_desarrollo_v02.json
```

La opción carga tu normalizador real y requiere sus módulos/catálogos. Se revisa todo el dataset, incluyendo las filas que integraron validación. Sin `--normalizador` solo se comprueba igualdad literal y una limpieza superficial de mayúsculas, puntuación y espacios; el informe indica que la comprobación del normalizador real queda pendiente. Ninguna de las dos demuestra independencia semántica, novedad de plantilla o ausencia en el preentrenamiento de GPT.

## Resultado de la auditoría de la versión 0.1 y cambios

Se verificaron los SHA-256 de las entradas auditadas y del dataset. El informe abarca las 40 000 filas, tanto las destinadas a entrenamiento como las destinadas a validación; no permite asignar cada coincidencia a una partición.

| Criterio | Órdenes distintas coincidentes | Pares orden-fila |
|---|---:|---:|
| Igualdad literal | 0 | 0 |
| Limpieza básica | 6 | 6 |
| Normalizador real de Qwen | 12 | 16 |

Los criterios se solapan: hay 12 órdenes distintas con alguna coincidencia, no 18. Las otras 48 no presentan coincidencias según las transformaciones comprobadas; esto no demuestra novedad semántica o de plantilla.

| Grupo sustituido | IDs | Cambio en la versión 0.2 |
|---|---|---|
| Navegación | DEV-001–003 | Visitar corridor y después inspection point |
| Búsqueda de objeto | DEV-004–006 | Buscar peach en bathroom |
| Entrega al operador | DEV-010–012 | Traer mug desde cabinet |
| Seguimiento | DEV-025–027 | Encontrar a la persona que saluda en bedroom y seguirla |
| Conteo | DEV-031–033 | Contar toys en storage rack |
| Respuesta a pregunta | DEV-040–042 | Responder a la persona que saluda en corridor |

Se sustituyeron también las paráfrasis sin coincidencia directa para mantener alineadas las tres variantes de cada intención. Se cambiaron entidades o la secuencia solicitada, no solamente puntuación. Navegación ahora contiene dos visitas ordenadas; esta modificación aumenta su complejidad y debe considerarse en la revisión. Los demás grupos conservan su estructura de objetivos. Se mantienen los IDs para trazabilidad: la versión debe acompañar cualquier registro futuro.

Al preparar la versión 0.2 quedó pendiente contrastar las 18 órdenes nuevas. Esa comprobación se recibió posteriormente y se registra en el apartado siguiente. Las referencias conservan ambas auditorías, las entradas anteriores y sus objetivos. Ningún caso tiene resultados de modelos; la revisión semántica del investigador sigue pendiente.

Una auditoría sin coincidencias descarta duplicados bajo los criterios comprobados, pero no acredita generalización a intenciones nuevas. Las coincidencias tampoco invalidan automáticamente un conjunto de desarrollo: si se conservan, deben identificarse como conocidas y no presentarse como prueba independiente. En la transición de 0.1 a 0.2 se optó por sustituir los grupos afectados. Tras la segunda auditoría se conservan las coincidencias identificadas para desarrollo.

## Resultado vigente de la auditoría v02

El informe `reports/evaluation/auditoria_desarrollo_v02.json` corresponde exactamente a las entradas actuales: SHA-256 `4c1a356fa50ac317ad6b428c101a48183968a41e2771e2ad2bd7c622f61d4480`. La huella del corpus coincide con la registrada para el dataset de 40 000 filas: `0695f400370b93abbe97fc403a2acaa9f2d6bc8241667788bd466c6ad7c1c406`.

| Criterio | Órdenes distintas coincidentes | Pares orden-fila |
|---|---:|---:|
| Igualdad literal | 0 | 0 |
| Limpieza básica | 4 | 4 |
| Normalizador real de Qwen | 8 | 8 |

Son ocho órdenes con alguna coincidencia, no doce: los criterios se solapan.

| Intención | Coinciden tras normalizar | Paráfrasis sin coincidencia directa | Fila del dataset |
|---|---|---|---:|
| INT-04: mug desde cabinet al operador | DEV-010, DEV-012 | DEV-011 | 4671 |
| INT-09: seguir a la persona que saluda en bedroom | DEV-025, DEV-027 | DEV-026 | 35245 |
| INT-11: contar toys en storage rack | DEV-031, DEV-033 | DEV-032 | 6467 |
| INT-14: responder a la persona que saluda en corridor | DEV-040, DEV-042 | DEV-041 | 18455 |

Se conservan las 60 entradas sin cambios. Las ocho coincidencias se identifican como tales. Las cuatro paráfrasis asociadas no son coincidencias de texto detectadas, pero comparten intención con esos casos; sus grupos completos se tratarán como diagnósticos conocidos. Las otras 48 órdenes pertenecen a grupos sin coincidencias detectadas, lo que tampoco certifica novedad semántica. Las 52 órdenes sin coincidencia directa incluyen las cuatro paráfrasis anteriores.

Esta auditoría no determina si las filas coincidentes quedaron en entrenamiento o validación, ni acredita memorización del modelo. Tampoco certifica la corrección de las referencias. Toda instancia de desarrollo y sus variantes se excluirán de la prueba final. No se cambian los objetivos ni los criterios para favorecer las salidas de los sistemas.

En las fichas, `overlap_status` describe la coincidencia de la entrada y `intent_overlap_status` describe la coincidencia de alguna variante de su grupo. La historia conserva las filas y huellas de cada auditoría. La revisión de referencias y las ejecuciones del piloto permanecen pendientes.

## Revisión por caso

### DEV-001 · INT-01 · canonica

**Orden:** Go to the corridor, then go to the inspection point.

**Grupo:** navegacion. **Bloque:** funcional_y_linguistico.

**Propósito:** Orden de dos visitas y distinción entre inspection point e instruction_point. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(corridor)
go(inspection point)
```

**Subtareas requeridas:**

- Visitar corridor.
- Después visitar inspection point; distinguirlo de instruction_point.

**Restricciones:**

- La visita a corridor precede a la visita a inspection point.
- El retorno de cierre no sustituye ninguna de las visitas solicitadas.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-002 · INT-01 · parafrasis

**Orden:** Visit the corridor first and the inspection point afterwards.

**Grupo:** navegacion. **Bloque:** funcional_y_linguistico.

**Propósito:** Orden de dos visitas y distinción entre inspection point e instruction_point. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(corridor)
go(inspection point)
```

**Subtareas requeridas:**

- Visitar corridor.
- Después visitar inspection point; distinguirlo de instruction_point.

**Restricciones:**

- La visita a corridor precede a la visita a inspection point.
- El retorno de cierre no sustituye ninguna de las visitas solicitadas.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-003 · INT-01 · ruido_leve

**Orden:** please go go to the corridor then go to the inspection point

**Grupo:** navegacion. **Bloque:** funcional_y_linguistico.

**Propósito:** Orden de dos visitas y distinción entre inspection point e instruction_point. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(corridor)
go(inspection point)
```

**Subtareas requeridas:**

- Visitar corridor.
- Después visitar inspection point; distinguirlo de instruction_point.

**Restricciones:**

- La visita a corridor precede a la visita a inspection point.
- El retorno de cierre no sustituye ninguna de las visitas solicitadas.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-004 · INT-02 · canonica

**Orden:** Find a peach in the bathroom.

**Grupo:** busqueda_objeto. **Bloque:** funcional_y_linguistico.

**Propósito:** Objeto y habitación. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bathroom)
find(peach, kind=object)
```

**Subtareas requeridas:**

- Ir a bathroom.
- Buscar peach en bathroom.

**Restricciones:**

- No adquirir ni transportar el objeto: solo se solicita localizarlo.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-005 · INT-02 · parafrasis

**Orden:** Look for a peach inside the bathroom.

**Grupo:** busqueda_objeto. **Bloque:** funcional_y_linguistico.

**Propósito:** Objeto y habitación. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bathroom)
find(peach, kind=object)
```

**Subtareas requeridas:**

- Ir a bathroom.
- Buscar peach en bathroom.

**Restricciones:**

- No adquirir ni transportar el objeto: solo se solicita localizarlo.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-006 · INT-02 · ruido_leve

**Orden:** please find a peach in the bathrom

**Grupo:** busqueda_objeto. **Bloque:** funcional_y_linguistico.

**Propósito:** Objeto y habitación. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bathroom)
find(peach, kind=object)
```

**Subtareas requeridas:**

- Ir a bathroom.
- Buscar peach en bathroom.

**Restricciones:**

- No adquirir ni transportar el objeto: solo se solicita localizarlo.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-007 · INT-03 · canonica

**Orden:** Find a spoon at the bed and take it.

**Grupo:** adquisicion. **Bloque:** funcional_y_linguistico.

**Propósito:** Referencia pronominal y adquisición. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bed)
find(spoon, kind=object)
take(spoon)
```

**Subtareas requeridas:**

- Ir a bed.
- Localizar spoon.
- Adquirir ese mismo spoon.

**Restricciones:**

- La búsqueda precede a la adquisición; it refiere a spoon.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-008 · INT-03 · parafrasis

**Orden:** Pick up the spoon you find at the bed.

**Grupo:** adquisicion. **Bloque:** funcional_y_linguistico.

**Propósito:** Referencia pronominal y adquisición. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bed)
find(spoon, kind=object)
take(spoon)
```

**Subtareas requeridas:**

- Ir a bed.
- Localizar spoon.
- Adquirir ese mismo spoon.

**Restricciones:**

- La búsqueda precede a la adquisición; it refiere a spoon.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-009 · INT-03 · ruido_leve

**Orden:** please find a spoon at the bed and and take it

**Grupo:** adquisicion. **Bloque:** funcional_y_linguistico.

**Propósito:** Referencia pronominal y adquisición. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bed)
find(spoon, kind=object)
take(spoon)
```

**Subtareas requeridas:**

- Ir a bed.
- Localizar spoon.
- Adquirir ese mismo spoon.

**Restricciones:**

- La búsqueda precede a la adquisición; it refiere a spoon.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-010 · INT-04 · canonica

**Orden:** Bring me a mug from the cabinet.

**Grupo:** entrega_operador. **Bloque:** funcional_y_linguistico.

**Propósito:** Origen y destinatario me. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(cabinet)
find(mug, kind=object)
take(mug)
deliver(mug, to=me)
```

**Subtareas requeridas:**

- Buscar y adquirir mug en cabinet.
- Regresar al punto del operador y entregarle mug.

**Restricciones:**

- No confundir el origen cabinet con el destinatario.
- La entrega requiere adquisición previa y una acción de entrega, no solo un anuncio.

**Auditoría de la entrada:** `coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-011 · INT-04 · parafrasis

**Orden:** Fetch a mug at the cabinet and deliver it to me.

**Grupo:** entrega_operador. **Bloque:** funcional_y_linguistico.

**Propósito:** Origen y destinatario me. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(cabinet)
find(mug, kind=object)
take(mug)
deliver(mug, to=me)
```

**Subtareas requeridas:**

- Buscar y adquirir mug en cabinet.
- Regresar al punto del operador y entregarle mug.

**Restricciones:**

- No confundir el origen cabinet con el destinatario.
- La entrega requiere adquisición previa y una acción de entrega, no solo un anuncio.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-012 · INT-04 · ruido_leve

**Orden:** please bring me a mug from the cabnet

**Grupo:** entrega_operador. **Bloque:** funcional_y_linguistico.

**Propósito:** Origen y destinatario me. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(cabinet)
find(mug, kind=object)
take(mug)
deliver(mug, to=me)
```

**Subtareas requeridas:**

- Buscar y adquirir mug en cabinet.
- Regresar al punto del operador y entregarle mug.

**Restricciones:**

- No confundir el origen cabinet con el destinatario.
- La entrega requiere adquisición previa y una acción de entrega, no solo un anuncio.

**Auditoría de la entrada:** `coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-013 · INT-05 · canonica

**Orden:** Bring a bowl from the bed to the storage rack.

**Grupo:** transporte_ubicaciones. **Bloque:** funcional_y_linguistico.

**Propósito:** Destino navegable de colocación. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bed)
find(bowl, kind=object)
take(bowl)
place(bowl, at=storage rack)
```

**Subtareas requeridas:**

- Buscar y adquirir bowl en bed.
- Trasladarlo a storage rack y colocarlo allí.

**Restricciones:**

- bed es el origen y storage rack es el destino; no invertirlos.
- Llegar al destino antes de colocar el objeto.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-014 · INT-05 · parafrasis

**Orden:** Collect a bowl at the bed and leave it at the storage rack.

**Grupo:** transporte_ubicaciones. **Bloque:** funcional_y_linguistico.

**Propósito:** Destino navegable de colocación. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bed)
find(bowl, kind=object)
take(bowl)
place(bowl, at=storage rack)
```

**Subtareas requeridas:**

- Buscar y adquirir bowl en bed.
- Trasladarlo a storage rack y colocarlo allí.

**Restricciones:**

- bed es el origen y storage rack es el destino; no invertirlos.
- Llegar al destino antes de colocar el objeto.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-015 · INT-05 · ruido_leve

**Orden:** please bring a bowl from the bed to the storage  rack

**Grupo:** transporte_ubicaciones. **Bloque:** funcional_y_linguistico.

**Propósito:** Destino navegable de colocación. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bed)
find(bowl, kind=object)
take(bowl)
place(bowl, at=storage rack)
```

**Subtareas requeridas:**

- Buscar y adquirir bowl en bed.
- Trasladarlo a storage rack y colocarlo allí.

**Restricciones:**

- bed es el origen y storage rack es el destino; no invertirlos.
- Llegar al destino antes de colocar el objeto.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-016 · INT-06 · canonica

**Orden:** In the kitchen, find a cup, take it, and put it on the table.

**Grupo:** colocacion_local. **Bloque:** funcional_y_linguistico.

**Propósito:** Soporte local y relación on. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(cup, kind=object)
take(cup)
place(cup, on=table)
```

**Subtareas requeridas:**

- Buscar y adquirir cup en kitchen.
- Colocar cup sobre la mesa local de kitchen.

**Restricciones:**

- table es un soporte local, no una habitación ni un punto de navegación adicional.
- No confundir colocación con entrega a una persona.

**Límites de verificación:**

- La regla place puede asignar el soporte a location; revisar la representación del estado sin inferir desplazamiento físico.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-017 · INT-06 · parafrasis

**Orden:** Locate a cup in the kitchen and pick it up, then place it on the table there.

**Grupo:** colocacion_local. **Bloque:** funcional_y_linguistico.

**Propósito:** Soporte local y relación on. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(cup, kind=object)
take(cup)
place(cup, on=table)
```

**Subtareas requeridas:**

- Buscar y adquirir cup en kitchen.
- Colocar cup sobre la mesa local de kitchen.

**Restricciones:**

- table es un soporte local, no una habitación ni un punto de navegación adicional.
- No confundir colocación con entrega a una persona.

**Límites de verificación:**

- La regla place puede asignar el soporte a location; revisar la representación del estado sin inferir desplazamiento físico.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-018 · INT-06 · ruido_leve

**Orden:** in the kichen find a cup take it and put it on the table please

**Grupo:** colocacion_local. **Bloque:** funcional_y_linguistico.

**Propósito:** Soporte local y relación on. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(cup, kind=object)
take(cup)
place(cup, on=table)
```

**Subtareas requeridas:**

- Buscar y adquirir cup en kitchen.
- Colocar cup sobre la mesa local de kitchen.

**Restricciones:**

- table es un soporte local, no una habitación ni un punto de navegación adicional.
- No confundir colocación con entrega a una persona.

**Límites de verificación:**

- La regla place puede asignar el soporte a location; revisar la representación del estado sin inferir desplazamiento físico.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-019 · INT-07 · canonica

**Orden:** Find Robin in the office.

**Grupo:** busqueda_persona_nombre. **Bloque:** funcional_y_linguistico.

**Propósito:** Nombre propio y tipo person. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(office)
find(Robin, kind=person)
```

**Subtareas requeridas:**

- Ir a office y localizar a la persona llamada Robin.

**Restricciones:**

- No tratar Robin como objeto o ubicación.
- Buscar a anybody sin un mecanismo de identificación no acredita encontrar a Robin.

**Límites de verificación:**

- Separar conformidad con el protocolo ask_name/listen de la verificación efectiva del nombre: la coincidencia de identidad requiere revisión del contrato del ejecutor.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-020 · INT-07 · parafrasis

**Orden:** Look for Robin inside the office.

**Grupo:** busqueda_persona_nombre. **Bloque:** funcional_y_linguistico.

**Propósito:** Nombre propio y tipo person. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(office)
find(Robin, kind=person)
```

**Subtareas requeridas:**

- Ir a office y localizar a la persona llamada Robin.

**Restricciones:**

- No tratar Robin como objeto o ubicación.
- Buscar a anybody sin un mecanismo de identificación no acredita encontrar a Robin.

**Límites de verificación:**

- Separar conformidad con el protocolo ask_name/listen de la verificación efectiva del nombre: la coincidencia de identidad requiere revisión del contrato del ejecutor.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-021 · INT-07 · ruido_leve

**Orden:** please find Robin in the ofice

**Grupo:** busqueda_persona_nombre. **Bloque:** funcional_y_linguistico.

**Propósito:** Nombre propio y tipo person. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(office)
find(Robin, kind=person)
```

**Subtareas requeridas:**

- Ir a office y localizar a la persona llamada Robin.

**Restricciones:**

- No tratar Robin como objeto o ubicación.
- Buscar a anybody sin un mecanismo de identificación no acredita encontrar a Robin.

**Límites de verificación:**

- Separar conformidad con el protocolo ask_name/listen de la verificación efectiva del nombre: la coincidencia de identidad requiere revisión del contrato del ejecutor.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-022 · INT-08 · canonica

**Orden:** Find Morgan in the kitchen and guide them to the entrance.

**Grupo:** guia. **Bloque:** funcional_y_linguistico.

**Propósito:** Origen, persona y destino. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(Morgan, kind=person)
guide(Morgan, to=entrance)
```

**Subtareas requeridas:**

- Localizar a Morgan en kitchen.
- Indicar a Morgan que siga al robot y guiarle a entrance.

**Restricciones:**

- Resolver them como Morgan; conservar entrance como destino.
- Un desplazamiento sin vincular a la persona no cubre por sí solo la subtarea de guía.

**Límites de verificación:**

- Identidad de la persona sujeta al contrato de identificación; presencia física durante la guía fuera del alcance.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-023 · INT-08 · parafrasis

**Orden:** Meet Morgan in the kitchen, then lead Morgan to the entrance.

**Grupo:** guia. **Bloque:** funcional_y_linguistico.

**Propósito:** Origen, persona y destino. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(Morgan, kind=person)
guide(Morgan, to=entrance)
```

**Subtareas requeridas:**

- Localizar a Morgan en kitchen.
- Indicar a Morgan que siga al robot y guiarle a entrance.

**Restricciones:**

- Resolver them como Morgan; conservar entrance como destino.
- Un desplazamiento sin vincular a la persona no cubre por sí solo la subtarea de guía.

**Límites de verificación:**

- Identidad de la persona sujeta al contrato de identificación; presencia física durante la guía fuera del alcance.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-024 · INT-08 · ruido_leve

**Orden:** find Morgan in the kichen and guide them to the entrance please

**Grupo:** guia. **Bloque:** funcional_y_linguistico.

**Propósito:** Origen, persona y destino. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(Morgan, kind=person)
guide(Morgan, to=entrance)
```

**Subtareas requeridas:**

- Localizar a Morgan en kitchen.
- Indicar a Morgan que siga al robot y guiarle a entrance.

**Restricciones:**

- Resolver them como Morgan; conservar entrance como destino.
- Un desplazamiento sin vincular a la persona no cubre por sí solo la subtarea de guía.

**Límites de verificación:**

- Identidad de la persona sujeta al contrato de identificación; presencia física durante la guía fuera del alcance.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-025 · INT-09 · canonica

**Orden:** Find the waving person in the bedroom and follow them.

**Grupo:** seguimiento. **Bloque:** funcional_y_linguistico.

**Propósito:** Gesto y referencia a la persona. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bedroom)
find(person, kind=person, gesture='waving person')
follow(person)
```

**Subtareas requeridas:**

- Localizar una persona que saluda con la mano en bedroom.
- Iniciar seguimiento de esa misma persona sin inventar un destino.

**Restricciones:**

- El gesto debe conservarse en la búsqueda.
- El seguimiento debe corresponder al referente encontrado.

**Límites de verificación:**

- instruct_follow_only es una clave de protocolo. Su presencia no demuestra seguimiento; cumplimiento operativo no verificable hasta precisar el contrato del ejecutor.

**Auditoría de la entrada:** `coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-026 · INT-09 · parafrasis

**Orden:** In the bedroom, locate the person who is waving and follow that person.

**Grupo:** seguimiento. **Bloque:** funcional_y_linguistico.

**Propósito:** Gesto y referencia a la persona. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bedroom)
find(person, kind=person, gesture='waving person')
follow(person)
```

**Subtareas requeridas:**

- Localizar una persona que saluda con la mano en bedroom.
- Iniciar seguimiento de esa misma persona sin inventar un destino.

**Restricciones:**

- El gesto debe conservarse en la búsqueda.
- El seguimiento debe corresponder al referente encontrado.

**Límites de verificación:**

- instruct_follow_only es una clave de protocolo. Su presencia no demuestra seguimiento; cumplimiento operativo no verificable hasta precisar el contrato del ejecutor.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-027 · INT-09 · ruido_leve

**Orden:** please find the waving person in the bedrom and follow them

**Grupo:** seguimiento. **Bloque:** funcional_y_linguistico.

**Propósito:** Gesto y referencia a la persona. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bedroom)
find(person, kind=person, gesture='waving person')
follow(person)
```

**Subtareas requeridas:**

- Localizar una persona que saluda con la mano en bedroom.
- Iniciar seguimiento de esa misma persona sin inventar un destino.

**Restricciones:**

- El gesto debe conservarse en la búsqueda.
- El seguimiento debe corresponder al referente encontrado.

**Límites de verificación:**

- instruct_follow_only es una clave de protocolo. Su presencia no demuestra seguimiento; cumplimiento operativo no verificable hasta precisar el contrato del ejecutor.

**Auditoría de la entrada:** `coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-028 · INT-10 · canonica

**Orden:** Take an orange from the refrigerator and give it to Sarah in the kitchen.

**Grupo:** entrega_persona. **Bloque:** funcional_y_linguistico.

**Propósito:** Cambio de referente objeto-persona. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(refrigerator)
find(orange, kind=object)
take(orange)
go(kitchen)
find(Sarah, kind=person)
deliver(orange, to=Sarah)
```

**Subtareas requeridas:**

- Adquirir orange en refrigerator.
- Localizar a Sarah en kitchen.
- Entregar a Sarah la misma orange.

**Restricciones:**

- Conservar el objeto al cambiar de ubicación y buscar a Sarah.
- No entregar al operador ni confundir orange con un atributo de ropa.

**Límites de verificación:**

- Verificar el enlace entre el nombre Sarah y la referencia interna del destinatario.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-029 · INT-10 · parafrasis

**Orden:** Fetch an orange at the refrigerator, then find Sarah in the kitchen and hand the orange to her.

**Grupo:** entrega_persona. **Bloque:** funcional_y_linguistico.

**Propósito:** Cambio de referente objeto-persona. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(refrigerator)
find(orange, kind=object)
take(orange)
go(kitchen)
find(Sarah, kind=person)
deliver(orange, to=Sarah)
```

**Subtareas requeridas:**

- Adquirir orange en refrigerator.
- Localizar a Sarah en kitchen.
- Entregar a Sarah la misma orange.

**Restricciones:**

- Conservar el objeto al cambiar de ubicación y buscar a Sarah.
- No entregar al operador ni confundir orange con un atributo de ropa.

**Límites de verificación:**

- Verificar el enlace entre el nombre Sarah y la referencia interna del destinatario.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-030 · INT-10 · ruido_leve

**Orden:** take an orange from the refridgerator and give it to Sarah in the kichen

**Grupo:** entrega_persona. **Bloque:** funcional_y_linguistico.

**Propósito:** Cambio de referente objeto-persona. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(refrigerator)
find(orange, kind=object)
take(orange)
go(kitchen)
find(Sarah, kind=person)
deliver(orange, to=Sarah)
```

**Subtareas requeridas:**

- Adquirir orange en refrigerator.
- Localizar a Sarah en kitchen.
- Entregar a Sarah la misma orange.

**Restricciones:**

- Conservar el objeto al cambiar de ubicación y buscar a Sarah.
- No entregar al operador ni confundir orange con un atributo de ropa.

**Límites de verificación:**

- Verificar el enlace entre el nombre Sarah y la referencia interna del destinatario.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-031 · INT-11 · canonica

**Orden:** Count the toys on the storage rack.

**Grupo:** conteo_objetos. **Bloque:** funcional_y_linguistico.

**Propósito:** Categoría y comunicación del resultado. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(storage rack)
count(toys, kind=object)
```

**Subtareas requeridas:**

- Contar toys en storage rack y comunicar el conteo al operador.

**Restricciones:**

- No inventar una cantidad: el plan debe solicitar el análisis y la comunicación del resultado.
- La categoría completa toys debe preservarse.

**Auditoría de la entrada:** `coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-032 · INT-11 · parafrasis

**Orden:** Tell me how many toys are on the storage rack.

**Grupo:** conteo_objetos. **Bloque:** funcional_y_linguistico.

**Propósito:** Categoría y comunicación del resultado. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(storage rack)
count(toys, kind=object)
```

**Subtareas requeridas:**

- Contar toys en storage rack y comunicar el conteo al operador.

**Restricciones:**

- No inventar una cantidad: el plan debe solicitar el análisis y la comunicación del resultado.
- La categoría completa toys debe preservarse.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-033 · INT-11 · ruido_leve

**Orden:** please count the the toys on the storage rack

**Grupo:** conteo_objetos. **Bloque:** funcional_y_linguistico.

**Propósito:** Categoría y comunicación del resultado. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(storage rack)
count(toys, kind=object)
```

**Subtareas requeridas:**

- Contar toys en storage rack y comunicar el conteo al operador.

**Restricciones:**

- No inventar una cantidad: el plan debe solicitar el análisis y la comunicación del resultado.
- La categoría completa toys debe preservarse.

**Auditoría de la entrada:** `coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-034 · INT-12 · canonica

**Orden:** Find Charlie in the living room and tell Charlie the current time.

**Grupo:** informacion_fija. **Bloque:** funcional_y_linguistico.

**Propósito:** Información y persona destinataria. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(living room)
find(Charlie, kind=person)
tell(current_time)
```

**Subtareas requeridas:**

- Localizar a Charlie en living room.
- Comunicarle la hora actual.

**Restricciones:**

- Normalizar la información a current_time y conservar el contexto de Charlie.
- No reemplazar la hora por fecha o nombre del equipo.

**Límites de verificación:**

- Comprobar que el diálogo se dirige a la persona identificada; no inferir identidad correcta de un simple acuse hablado.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-035 · INT-12 · parafrasis

**Orden:** Locate Charlie in the living room and say what time it is to Charlie.

**Grupo:** informacion_fija. **Bloque:** funcional_y_linguistico.

**Propósito:** Información y persona destinataria. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(living room)
find(Charlie, kind=person)
tell(current_time)
```

**Subtareas requeridas:**

- Localizar a Charlie en living room.
- Comunicarle la hora actual.

**Restricciones:**

- Normalizar la información a current_time y conservar el contexto de Charlie.
- No reemplazar la hora por fecha o nombre del equipo.

**Límites de verificación:**

- Comprobar que el diálogo se dirige a la persona identificada; no inferir identidad correcta de un simple acuse hablado.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-036 · INT-12 · ruido_leve

**Orden:** please find Charlie in the living  room and tell Charlie the current time

**Grupo:** informacion_fija. **Bloque:** funcional_y_linguistico.

**Propósito:** Información y persona destinataria. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(living room)
find(Charlie, kind=person)
tell(current_time)
```

**Subtareas requeridas:**

- Localizar a Charlie en living room.
- Comunicarle la hora actual.

**Restricciones:**

- Normalizar la información a current_time y conservar el contexto de Charlie.
- No reemplazar la hora por fecha o nombre del equipo.

**Límites de verificación:**

- Comprobar que el diálogo se dirige a la persona identificada; no inferir identidad correcta de un simple acuse hablado.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-037 · INT-13 · canonica

**Orden:** Find a person in the bedroom, ask their name, and come back to tell me their name.

**Grupo:** guardar_informacion. **Bloque:** funcional_y_linguistico.

**Propósito:** Información adquirida y retorno. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bedroom)
find(person, kind=person)
save(name)
go(instruction_point)
tell(name)
```

**Subtareas requeridas:**

- Encontrar una persona en bedroom y adquirir su nombre.
- Regresar al operador y comunicar el nombre adquirido.

**Restricciones:**

- No inventar el nombre ni confundirlo con un nombre fijo del catálogo.
- La comunicación al operador debe referirse a la información adquirida.

**Límites de verificación:**

- La persistencia y recuperación de saved_name deben verificarse respecto del contrato del ejecutor.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-038 · INT-13 · parafrasis

**Orden:** Go to the bedroom, learn the name of a person there, then return and report it to me.

**Grupo:** guardar_informacion. **Bloque:** funcional_y_linguistico.

**Propósito:** Información adquirida y retorno. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bedroom)
find(person, kind=person)
save(name)
go(instruction_point)
tell(name)
```

**Subtareas requeridas:**

- Encontrar una persona en bedroom y adquirir su nombre.
- Regresar al operador y comunicar el nombre adquirido.

**Restricciones:**

- No inventar el nombre ni confundirlo con un nombre fijo del catálogo.
- La comunicación al operador debe referirse a la información adquirida.

**Límites de verificación:**

- La persistencia y recuperación de saved_name deben verificarse respecto del contrato del ejecutor.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-039 · INT-13 · ruido_leve

**Orden:** please find a person in the bedroom ask their name and come back to tell me their name

**Grupo:** guardar_informacion. **Bloque:** funcional_y_linguistico.

**Propósito:** Información adquirida y retorno. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(bedroom)
find(person, kind=person)
save(name)
go(instruction_point)
tell(name)
```

**Subtareas requeridas:**

- Encontrar una persona en bedroom y adquirir su nombre.
- Regresar al operador y comunicar el nombre adquirido.

**Restricciones:**

- No inventar el nombre ni confundirlo con un nombre fijo del catálogo.
- La comunicación al operador debe referirse a la información adquirida.

**Límites de verificación:**

- La persistencia y recuperación de saved_name deben verificarse respecto del contrato del ejecutor.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-040 · INT-14 · canonica

**Orden:** Find the waving person in the corridor and answer their question.

**Grupo:** respuesta_pregunta. **Bloque:** funcional_y_linguistico.

**Propósito:** Interacción y escucha previa. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(corridor)
find(person, kind=person, gesture='waving person')
answer_question()
```

**Subtareas requeridas:**

- Localizar en corridor a la persona que saluda con la mano.
- Escuchar su pregunta y solicitar la respuesta.

**Restricciones:**

- Conservar el contexto de esa persona.
- No inventar la pregunta ni una respuesta concreta en el plan.

**Auditoría de la entrada:** `coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-041 · INT-14 · parafrasis

**Orden:** In the corridor, locate the person who is waving and respond to that person's question.

**Grupo:** respuesta_pregunta. **Bloque:** funcional_y_linguistico.

**Propósito:** Interacción y escucha previa. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(corridor)
find(person, kind=person, gesture='waving person')
answer_question()
```

**Subtareas requeridas:**

- Localizar en corridor a la persona que saluda con la mano.
- Escuchar su pregunta y solicitar la respuesta.

**Restricciones:**

- Conservar el contexto de esa persona.
- No inventar la pregunta ni una respuesta concreta en el plan.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-042 · INT-14 · ruido_leve

**Orden:** find the waving person in the corridor and and answer their question please

**Grupo:** respuesta_pregunta. **Bloque:** funcional_y_linguistico.

**Propósito:** Interacción y escucha previa. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(corridor)
find(person, kind=person, gesture='waving person')
answer_question()
```

**Subtareas requeridas:**

- Localizar en corridor a la persona que saluda con la mano.
- Escuchar su pregunta y solicitar la respuesta.

**Restricciones:**

- Conservar el contexto de esa persona.
- No inventar la pregunta ni una respuesta concreta en el plan.

**Auditoría de la entrada:** `coincidencia_detectada_v02`. **Grupo de intención:** `grupo_con_variantes_coincidentes_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-043 · INT-15 · canonica

**Orden:** Find Jane in the kitchen and greet her.

**Grupo:** saludo. **Bloque:** funcional_y_linguistico.

**Propósito:** Persona nombrada e interacción. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(Jane, kind=person)
greet(Jane)
```

**Subtareas requeridas:**

- Localizar a Jane en kitchen y saludarla.

**Restricciones:**

- Resolver her como Jane; no saludar al operador ni a una persona distinta.

**Límites de verificación:**

- La identificación por nombre debe distinguirse de la búsqueda de una persona cualquiera.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-044 · INT-15 · parafrasis

**Orden:** Look for Jane in the kitchen and say hello to Jane.

**Grupo:** saludo. **Bloque:** funcional_y_linguistico.

**Propósito:** Persona nombrada e interacción. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(Jane, kind=person)
greet(Jane)
```

**Subtareas requeridas:**

- Localizar a Jane en kitchen y saludarla.

**Restricciones:**

- Resolver her como Jane; no saludar al operador ni a una persona distinta.

**Límites de verificación:**

- La identificación por nombre debe distinguirse de la búsqueda de una persona cualquiera.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-045 · INT-15 · ruido_leve

**Orden:** please find Jane in the kichen and greet her

**Grupo:** saludo. **Bloque:** funcional_y_linguistico.

**Propósito:** Persona nombrada e interacción. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(Jane, kind=person)
greet(Jane)
```

**Subtareas requeridas:**

- Localizar a Jane en kitchen y saludarla.

**Restricciones:**

- Resolver her como Jane; no saludar al operador ni a una persona distinta.

**Límites de verificación:**

- La identificación por nombre debe distinguirse de la búsqueda de una persona cualquiera.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-046 · INT-16 · canonica

**Orden:** Tell me which is the largest fruit on the sofa.

**Grupo:** propiedad_objeto. **Bloque:** funcional_y_linguistico.

**Propósito:** Comparación de tamaño y reporte. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(sofa)
find(fruit, kind=object, property=largest)
tell(fruit, property=largest)
```

**Subtareas requeridas:**

- Analizar el tamaño de las frutas en sofa y comunicar cuál es la mayor.

**Restricciones:**

- No sustituir tamaño por peso ni buscar un objeto arbitrario.
- biggest y largest son equivalentes semánticos aquí; registrar diferencia literal sin penalizar semántica.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-047 · INT-16 · parafrasis

**Orden:** Identify the biggest fruit on the sofa and report which one it is.

**Grupo:** propiedad_objeto. **Bloque:** funcional_y_linguistico.

**Propósito:** Comparación de tamaño y reporte. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(sofa)
find(fruit, kind=object, property=largest)
tell(fruit, property=largest)
```

**Subtareas requeridas:**

- Analizar el tamaño de las frutas en sofa y comunicar cuál es la mayor.

**Restricciones:**

- No sustituir tamaño por peso ni buscar un objeto arbitrario.
- biggest y largest son equivalentes semánticos aquí; registrar diferencia literal sin penalizar semántica.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-048 · INT-16 · ruido_leve

**Orden:** please tell me which is the largest fruit on the sofa

**Grupo:** propiedad_objeto. **Bloque:** funcional_y_linguistico.

**Propósito:** Comparación de tamaño y reporte. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(sofa)
find(fruit, kind=object, property=largest)
tell(fruit, property=largest)
```

**Subtareas requeridas:**

- Analizar el tamaño de las frutas en sofa y comunicar cuál es la mayor.

**Restricciones:**

- No sustituir tamaño por peso ni buscar un objeto arbitrario.
- biggest y largest son equivalentes semánticos aquí; registrar diferencia literal sin penalizar semántica.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-049 · INT-17 · diagnostico

**Orden:** Find the person waving and wearing a blue coat in the office, then guide them to the entrance.

**Grupo:** atributos_conjuntos. **Bloque:** limites_y_composicion.

**Propósito:** atributos_conjuntos. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(office)
find(person, kind=person, gesture='waving person', wearing='blue coat')
guide(person, to=entrance)
```

**Subtareas requeridas:**

- Buscar en office una única persona que cumpla ambos atributos.
- Guiar a esa persona a entrance.

**Restricciones:**

- La conjunción gesto y vestimenta debe mantenerse; no basta con cualquiera de ellos.

**Límites de verificación:**

- El adaptador conserva un único qualifier y puede perder un atributo; registrar la pérdida.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-050 · INT-18 · diagnostico

**Orden:** Count the people wearing red shirts in the living room.

**Grupo:** conteo_personas_filtrado. **Bloque:** limites_y_composicion.

**Propósito:** conteo_personas_filtrado. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(living room)
count(person, kind=person, wearing='red shirts')
```

**Subtareas requeridas:**

- Contar exclusivamente las personas con camisa roja en living room.
- Comunicar el resultado al operador.

**Restricciones:**

- El plan debe conservar el filtro de vestimenta; un conteo de todas las personas no cumple.

**Límites de verificación:**

- La expansión actual de count puede omitir el filtro; comprobarlo sin equiparar planificabilidad con cumplimiento.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-051 · INT-19 · diagnostico

**Orden:** Tell me which is the heaviest fruit on the sofa.

**Grupo:** propiedad_peso. **Bloque:** limites_y_composicion.

**Propósito:** propiedad_peso. **Respuesta prevista:** `domain_capability_review`.

**Objetivos propuestos:**

```text
go(sofa)
find(fruit, kind=object, property=heaviest)
tell(fruit, property=heaviest)
```

**Subtareas requeridas:**

- Determinar qué fruta tiene mayor peso en sofa y comunicarlo.

**Restricciones:**

- No sustituir peso por tamaño.

**Límites de verificación:**

- heaviest pertenece al vocabulario pero la expansión usa tamaño como aproximación; clasificar proxy_insuficiente si no existe evidencia del peso. No exigir un plan exitoso cuando el repertorio no permite satisfacerlo.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-052 · INT-20 · diagnostico

**Orden:** Find Simone at the coatrack and follow Simone to the bedroom.

**Grupo:** seguimiento_destino. **Bloque:** limites_y_composicion.

**Propósito:** seguimiento_destino. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(coatrack)
find(Simone, kind=person)
follow(Simone, to=bedroom)
```

**Subtareas requeridas:**

- Localizar a Simone en coatrack.
- Seguir a Simone hasta bedroom.

**Restricciones:**

- No convertir seguimiento en guía.
- No ir solo a bedroom antes de localizar a Simone.

**Límites de verificación:**

- El protocolo instruct_follow_to requiere precisar los efectos del ejecutor; un anuncio no acredita llegar siguiendo a Simone.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-053 · INT-21 · diagnostico

**Orden:** Bring me a mug from the refrigerator, then bring me a spoon from the bed.

**Grupo:** composicion_dos_entregas. **Bloque:** limites_y_composicion.

**Propósito:** composicion_dos_entregas. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(refrigerator)
find(mug, kind=object)
take(mug)
deliver(mug, to=me)
go(bed)
find(spoon, kind=object)
take(spoon)
deliver(spoon, to=me)
```

**Subtareas requeridas:**

- Entregar al operador mug desde refrigerator.
- Después entregar al operador spoon desde bed.

**Restricciones:**

- Completar la primera entrega antes de buscar el segundo objeto.
- Reiniciar la posesión tras cada entrega; no reutilizar el identificador de mug para spoon.

**Límites de verificación:**

- Caso para comprobar truncamiento por límite de tokens, conservación de orden y reinicio del estado de posesión.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-054 · INT-22 · diagnostico

**Orden:** Find Water in the kitchen, take it, and bring it to me.

**Grupo:** tipo_independiente_mayusculas. **Bloque:** limites_y_composicion.

**Propósito:** tipo_independiente_mayusculas. **Respuesta prevista:** `executable`.

**Objetivos propuestos:**

```text
go(kitchen)
find(Water, kind=object)
take(Water)
deliver(Water, to=me)
```

**Subtareas requeridas:**

- Buscar y adquirir el objeto Water en kitchen.
- Entregarlo al operador.

**Restricciones:**

- La mayúscula de Water no debe convertir el objeto en una persona.

**Límites de verificación:**

- Examinar la predicción original y el kind calculado por el adaptador por separado.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-055 · INT-23 · limite_dominio

**Orden:** Go to the kitchen and bring it to me.

**Grupo:** referente_ausente. **Bloque:** ambiguedad_y_fuera_dominio.

**Propósito:** referente_ausente. **Respuesta prevista:** `clarification`.

**Información/razón:** ¿Qué objeto debe llevarse al operador?

**Objetivos de referencia:** no aplican mientras no exista una instrucción resoluble.

**Restricciones:**

- No completar datos faltantes ni generar un plan completo apoyado en suposiciones no autorizadas.

**Límites de verificación:**

- Qwen no implementa el mismo contrato conversacional: registrar su respuesta observada sin equiparar error de esquema y aclaración.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-056 · INT-24 · limite_dominio

**Orden:** Find Robin in the office and guide Robin to the destination.

**Grupo:** destino_ausente. **Bloque:** ambiguedad_y_fuera_dominio.

**Propósito:** destino_ausente. **Respuesta prevista:** `clarification`.

**Información/razón:** ¿Cuál es el destino al que debe guiarse a Robin?

**Objetivos de referencia:** no aplican mientras no exista una instrucción resoluble.

**Restricciones:**

- No completar datos faltantes ni generar un plan completo apoyado en suposiciones no autorizadas.

**Límites de verificación:**

- Qwen no implementa el mismo contrato conversacional: registrar su respuesta observada sin equiparar error de esquema y aclaración.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-057 · INT-25 · limite_dominio

**Orden:** Take a fork from the shelf and give it to her.

**Grupo:** destinatario_ausente. **Bloque:** ambiguedad_y_fuera_dominio.

**Propósito:** destinatario_ausente. **Respuesta prevista:** `clarification`.

**Información/razón:** ¿A quién se refiere her?

**Objetivos de referencia:** no aplican mientras no exista una instrucción resoluble.

**Restricciones:**

- No completar datos faltantes ni generar un plan completo apoyado en suposiciones no autorizadas.

**Límites de verificación:**

- Qwen no implementa el mismo contrato conversacional: registrar su respuesta observada sin equiparar error de esquema y aclaración.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-058 · INT-26 · limite_dominio

**Orden:** Fly to the ceiling and inspect the lamp.

**Grupo:** accion_fuera_repertorio. **Bloque:** ambiguedad_y_fuera_dominio.

**Propósito:** accion_fuera_repertorio. **Respuesta prevista:** `rejected`.

**Información/razón:** Volar e inspeccionar la lámpara excede el repertorio definido.

**Objetivos de referencia:** no aplican mientras no exista una instrucción resoluble.

**Restricciones:**

- No completar datos faltantes ni generar un plan completo apoyado en suposiciones no autorizadas.

**Límites de verificación:**

- Qwen no implementa el mismo contrato conversacional: registrar su respuesta observada sin equiparar error de esquema y aclaración.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-059 · INT-27 · limite_dominio

**Orden:** Set the thermostat to twenty degrees.

**Grupo:** dispositivo_fuera_repertorio. **Bloque:** ambiguedad_y_fuera_dominio.

**Propósito:** dispositivo_fuera_repertorio. **Respuesta prevista:** `rejected`.

**Información/razón:** Controlar el termostato no pertenece al repertorio de acciones.

**Objetivos de referencia:** no aplican mientras no exista una instrucción resoluble.

**Restricciones:**

- No completar datos faltantes ni generar un plan completo apoyado en suposiciones no autorizadas.

**Límites de verificación:**

- Qwen no implementa el mismo contrato conversacional: registrar su respuesta observada sin equiparar error de esquema y aclaración.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

### DEV-060 · INT-28 · limite_dominio

**Orden:** Pick up the apple on the shelf, but do not pick up the apple.

**Grupo:** restriccion_contradictoria. **Bloque:** ambiguedad_y_fuera_dominio.

**Propósito:** restriccion_contradictoria. **Respuesta prevista:** `rejected`.

**Información/razón:** La misma adquisición se exige y se prohíbe en la instrucción.

**Objetivos de referencia:** no aplican mientras no exista una instrucción resoluble.

**Restricciones:**

- No completar datos faltantes ni generar un plan completo apoyado en suposiciones no autorizadas.

**Límites de verificación:**

- Qwen no implementa el mismo contrato conversacional: registrar su respuesta observada sin equiparar error de esquema y aclaración.

**Auditoría de la entrada:** `sin_coincidencia_detectada_v02`. **Grupo de intención:** `grupo_sin_coincidencias_detectadas_v02`.

**Revisión del investigador:** pendiente. **Resultados de modelos:** no ejecutados.

