# Programas experimentales: GPT directo y Qwen–CLIPS

Estos programas reciben instrucciones, obtienen objetivos y planes y guardan
la evidencia necesaria para evaluarlos. Terminan en el plan: no publican tópicos
ROS ni ejecutan acciones físicas. Ambos usan el mismo formato de resultados.

- `python3 -m experiments.run_gpt`: GPT produce objetivos y plan en una solicitud.
- `python3 -m experiments.run_qwen_clips`: consulta el servidor Qwen y planifica
  localmente con CLIPS; también ejecuta el control de objetivos de referencia.
- `python3 -m experiments`: coordina las condiciones de una campaña combinada.

El diseño implementa los [requisitos experimentales](../Requisitos_programa_experimental.md).
Los ejemplos de comandos usan rutas desde la raíz del repositorio. El modelo GPT
se elige explícitamente; no hay un modelo predeterminado.

## Preparación

```bash
python3 -m pip install -r experiments/requirements.txt
```

Se requiere Python 3.10 o superior en Linux. El cliente experimental usa `httpx`,
`openai`, `jsonschema` y `clipspy`; no carga PyTorch ni el modelo Qwen localmente.
El servidor Qwen mantiene sus propias dependencias y el modelo cargado.

Para Qwen, iniciar el servidor del repositorio y configurar en la terminal del
cliente:

```bash
export QWEN_SERVER_URL='http://127.0.0.1:8008'
# Configurar QWEN_API_KEY con la misma clave del servidor, si utiliza autenticación.
```

El servidor expone `/metadata`, protegido con la misma clave que `/translate`.
Contiene el modelo base y su revisión observada, parámetros de generación,
inventario SHA-256 del adaptador y tokenizer, normalizador, catálogos y fuentes,
así como versiones de paquetes. El cálculo del inventario se hace al cargar el
servidor. Cada respuesta de `/translate` identifica esa configuración mediante
`effective_config_sha256`.

La creación de una campaña Qwen consulta `/metadata`; la ejecución verifica de
nuevo la configuración y el identificador de cada respuesta. Una discrepancia
se registra como error. Los parámetros del manifiesto no reconfiguran el servidor.
Si el servidor estaba en ejecución durante una modificación de su código, debe
reiniciarse para cargar esa implementación.

Para GPT, configurar `OPENAI_API_KEY` en el entorno. Su valor no se escribe en el
manifiesto ni en los registros. No se leen archivos `.env` automáticamente.
La integración usa [Responses API con Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs):
`text.format` fija el esquema, pero la corrección semántica se evalúa por separado.

## Probar una instrucción

Crear la campaña y ejecutarla son operaciones separadas: `init` fija entradas y
configuración; `run` inicia las consultas.

GPT:

```bash
python3 -m experiments.run_gpt init \
  --campaign reports/experiments/gpt_orden_01 \
  --command 'Go to the kitchen.' --case-id CASE-001 \
  --model "$OPENAI_MODEL"

python3 -m experiments.run_gpt run \
  --campaign reports/experiments/gpt_orden_01
```

`OPENAI_MODEL` debe contener el modelo o snapshot elegido por el investigador.
El argumento `--model` es obligatorio para crear configuraciones GPT.

Qwen–CLIPS:

```bash
python3 -m experiments.run_qwen_clips init \
  --campaign reports/experiments/qwen_orden_01 \
  --command 'Go to the kitchen.' --case-id CASE-001

python3 -m experiments.run_qwen_clips run \
  --campaign reports/experiments/qwen_orden_01
```

## Procesar el conjunto de desarrollo

Cada entrada contiene `id`, `input` y, opcionalmente, `intent_id`. Se preserva el
texto original, incluidos sus espacios. Solo `input` llega al modelo como orden.
Cuando falta `intent_id`, se registra `null`, o se obtiene del índice de las
referencias aportadas al preparar la campaña. No se inventa un grupo de intención.

```bash
python3 -m experiments.run_gpt init \
  --campaign reports/experiments/gpt_desarrollo_01 \
  --inputs data/development/desarrollo_60_entradas.jsonl \
  --references data/development/desarrollo_60_referencias.jsonl \
  --model "$OPENAI_MODEL" --repetitions 3 --order-seed 42

python3 -m experiments.run_gpt run \
  --campaign reports/experiments/gpt_desarrollo_01
```

Para Qwen se utiliza `experiments.run_qwen_clips` con los mismos argumentos de
entradas y referencias, sin `--model`. Aportar referencias no las envía al modelo
ni activa por sí solo el control CLIPS.

`--prompt`, `--response-schema` y `--gpt-parameters` permiten fijar los artefactos
y parámetros GPT al crear la campaña. Por ejemplo:

```bash
--gpt-parameters '{"max_output_tokens":8192,"reasoning":{"effort":"low"}}'
```

La compatibilidad de los parámetros depende del modelo elegido. Se envían
solamente los parámetros registrados: `store=false`, el límite de tokens y los
opcionales especificados. No se atribuyen valores a temperatura u otros parámetros
omitidos. El SDK usa `max_retries=0` y cada solicitud tiene un historial vacío.

## Piloto con diez órdenes distintas

`--max-runs` limita intentos nuevos, no órdenes distintas. Con tres repeticiones,
diez intentos pueden corresponder a varias repeticiones de las mismas órdenes.
Para el piloto, crear una campaña con **una repetición** y seleccionar diez IDs:

```bash
python3 -m experiments init \
  --campaign reports/experiments/piloto_10 \
  --conditions qwen_clips gpt_direct reference_clips \
  --inputs data/development/desarrollo_60_entradas.jsonl \
  --references data/development/desarrollo_60_referencias.jsonl \
  --model "$OPENAI_MODEL" --repetitions 1

casos=(--case-id DEV-001 --case-id DEV-004 --case-id DEV-007 --case-id DEV-010
       --case-id DEV-013 --case-id DEV-016 --case-id DEV-031 --case-id DEV-037
       --case-id DEV-040 --case-id DEV-043)
python3 -m experiments run --campaign reports/experiments/piloto_10 \
  --architectures qwen_clips gpt_direct "${casos[@]}"
```

Después de revisar realmente las referencias **antes de crear la campaña**,
ejecutar el control seleccionando explícitamente solo los IDs de esos diez con
referencia `approved` y `goals_ref` aplicables. Por ejemplo, **solo si DEV-001 y
DEV-004 cumplen esas condiciones en el archivo congelado**:

```bash
python3 -m experiments run --campaign reports/experiments/piloto_10 \
  --architectures reference_clips --case-id DEV-001 --case-id DEV-004
```

Si las diez referencias están aprobadas y son aplicables, usar `"${casos[@]}"`
también para el control: diez órdenes en tres condiciones producen hasta treinta
registros sin reintentos. No editar las referencias congeladas de una campaña;
si cambia su revisión, crear una nueva campaña.

## Campaña combinada y control simbólico

```bash
python3 -m experiments init \
  --campaign reports/experiments/comparacion_01 \
  --conditions qwen_clips gpt_direct reference_clips \
  --inputs data/development/desarrollo_60_entradas.jsonl \
  --references data/development/desarrollo_60_referencias.jsonl \
  --model "$OPENAI_MODEL" --repetitions 3 --order-seed 42

python3 -m experiments run --campaign reports/experiments/comparacion_01
```

Las condiciones se alternan en bloques de caso/repetición con una semilla fija.
Se procesa una solicitud cada vez. Para ejecutar una selección:

```bash
python3 -m experiments run --campaign reports/experiments/comparacion_01 \
  --architectures qwen_clips reference_clips --case-id DEV-001 --case-id DEV-004
```

El control solo acepta referencias con `reference_status: "approved"` y que no
estén marcadas como ejemplos. La aprobación debe proceder de la revisión del
investigador. Las referencias pendientes producen `ReferenceNotApproved`; no se
marcan aprobadas automáticamente. Si `goals_ref` es `null`, se registra
`ReferenceNotApplicable`, sin inferencia ni plan. Puede seleccionarse el subconjunto
resoluble mediante `--case-id`. Ambos se cuentan como `control_not_submitted`,
con motivos separados, y quedan fuera de los fallos de planificación y sus
métricas. En la evaluación tienen cumplimiento `not_applicable` porque ese
control no llegó a ejecutarse, aunque una revisión posterior apruebe la referencia.
El error original permanece en la evidencia; no se modifica ninguna aprobación.

El control usa el mismo adaptador, archivo de reglas y estado inicial que Qwen.
Su campo `goals_pred` queda en `null`; los objetivos aportados se guardan en
`reference_clips.goals_reference_input`. Para un control aislado se puede crear
una campaña con `--conditions reference_clips --references ...`, sin servidor
Qwen ni credenciales GPT.

## Registros, estados y reanudación

Cada carpeta de campaña contiene:

| Archivo | Contenido |
|---|---|
| `manifest.json` y `manifest.sha256` | Configuración y huella del manifiesto final |
| `assets/` | Copias fijadas de entradas, referencias, prompt, esquema, reglas y metadatos aplicables |
| `resultados.jsonl` | Una fila por intento terminado, con `run_id` único |
| `journal.jsonl` | Inicio, evidencia parcial, fin e interrupciones detectadas |
| `startup.jsonl` | Carga inicial del motor/proveedor, separada de cada respuesta |
| `evaluaciones.jsonl` | Evaluaciones posteriores versionadas, vinculadas por `run_id` |

`init` exige una carpeta nueva. `run` reanuda la campaña y omite los intentos con
resultado, incluidos errores. `--retry-failed` solicita explícitamente otro intento
de las ejecuciones con error/timeout: conserva el resultado anterior, incrementa
`attempt` y asigna otro `run_id`. No repite respuestas `completed` con formato
incorrecto. Las repeticiones ordinarias se fijan mediante `--repetitions`.

Una interrupción sin resultado queda como `interrupted_unknown` en el diario al
reanudar; no se inventa un resultado o un timeout. El nuevo intento usa otro ID y
número. El bloqueo de campaña impide escritores concurrentes. Si se detecta una
última fila incompleta por pérdida de alimentación, se detiene la lectura/escritura
para que se recupere conservando la evidencia; no se trunca automáticamente.

Las huellas de artefactos, código y versiones Python se comprueban antes de
reanudar. Un cambio requiere otra campaña. El identificador Git se acompaña de
un inventario de fuentes para identificar también código sin commit.

Estados independientes:

- `execution_status`: `completed`, `error` o `timeout`.
- `response_kind`: `plan`, `clarification`, `rejected` o `null`.
- `validation`: comprobaciones de esquema, objetivos y contrato del plan.

Un JSON GPT recibido completo pero inválido se registra como `completed` con
validación fallida. Un rechazo de la API o una respuesta truncada se registra como
incidencia del proveedor; no como rechazo correcto del dominio. Qwen sin objetivos
analizables produce `error` porque no puede continuar a CLIPS. Se conserva el
cuerpo HTTP completo disponible, identificado como `http_body`; no se reconstruye
el texto interno del modelo. `null`, `[]` y `false` mantienen significados distintos.

Los planes conservan sus números, duplicados, acciones y parámetros. CLIPS se
serializa por `step`; GPT conserva el orden recibido. Los valores de tipo inválido
permanecen en la salida original y no se convierten en valores supuestamente válidos.
Las transformaciones del adaptador quedan registradas junto con los goals originales.

## Límites de tiempo y aislamiento

Al crear la campaña se fijan `--request-timeout`, `--planning-timeout` y
`--total-timeout`, en segundos. Los valores predeterminados son 60, 10 y 75,
respectivamente; deben ajustarse durante el piloto y fijarse para el experimento.

Los trabajadores son procesos separados. El supervisor puede terminarlos aunque
CLIPS no retorne o una solicitud quede bloqueada. Las reglas se cargan una vez por
trabajador y el estado se reinicia en cada orden. La carga inicial tiene un límite
de 30 segundos y se informa aparte. La primera versión admite el estado
`location=unknown`, `holding=nothing`, `focus=false`, `manipulation_enabled=true`,
que coincide con las reglas fijadas; rechaza otros estados.

El límite total termina la espera local. No garantiza cancelar la inferencia en
el servidor Qwen ni en el proveedor GPT. La conexión del intento queda aislada;
una respuesta tardía no se asigna a la orden siguiente. En Qwen, un trabajo remoto
pendiente puede afectar la latencia de una solicitud posterior, dado el lock del
servidor. Por eso, tras un timeout de Qwen (o la pérdida de su trabajador),
se consulta el endpoint autenticado `/status?run_id=...`. Solo continúa si confirma
que esa solicitud terminó, que no hay solicitudes activas ni en espera y que la
configuración coincide. Si está ocupado, no responde o no reconoce la solicitud,
se detiene toda la campaña conservando el fallo. Al reanudar `run` se repite la
comprobación antes de ejecutar otro ensayo, incluso de otra arquitectura. El diario
registra la verificación separada; ese tiempo no cambia la latencia del intento.
También se comprueban solicitudes Qwen interrumpidas sin resultado final.

El servidor conserva los últimos 10 000 identificadores terminados en memoria;
un reinicio pierde esa evidencia. En ese caso no se reanuda automáticamente la
campaña afectada: verificar el servidor y crear otra campaña, conservando y
reportando la anterior. Instalar este servidor y reiniciarlo antes de crear las
nuevas campañas; `/health` y `/metadata` no prueban que esté libre. Durante las
mediciones se debe reservar el servidor para la campaña, sin otros clientes.
No debe interpretarse el tiempo HTTP como tiempo puro de inferencia.

`total_ms` cubre el recorrido observado por el cliente hasta la validación o el
fallo, excluyendo la carga inicial y la escritura final. Los tiempos internos del
servidor se guardan aparte. Las etapas ausentes quedan en `null`. En un fallo de
inicialización no se mide un recorrido de consulta y `total_ms` queda en `null`.
El diario añade sobrecarga de instrumentación. No se mide ejecución física, ni
memoria/energía de los modelos, ni tiempo de carga del modelo remoto.

## Evaluación posterior

```bash
python3 -m experiments evaluate \
  --campaign reports/experiments/comparacion_01 \
  --references data/development/desarrollo_60_referencias.jsonl \
  --evaluator-version formato-1

python3 -m experiments summary --campaign reports/experiments/comparacion_01
```

El evaluador calcula coincidencia literal de goals para referencias aprobadas y
valida el contrato de los planes. No equipara coincidencia literal con equivalencia
semántica, ni terminación CLIPS con cumplimiento. Las rúbricas de las fichas siguen
requiriendo revisión; `semantic_correct` queda en `null` y la evaluación permanece
`pending` hasta incorporar un dictamen. El control no recibe puntuación lingüística.

Para incorporar revisión humana se proporciona un JSONL mediante `--reviews`.
Cada fila debe contener `run_id`, `reference_version` (SHA-256 del archivo completo
de referencias), `reviewer`, `reviewed_at_utc` y `task_fulfillment`. Puede añadir
`semantic_correct`, `domain_response_correct`, `failed_checks`, `error_categories`
y `review_notes`. Los valores de cumplimiento son `pass`, `fail`, `not_verifiable`
y `not_applicable`. Este último indica referencias sin tarea ejecutable o controles no sometidos.

```bash
python3 -m experiments evaluate --campaign reports/experiments/comparacion_01 \
  --reviews revisiones.jsonl --evaluator-version revision-1
```

Cambiar un dictamen exige otra versión del evaluador; los resultados originales
no se editan. Un fallo técnico de una orden resoluble registra cumplimiento no
obtenido sin deducir automáticamente una causa semántica. Las aclaraciones y
rechazos esperados se evalúan mediante `domain_response_correct`.

El resultado principal (`primary_first_attempt_per_repetition`) utiliza el primer
intento de cada caso/configuración/repetición, incluidos errores, timeouts e
interrupciones sin resultado. La recuperación (`recovery_latest_attempt_per_repetition`)
muestra aparte el último intento disponible, como análisis adicional. `architectures`
conserva los conteos de todos los intentos. Cada vista distingue controles no
sometidos, fallos de ejecución y dictámenes; las tasas incluyen sus numeradores,
denominadores y pendientes explícitos. Un reintento exitoso no reemplaza el fallo
inicial en el resultado principal.
Si hay varias versiones de evaluación, elegir `summary --evaluator-version ...`.
Estos conteos no tratan las repeticiones o paráfrasis como intenciones independientes.

## Equivalencia con Justina y pruebas

`vendor/goal_adapter.py` conserva las clases `ParsedGoal`, `GoalParser` y
`ClipsGoalFactBuilder`; solo se separaron del transporte ROS. Las reglas están en
`vendor/goals_planning.clp`. `vendor/provenance.json` identifica las fuentes y sus
huellas. No se modifica el workspace de Justina.

```bash
python3 -m experiments verify-justina --workspace /home/sergio/Justina
python3 -m unittest discover -s tests -v
```

La verificación compara las clases mediante AST, las reglas mediante SHA-256 y
los hechos y planes de las mismas secuencias, usando el `PlanExtractor` de las
fuentes de Justina. No inicia ROS ni certifica comunicación con el robot.

Las pruebas automatizadas utilizan CLIPS real, un servidor HTTP simulado en
`127.0.0.1` y respuestas GPT simuladas, incluido el SDK. Comprueban errores,
aclaraciones, truncamiento, timeout, reinicio de estado, reanudación, rechazo de
cambios de configuración y conservación de evidencia. No son resultados de los
modelos ni sustituyen las ejecuciones reales del piloto.

## Qwen2.5-3B, Qwen2.5-7B y GPT directo

Las tres condiciones principales son `qwen3b_clips`, `qwen7b_clips` y
`gpt_direct`. Las dos primeras comparten la arquitectura Qwen–CLIPS, con modelos
y adaptadores distintos. `reference_clips` es un control auxiliar y no representa
otro modelo. El servidor obtiene el nombre del modelo base de
`adapter_config.json`; `--adapter-path` selecciona el adaptador entrenado.

En una misma GPU, ejecutar los modelos por bloques para no mantener ambos pesos
residentes durante la medición. Preparar metadatos de ambos servidores antes de
crear la campaña. Por ejemplo, iniciar el 3B:

```bash
python3 server.py --adapter-path models/nl2cd_qwen3b --port 8008
```

Desde otra terminal, guardar sus metadatos:

```bash
export QWEN_SERVER_URL=http://127.0.0.1:8008
curl --fail -H "Authorization: Bearer $QWEN_API_KEY" \
  "$QWEN_SERVER_URL/metadata" > /tmp/qwen3b_metadata.json
```

Detener ese servidor cuando esté libre, iniciar el 7B con
`--adapter-path models/nl2cd_qwen7b`, y guardar `/metadata` como
`/tmp/qwen7b_metadata.json`. Crear `variantes.json`:

```json
[
  {"label":"qwen3b_clips","url_env":"QWEN_SERVER_URL","api_key_env":"QWEN_API_KEY","metadata_file":"/tmp/qwen3b_metadata.json"},
  {"label":"qwen7b_clips","url_env":"QWEN_SERVER_URL","api_key_env":"QWEN_API_KEY","metadata_file":"/tmp/qwen7b_metadata.json"}
]
```

```bash
python3 -m experiments init --campaign reports/experiments/tres_modelos \
  --conditions qwen_clips gpt_direct --qwen-variants variantes.json \
  --model "$OPENAI_MODEL" --repetitions 1 \
  --inputs data/development/desarrollo_60_entradas.jsonl \
  --references data/development/desarrollo_60_referencias.jsonl

# Con el servidor 7B activo:
python3 -m experiments run --campaign reports/experiments/tres_modelos \
  --condition qwen7b_clips

# Después de cambiar al servidor 3B, estando libre el anterior:
python3 -m experiments run --campaign reports/experiments/tres_modelos \
  --condition qwen3b_clips

python3 -m experiments run --campaign reports/experiments/tres_modelos \
  --condition gpt_direct
```

Añadir los mismos diez `--case-id` del piloto a **cada** ejecución para limitarlo
a diez órdenes. Sin esa selección se ejecutan todas las entradas. Cada variante
conserva su propio `config_id`, metadatos y huellas; el resumen las presenta por
etiqueta sin sumar 3B y 7B. `conditions` identifica modelo y arquitectura;
`architectures` conserva su nombre de campo pero sus claves son las etiquetas de
las condiciones. `--architectures qwen_clips` selecciona ambas variantes;
`--condition` permite elegir una.

Con servidores independientes también pueden usarse variables de URL distintas
y omitir `metadata_file` para capturar los metadatos en `init`. No cargar ambos
modelos en la GPU que se esté midiendo. Registrar el orden real de los bloques y
alternarlo entre campañas: ejecutar por bloques no equivale a intercalar modelos.
Mantener comparables hardware, cuantización, límites, entradas y repeticiones.
La comprobación pendiente tras un timeout debe resolverse **antes** de detener o
cambiar el servidor; un reinicio pierde su historial de solicitudes.

## Recursos computacionales por intento

Los tiempos y tokens ya registrados se complementan con `resources`:

| Campo | Alcance |
| --- | --- |
| `client` | Proceso trabajador: llamada HTTP, adaptación, CLIPS y validación; excluye carga inicial y supervisor. |
| `model_internal` en Qwen | Proceso del servidor durante la inferencia; excluye espera en cola y carga de pesos. Incluye memoria residente del modelo. |
| `model_internal` en GPT | **«no disponibles»**: CPU, RAM y GPU internos no son observables desde la API. |
| `model_internal` en el control | No aplicable: no hay inferencia de modelo. CLIPS se mide en `client`. |

Se guardan segundos de CPU del proceso, tiempo observado, RSS inicial y máximo
muestreado en bytes. La RAM se obtiene de `/proc/self/statm` en Linux; si falta,
se registra `null`. En el servidor se muestrea cada 50 ms la memoria asignada y
reservada por el asignador de PyTorch, por GPU visible, con valores iniciales y
máximos observados. Estos máximos pueden omitir picos entre muestras. La memoria
GPU medida **no abarca asignaciones ajenas a PyTorch**, ni expresa utilización,
energía o potencia. No se suman CPU del cliente y servidor ni se atribuyen al
modelo remoto. El muestreo añade una pequeña carga incluida en las mediciones.

GPT conserva por separado los tokens reportados por el proveedor; no se usan para
estimar CPU, RAM o GPU. Sus recursos internos siempre llevan `status: unavailable`,
`display: "no disponibles"` y valores `null`, nunca cero. El contrato JSON rechaza
valores numéricos en esos campos. Los recursos locales del cliente sí pueden
medirse, pero no sustituyen los internos del proveedor.

Los resúmenes principal y de recuperación incluyen CPU y RAM por condición y
alcance, con media, máximo, cantidad medida y cantidad no disponible. Las métricas
GPU por dispositivo quedan en los registros individuales. Las mediciones ausentes
no entran como ceros en las medias. Si el trabajador se termina por un límite duro,
no se inventa una medición final; si no llega una respuesta Qwen, sus recursos
internos permanecen no disponibles. Conservar esos fallos al interpretar las
medias, que describen únicamente los intentos con mediciones disponibles.

Estos cambios requieren servidores actualizados y campañas nuevas, porque el
manifiesto fija las huellas del código y los contratos. No se modifican campañas
ni resultados ya guardados.
