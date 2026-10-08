> Ejecutar los comandos desde la raíz del repositorio.

# Guía del experimento y del borrador del capítulo 6

Versión 0.1 — 22 de septiembre de 2026. Propuesta para revisión; la comparación final todavía no se ha ejecutado.

## Qué buscamos demostrar

La pregunta es con qué fidelidad y consistencia las configuraciones Qwen–CLIPS y GPT directo convierten una orden del dominio en un plan. Se evaluará el producto computacional y las etapas observables. No se medirán percepción, navegación física, manipulación real ni seguridad del robot.

La comparación no permite atribuir una diferencia exclusivamente a CLIPS: también cambian el modelo, su adaptación y el acceso al conocimiento del dominio. GPT recibe instrucciones detalladas de las convenciones de expansión. Las conclusiones describirán estos dos sistemas concretos.

## Pruebas y evidencias

| Prueba | Qué hacemos | Qué buscamos | Qué no demuestra |
|---|---|---|---|
| Recorrido y registro | Enviar una orden y conservar todas las etapas disponibles | Saber de qué orden procede cada resultado, detectar tiempos agotados y respuestas tardías | Calidad semántica |
| Interpretación | Comparar objetivos originales con la ficha revisada | Subtareas, objeto, lugar, destinatario, atributos y dependencias correctos | Que exista un plan adecuado |
| Contrato | Analizar objetivos y acciones, argumentos y numeración | Formato y repertorio válidos | Cumplimiento de la orden |
| Cumplimiento del plan | Aplicar restricciones y efectos documentados de las acciones | Que todas las subtareas estén cubiertas, sin operaciones contradictorias | Éxito físico |
| Control de CLIPS | Pasar objetivos de referencia por el mismo adaptador y reglas | Examinar adaptación y expansión sin el error de interpretación de Qwen | Que el plan de control sea automáticamente correcto |
| Variación lingüística | Formular la misma intención de tres maneras | Conservar corrección ante paráfrasis y ruido | Independencia entre las tres observaciones |
| Composición | Aumentar subtareas y dependencias de manera identificada | Conservar objetos, destinatarios, orden y salida completa | Un efecto puro de longitud si cambian otras dificultades |
| Límites del dominio | Usar ambigüedad, contradicción o acciones no soportadas | Describir aclaración, rechazo, bloqueo o invención de tareas | Comparabilidad directa de contratos conversacionales distintos |
| Rendimiento | Medir tiempo completo, fallos, recursos locales y tokens | Caracterizar el coste observable del servicio | Memoria o energía internas del proveedor GPT |

## Ejemplo para entender la calificación

Orden de desarrollo: **Bring me a mug from the cabinet.**

Referencia propuesta:

```text
go(cabinet)
find(mug, kind=object)
take(mug)
deliver(mug, to=me)
```

Antes de observar los modelos se revisará que esta referencia represente correctamente la orden. La ficha pedirá encontrar y adquirir la taza en cabinet y entregarla al operador. El plan podrá usar anuncios y referencias internas diferentes, siempre que conserve los efectos y las dependencias.

| Resultado hipotético | Interpretación |
|---|---|
| Objetivos con refrigerator en vez de cabinet | Error semántico de ubicación |
| Objetivos correctos; adaptación altera el destinatario | Error de adaptación |
| Objetivos y hechos correctos; el plan entrega sin adquirir | Error de planificación |
| El plan dice «tarea completada» sin realizar las subtareas | Terminación formal sin cumplimiento |
| Objetivos y plan correctos con otros anuncios equivalentes | Resultado admisible |
| No llega respuesta antes del límite | Fallo de extremo a extremo; registrar origen técnico si se conoce |

Son ejemplos de calificación, no resultados observados. El plan producido al alimentar CLIPS con la referencia también debe pasar por esta evaluación.

## Cómo se realizará, en orden

1. **Revisar las fichas.** Confirmar intención, objetivos, restricciones y capacidades evaluables. No convertir una salida de CLIPS en referencia por el mero hecho de que CLIPS la produzca. Las fichas actuales siguen pendientes de revisión del investigador.
2. **Cerrar el registro de coincidencias.** Conservar el informe y las huellas del conjunto usado. Marcar casos conocidos y casos sin coincidencias bajo los criterios comprobados.
3. **Preparar el instrumento común.** Asociar `case_id`, `intent_id`, versión, arquitectura, repetición y configuración con salida cruda, objetivos, hechos, plan, tiempo e incidencias. No enviar las referencias al modelo.
4. **Comprobar el evaluador.** Probar tanto planes correctos como versiones con errores deliberados. Verificar que acepte alternativas válidas y detecte omisiones.
5. **Ejecutar diez casos iniciales.** DEV-001, 004, 007, 010, 013, 016, 031, 037, 040 y 043. Usar Qwen–CLIPS, GPT y el control correspondiente. Revisar registros antes de ampliar. Son parte del conjunto de 60.
6. **Completar el piloto de 60.** Ajustar límites de salida, tiempos de espera, registros y rúbricas usando exclusivamente desarrollo. Los diagnósticos de capacidades no verificables no se convierten en éxitos.
7. **Fijar configuraciones y prueba final.** Congelar modelos, adaptador, prompt, reglas, normalizador, datos, evaluador, parámetros y política de reintentos. Preparar nuevas instancias de intención sin reutilizar las de desarrollo.
8. **Ejecutar la comparación final.** Mismas órdenes originales para ambas arquitecturas, sin historial y con estado reiniciado. Alternar el orden de condiciones por bloques; procesar una solicitud a la vez. Mantener los fallos y todas las repeticiones.
9. **Analizar por intención y presentar resultados.** Informar aciertos, fallos, incertidumbre, errores y costes. Conservar juntas las variantes de una intención. El capítulo 6 explicará el procedimiento; el 7 contendrá sus resultados.

## Auditoría v02 verificada

Se recibió `reports/evaluation/auditoria_desarrollo_v02.json` y se comprobó que sus huellas corresponden a las entradas actuales y al corpus registrado de 40 000 filas. El informe contiene cero coincidencias literales, cuatro por limpieza básica y ocho mediante el normalizador real de Qwen. Son ocho órdenes distintas en total.

Las coincidencias son DEV-010 y DEV-012 (entrega al operador), DEV-025 y DEV-027 (seguimiento), DEV-031 y DEV-033 (conteo), y DEV-040 y DEV-042 (respuesta a pregunta). Las paráfrasis DEV-011, DEV-026, DEV-032 y DEV-041 no coinciden directamente, pero comparten intención con ellas. Los cuatro grupos se conservan como diagnósticos conocidos de desarrollo.

Las 60 entradas y sus objetivos permanecen iguales. Se actualizaron las fichas con estado de coincidencia por orden y por grupo, filas del corpus y evidencia de ambas auditorías. Hay 52 órdenes sin coincidencia directa; cuatro son las paráfrasis indicadas. No debe presentarse ese número como 52 intenciones nuevas ni como prueba de independencia semántica.

No se necesita otra auditoría por esta actualización de metadatos. Sí deberá repetirse si se cambian las entradas, el dataset o el normalizador. La comparación con todo el corpus no permite asignar las coincidencias a entrenamiento o validación ni demostrar memorización.

La revisión semántica de las referencias sigue pendiente. Todo el conjunto de desarrollo se mantendrá separado de la prueba final. En tareas simples con pocas combinaciones disponibles, las coincidencias pueden conservarse como controles conocidos; no se ocultarán cambiando únicamente palabras superfluas o puntuación.

## Tamaño y repeticiones: propuesta aún abierta

El piloto tiene 60 órdenes y 28 intenciones. Se propone una primera pasada por cada arquitectura, seguida de repeticiones para estimar variación y coste. Los ensayos corregidos del piloto no serán prueba final.

Para la campaña final se propone cobertura de diez intenciones por familia admisible, con tres formulaciones y tres repeticiones por arquitectura. Si entraran las 29 familias, serían 870 órdenes y 2 610 ejecuciones por arquitectura, 5 220 en total, más el control y el bloque de límites. Estas cifras son **un escenario de dimensionamiento**, no una cantidad aprobada o ejecutada ni una justificación estadística del tamaño.

Antes de comprometer ese volumen, el piloto debe decirnos cuánto tarda, cuánto cuesta y cuántas referencias pueden verificarse con rigor. Si se reduce el tamaño, se fijará la nueva distribución antes de observar las respuestas del conjunto final.

El control puede reutilizar resultados cuando objetivos y condiciones sean exactamente los mismos, siempre que se documente esa reutilización y no se cuente como repetición independiente. Para una primera implementación sencilla puede ejecutarse una vez por ficha aplicable.

## Qué falta implementar o confirmar

- **Registro común y correlación:** `qwen_to_plan.py` imprime resultados, pero sus salidas no constituyen todavía un registro experimental completo. Debe evitarse asociar un plan tardío con la siguiente orden. El JSONL de GPT ofrece parte de la evidencia, pero necesita vincularse con los identificadores del experimento.
- **Evaluación del contenido:** los validadores actuales de sintaxis y contrato son útiles, pero no comprueban todas las subtareas, precondiciones y referencias de una orden.
- **Control real:** ejecutar la referencia a través del adaptador usado en ROS y las mismas reglas, con registro de hechos. No sustituirlo por otro conversor sin demostrar equivalencia.
- **Contrato de acciones:** precisar seguimiento, verificación de nombres, atributos conjuntos y conservación de información. Distinguir efectos definidos, errores identificables y propiedades que no pueden verificarse.
- **Configuración final:** límites de tokens, tiempos de espera de cada capa, modalidad local o remota de Qwen, repeticiones y reintentos. Un tiempo externo mayor no resuelve un tiempo interno menor sin ajustar ambas capas.
- **Referencias y tamaño:** revisión humana, composición final por familia y criterio de inclusión anterior a las respuestas finales.

No hace falta otro entrenamiento para avanzar en estos puntos. Si el piloto motivara cambiar el modelo o entrenar nuevamente, esa decisión debe producirse antes de fijar la configuración final y quedar documentada.

## Archivos del borrador y cómo integrarlos

- `Ch06_Validation.tex`: capítulo redactado en LaTeX como protocolo propuesto, con secciones 6.1 a 6.7.
- `Ch06_Validation_lectura.md`: copia del mismo capítulo para lectura, no una segunda versión con contenido distinto.
- `referencias_capitulo6.bib`: dos antecedentes metodológicos consultados. Añadir sus entradas al archivo bibliográfico principal y evitar duplicarlas si ya existen con otras claves.
- Este archivo: explicación operativa y pendientes, separada del texto académico.

El `.tex` se integra con `\include` o `\input` desde el documento principal. Usa `amsmath`, `amssymb` y `booktabs`. No contiene un preámbulo ni activa por sí mismo la bibliografía.

Se propone sustituir la antigua sección 6.6 «Evaluación física con Justina» por «Robustez, límites del dominio y alcance físico». Si no se realizan pruebas físicas, también deberá ajustarse el apartado correspondiente del capítulo 7. La cifra de ocho coincidencias se conserva en esta guía de trabajo; no se presenta en el capítulo como una auditoría final ya cerrada.

El borrador no está listo para convertirse íntegramente a tiempo pasado: faltan el piloto y la campaña final. Al completarlos, deberán incorporarse los tamaños, configuraciones y procedimientos realmente utilizados, sin transformar decisiones propuestas en hechos retrospectivos.
