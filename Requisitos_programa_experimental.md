# Requisitos del programa experimental: Qwen–CLIPS y GPT directo

Versión propuesta 1.0 · 24 de septiembre de 2026

Este documento especifica entradas, configuración y registros para comparar Qwen–CLIPS con GPT directo, junto con el control de objetivos de referencia → adaptador → CLIPS. El programa termina en la obtención del plan; no ejecuta acciones físicas.

**Todos los ejemplos de salidas, tiempos, identificadores de respuesta y consumos son ficticios.** Ilustran el formato y no constituyen resultados experimentales ni referencias para calificar modelos. Los IDs `EX-*` tampoco pertenecen al conjunto de 60 casos. Las salidas llevan `example_only: true`; los resultados reales deben usar `false`.

## 1. Organización de los datos

El programa trabajará con cuatro archivos lógicos:

| Archivo propuesto | Función |
|---|---|
| `entradas.jsonl` | Órdenes e identificadores para las dos arquitecturas |
| `manifest.json` | Configuración y versiones de la campaña |
| `resultados.jsonl` | Una fila por intento, incluidos errores y tiempos agotados |
| `evaluaciones.jsonl` | Calificación posterior, vinculada a cada intento por `run_id` |

Las fichas de referencia estarán en un archivo separado, por ejemplo `referencias.jsonl`. El ejecutor de Qwen o GPT no necesita leerlo para generar respuestas. El evaluador lo utilizará después; la condición `reference_clips` sí lo leerá para recibir explícitamente los objetivos de referencia.

Los JSON de este documento están indentados para facilitar la lectura. Al escribir JSONL, cada objeto debe ocupar una sola línea y el archivo será UTF-8. No sobrescribir resultados anteriores al reanudar una campaña.

## 2. Entradas

Cada orden debe contener `id` e `input`. Se recomienda añadir `intent_id`; si las entradas existentes solo contienen los dos primeros campos, el programa puede recuperar el grupo desde un índice de metadatos sin enviar esa información al modelo.

| Campo | Tipo | Regla |
|---|---|---|
| `id` | cadena | Único dentro de la versión del conjunto |
| `intent_id` | cadena | Compartido por las variantes de una misma intención |
| `input` | cadena | Orden original no vacía; conservarla sin sobrescribir |

Ejemplo de archivo completo de entradas:

```jsonl
{"id": "EX-001", "intent_id": "EX-INT-01", "input": "Go to the kitchen."}
{"id": "EX-002", "intent_id": "EX-INT-02", "input": "Go to the kitchen and bring it to me."}
{"id": "EX-003", "intent_id": "EX-INT-03", "input": "Fly to the ceiling and inspect the lamp."}
```

En Qwen se enviará `input` a la ruta habitual de inferencia y normalización. En GPT se utilizará como mensaje de usuario, junto con el prompt y esquema fijos. No adjuntar la ficha, los objetivos esperados, el criterio de éxito ni respuestas de otros ensayos.

### 2.1. Referencia separada para el evaluador y el control

El siguiente formato es un ejemplo mínimo compatible en propósito con las fichas de desarrollo existentes; no exige convertirlas ni reemplazarlas:

```json
{
  "id": "EX-001",
  "intent_id": "EX-INT-01",
  "input": "Go to the kitchen.",
  "reference_version": "ejemplo-1",
  "reference_status": "approved",
  "example_only": true,
  "reviewed_by": "REVISOR_EJEMPLO",
  "expected_status": "executable",
  "goals_ref": [
    "go(kitchen)"
  ],
  "required_subtasks": [
    "Visitar kitchen."
  ],
  "constraints": [
    "El retorno convencional al operador no sustituye la visita solicitada."
  ],
  "acceptable_variations": [
    "Variar anuncios sin modificar la tarea."
  ],
  "verification_limits": [
    "No se verifica llegada física."
  ]
}
```

La marca `approved` y el revisor de la ficha anterior son ficticios, como el resto del ejemplo. En los datos reales, las referencias deben revisarse antes de la evaluación final. Para órdenes ambiguas o fuera del repertorio, `goals_ref` será `null` y la ficha describirá la aclaración o razón de rechazo esperada. La ausencia de una referencia aplicable no equivale a una lista vacía acertada.

Los metadatos de auditoría se conservan en las fichas. Los ocho casos coincidentes de desarrollo siguen identificados; no deben enviarse esas etiquetas a los modelos ni presentarse el desarrollo como prueba final.

## 3. Configuración de la campaña

El manifiesto identifica la campaña y las configuraciones de sus condiciones. Un `config_id` debe identificar valores inmutables: cualquier cambio de modelo, prompt, reglas o parámetros requiere una nueva versión o identificador.

Los siguientes tiempos y límites son ejemplos de configuración, no valores finales aprobados. Las huellas en `null` deben completarse en una campaña real; la huella del manifiesto se calcula externamente sobre el archivo final para evitar una autorreferencia.

```json
{
  "schema_version": "1.0",
  "example_only": true,
  "campaign_id": "EX-CAMPAIGN-01",
  "split": "development",
  "inputs": {
    "path": "entradas.jsonl",
    "sha256": null
  },
  "references": {
    "path": "referencias.jsonl",
    "sha256": null,
    "version": "ejemplo-1"
  },
  "schedule": {
    "repetitions": 3,
    "order_seed": 42,
    "concurrency": 1,
    "automatic_retries": 0
  },
  "initial_state": {
    "location": "unknown",
    "holding": "nothing",
    "focus": false,
    "manipulation_enabled": true
  },
  "configs": [
    {
      "config_id": "EX-CFG-QWEN-01",
      "architecture": "qwen_clips",
      "qwen": {
        "mode": "http",
        "url_env": "QWEN_SERVER_URL",
        "api_key_env": "QWEN_API_KEY",
        "base_model": "Qwen/Qwen2.5-7B",
        "adapter_path": "nl2cd_qwen7b",
        "adapter_sha256": null,
        "generation": {
          "do_sample": false,
          "max_new_tokens": 128
        }
      },
      "normalizer_sha256": null,
      "catalogs_sha256": null,
      "goal_adapter_sha256": null,
      "clips_rules": [
        {
          "path": "goals_planning.clp",
          "sha256": null
        }
      ],
      "timeouts_seconds": {
        "model_request": 60,
        "planning": 10,
        "total": 75
      }
    },
    {
      "config_id": "EX-CFG-GPT-01",
      "architecture": "gpt_direct",
      "model": "gpt-5.6-terra",
      "api_key_env": "OPENAI_API_KEY",
      "prompt": {
        "path": "system_prompt.md",
        "sha256": null
      },
      "response_schema": {
        "path": "response_schema.json",
        "sha256": null
      },
      "generation": {
        "max_output_tokens": 8192,
        "store": false
      },
      "timeouts_seconds": {
        "model_request": 60,
        "total": 75
      }
    },
    {
      "config_id": "EX-CFG-CONTROL-01",
      "architecture": "reference_clips",
      "symbolic_config_source": "EX-CFG-QWEN-01",
      "timeouts_seconds": {
        "planning": 10,
        "total": 15
      }
    }
  ],
  "software": {
    "python": null,
    "packages_file": "versiones_python.txt",
    "packages_sha256": null,
    "code_revision": null
  },
  "output_path": "resultados.jsonl"
}
```

Para un adaptador compuesto por varios archivos, utilizar un inventario de rutas y SHA-256 o una huella de ese inventario, con el método documentado. Si Qwen se ejecuta en un servidor, comprobar su configuración efectiva; escribir parámetros en el manifiesto del cliente no modifica el servidor automáticamente. Registrar también la revisión del modelo base y las versiones efectivas del entorno.

Los tiempos de espera deben ser efectivos en las capas correspondientes. Un límite total requiere un mecanismo real de cancelación o aislamiento. Si no puede imponerse, declararlo como no implementado; no afirmar que se aplica solo porque aparece en el JSON. Registrar los parámetros omitidos de la solicitud como tales, sin atribuirles valores predeterminados no observados. Las credenciales se obtienen del entorno y sus valores no se guardan en los registros.

## 4. Registro común de resultados

Los campos siguientes deben existir en todas las filas; los valores desconocidos o no aplicables serán `null` donde se permita. No fabricar valores para completar el registro.

| Campo | Tipo | Significado |
|---|---|---|
| `schema_version` | cadena | Versión del formato del registro |
| `example_only` | booleano | `false` en ejecuciones reales |
| `campaign_id` | cadena | Campaña correspondiente |
| `run_id` | cadena | Identificador globalmente único del intento |
| `case_id`, `intent_id` | cadenas | Orden y grupo de intención |
| `architecture` | enumeración | `qwen_clips`, `gpt_direct`, `reference_clips` |
| `config_id` | cadena | Configuración fijada |
| `repetition` | entero ≥ 1 | Repetición planificada |
| `attempt` | entero ≥ 1 | Intento dentro de esa repetición |
| `started_at_utc`, `finished_at_utc` | cadenas | Fechas ISO 8601 en UTC |
| `input_original` | cadena | Texto original exacto |
| `execution_status` | enumeración | `completed`, `error`, `timeout` |
| `response_kind` | cadena o null | `plan`, `clarification`, `rejected` o `null` |
| `goals_pred` | lista de cadenas o null | Objetivos originales del modelo; null para control |
| `plan` | lista de objetos o null | Plan convertido al formato común, sin corregirlo |
| `message` | cadena o null | Aclaración, rechazo o mensaje del dominio |
| `raw_output` | cadena, objeto o null | Salida recibida antes de adaptar o corregir |
| `raw_output_kind` | cadena o null | Origen: `http_body`, `provider_output_text`, `local_model_text` |
| `timing` | objeto | Duraciones en milisegundos |
| `validation` | objeto | Comprobaciones de formato; no calificación semántica |
| `error` | objeto o null | Incidencia que impidió completar el recorrido |
| `qwen_clips` | objeto o null | Información propia de esa cadena |
| `gpt` | objeto o null | Información propia del servicio GPT |
| `reference_clips` | objeto o null | Información propia del control |

### 4.1. Estados: ejecución, respuesta y corrección

- `completed`: terminó el recorrido y se registró su respuesta. No garantiza formato ni significado correctos.
- `error`: una incidencia impidió completar el recorrido; conservar toda salida parcial disponible.
- `timeout`: se agotó un límite impuesto; registrar etapa y umbral.
- `response_kind: plan`: existe una propuesta de plan, aunque el evaluador la rechace.
- `response_kind: clarification` o `rejected`: conducta del dominio explícita en la respuesta. No usar estas etiquetas para errores de red, rechazo de la API o JSON inválido.
- `response_kind: null`: no pudo identificarse una respuesta del dominio.

Una respuesta terminada pero inválida puede conservar `execution_status: completed` y `validation.response_schema_valid: false` si el programa logró registrarla e inspeccionarla. Si no puede continuar —por ejemplo, Qwen no produjo objetivos analizables y no se puede ejecutar CLIPS— se registrará `error`, con la etapa concreta. Esta convención debe aplicarse de manera estable durante toda la campaña.

**`null`, `[]` y `false` no significan lo mismo.** `null` significa no disponible, no aplicable o no evaluado según el campo. `[]` conserva una lista realmente vacía, como las exigidas por el contrato GPT para una aclaración. `false` significa que una comprobación efectuada falló. No transformar una salida ausente en lista vacía ni un pendiente en fallo.

### 4.2. Representación del plan

Cada paso conservará `step`, `robot`, `action` y `params`. Se incluye `robot` porque forma parte del esquema GPT actual y de los hechos `ros-message`.

```json
{
  "step": 1001,
  "robot": "Justina",
  "action": "go_to",
  "params": [
    "kitchen"
  ]
}
```

No renumerar pasos, rellenar acciones omitidas ni reemplazar parámetros para que el plan pase la validación. Para los hechos CLIPS, la extracción puede ordenar por el campo explícito `step`, según la serialización prevista; debe conservar los números originales y los duplicados. La secuencia devuelta por GPT se conserva en el orden recibido. Una representación que no pueda analizarse debe permanecer accesible en la salida original.

### 4.3. Tiempos

`timing.total_ms` se mide con reloj monotónico desde el envío de la orden —o del objetivo en el control— hasta una respuesta terminal y su validación de formato, o hasta el error/timeout. No incluye la revisión semántica posterior ni la escritura final del registro. La carga inicial del modelo y de las reglas se informa por separado en la campaña.

| Campo en `timing` | Qué mide |
|---|---|
| `total_ms` | Recorrido completo observado por el cliente |
| `model_request_ms` | Llamada a Qwen o GPT, incluida comunicación y espera |
| `adaptation_ms` | Objetivos → representación adaptada y hechos |
| `planning_ms` | Preparación del estado e inferencia de CLIPS |
| `extraction_ms` | Análisis de respuesta o extracción del plan |
| `validation_ms` | Comprobación automática de formato |

Las etapas inexistentes quedan en `null`. El tiempo de solicitud HTTP no es tiempo puro de inferencia. El tiempo interno comunicado por Qwen se almacena aparte y no se suma de nuevo a `total_ms`. Las etapas pueden dejar un pequeño resto de sobrecarga; no alterar medidas para forzar una suma exacta. Los tiempos de solicitudes fallidas se conservan y se analizan separados de las respuestas exitosas.

### 4.4. Validación inmediata

`validation` contiene `response_schema_valid`, `goals_schema_valid`, `plan_contract_valid` (booleano o null) e `issues` (lista de descripciones). Estos campos no significan que se cumplió la orden. Para una aclaración válida, el esquema de respuesta puede ser válido y las comprobaciones de objetivos ejecutables y plan quedar en `null`.

### 4.5. Información específica

**Qwen–CLIPS:** guardar texto normalizado, objetivos posteriores al adaptador, hechos insertados, salida CLIPS, terminación, objetivos pendientes y diagnósticos. `goals_pred` permanece intacto. El registro del adaptador puede serializar sus objetos internos; no necesita reconstruir expresiones de objetivos si eso es ambiguo. Conservar transformaciones o reparaciones cuando ocurran. `remaining_goals: []` solo procede si se inspeccionó el entorno y efectivamente no quedaron objetivos; si no se inspeccionó, usar `null`.

**GPT:** guardar modelo solicitado y devuelto, ID y estado del servicio, estado del dominio y uso de tokens cuando estén disponibles. Conservar el objeto completo de respuesta del proveedor en la fila o en un archivo auxiliar vinculado mediante ruta y SHA-256. No sumar de nuevo tokens de razonamiento o caché a un total que ya los incluye.

**Control:** omitir la inferencia; usar la referencia revisada y el mismo adaptador, reglas y estado inicial. Guardar `goals_reference_input` en el bloque `reference_clips`; `goals_pred` será `null`. Este control no recibe puntuación de interpretación de lenguaje y su latencia no se compara como si incluyera un modelo.

Si la ruta HTTP de Qwen no expone el texto crudo generado, guardar el cuerpo HTTP disponible e identificarlo mediante `raw_output_kind: http_body`; no reconstruir un supuesto texto crudo. Lo mismo aplica a campos internos del servidor que no estén expuestos.

## 5. Ejemplo de salida de Qwen–CLIPS

Registro ficticio para `EX-001`. Se ilustra la navegación y el cierre convencional. Los indicadores de formato son ejemplos; la corrección semántica debe evaluarse por separado.

```json
{
  "schema_version": "1.0",
  "example_only": true,
  "campaign_id": "EX-CAMPAIGN-01",
  "run_id": "EX-001-QWEN-R01-A01",
  "case_id": "EX-001",
  "intent_id": "EX-INT-01",
  "architecture": "qwen_clips",
  "config_id": "EX-CFG-QWEN-01",
  "repetition": 1,
  "attempt": 1,
  "started_at_utc": "2026-09-24T12:00:00.000Z",
  "finished_at_utc": "2026-09-24T12:00:01.000Z",
  "input_original": "Go to the kitchen.",
  "execution_status": "completed",
  "response_kind": "plan",
  "goals_pred": [
    "go(kitchen)"
  ],
  "plan": [
    {
      "step": 1,
      "robot": "Justina",
      "action": "say",
      "params": [
        "I will navigate to kitchen"
      ]
    },
    {
      "step": 1001,
      "robot": "Justina",
      "action": "go_to",
      "params": [
        "kitchen"
      ]
    },
    {
      "step": 1002,
      "robot": "Justina",
      "action": "say",
      "params": [
        "I have arrived at kitchen"
      ]
    },
    {
      "step": 1003,
      "robot": "Justina",
      "action": "go_to",
      "params": [
        "instruction_point"
      ]
    },
    {
      "step": 1004,
      "robot": "Justina",
      "action": "say",
      "params": [
        "task completed"
      ]
    }
  ],
  "message": "",
  "raw_output": {
    "goals": [
      "go(kitchen)"
    ]
  },
  "raw_output_kind": "http_body",
  "timing": {
    "total_ms": 1000.0,
    "model_request_ms": 980.0,
    "adaptation_ms": 1.0,
    "planning_ms": 3.0,
    "extraction_ms": 1.0,
    "validation_ms": 2.0
  },
  "validation": {
    "response_schema_valid": true,
    "goals_schema_valid": true,
    "plan_contract_valid": true,
    "issues": []
  },
  "error": null,
  "qwen_clips": {
    "input_normalized": "go to the kitchen",
    "goals_after_adapter": [
      "go(kitchen)"
    ],
    "clips_facts": [
      "(gpsr-goal (step 1) (name go) (target \"kitchen\") (kind unknown) (destination \"\") (relation \"\") (value \"\") (qualifier \"\"))"
    ],
    "clips_plan_raw": "Paso 1: Justina say I will navigate to kitchen\nPaso 1001: Justina go_to kitchen\nPaso 1002: Justina say I have arrived at kitchen\nPaso 1003: Justina go_to instruction_point\nPaso 1004: Justina say task completed",
    "rules_fired": null,
    "planning_done": true,
    "remaining_goals": [],
    "diagnostics": [],
    "server_elapsed_ms": null
  },
  "gpt": null,
  "reference_clips": null
}
```

La forma del cuerpo HTTP anterior es ilustrativa; en la implementación se conserva la forma exacta que entregue tu servidor, incluidos sus campos adicionales. `rules_fired` y `server_elapsed_ms` se muestran en `null` para ilustrar datos no disponibles, no valores cero.

## 6. Ejemplo de salida de GPT directo

Misma orden, con objetivos y plan producidos en una sola respuesta. El campo original `status: executable` se conserva en `gpt.domain_status` y se traduce a `response_kind: plan` para el registro común.

```json
{
  "schema_version": "1.0",
  "example_only": true,
  "campaign_id": "EX-CAMPAIGN-01",
  "run_id": "EX-001-GPT-R01-A01",
  "case_id": "EX-001",
  "intent_id": "EX-INT-01",
  "architecture": "gpt_direct",
  "config_id": "EX-CFG-GPT-01",
  "repetition": 1,
  "attempt": 1,
  "started_at_utc": "2026-09-24T12:01:00.000Z",
  "finished_at_utc": "2026-09-24T12:01:01.300Z",
  "input_original": "Go to the kitchen.",
  "execution_status": "completed",
  "response_kind": "plan",
  "goals_pred": [
    "go(kitchen)"
  ],
  "plan": [
    {
      "step": 1,
      "robot": "Justina",
      "action": "say",
      "params": [
        "I will navigate to kitchen"
      ]
    },
    {
      "step": 1001,
      "robot": "Justina",
      "action": "go_to",
      "params": [
        "kitchen"
      ]
    },
    {
      "step": 1002,
      "robot": "Justina",
      "action": "say",
      "params": [
        "I have arrived at kitchen"
      ]
    },
    {
      "step": 1003,
      "robot": "Justina",
      "action": "go_to",
      "params": [
        "instruction_point"
      ]
    },
    {
      "step": 1004,
      "robot": "Justina",
      "action": "say",
      "params": [
        "task completed"
      ]
    }
  ],
  "message": "",
  "raw_output": "{\"status\": \"executable\", \"message\": \"\", \"goals\": [\"go(kitchen)\"], \"start_note\": \"GPSR_START\", \"plan\": [{\"step\": 1, \"robot\": \"Justina\", \"action\": \"say\", \"params\": [\"I will navigate to kitchen\"]}, {\"step\": 1001, \"robot\": \"Justina\", \"action\": \"go_to\", \"params\": [\"kitchen\"]}, {\"step\": 1002, \"robot\": \"Justina\", \"action\": \"say\", \"params\": [\"I have arrived at kitchen\"]}, {\"step\": 1003, \"robot\": \"Justina\", \"action\": \"go_to\", \"params\": [\"instruction_point\"]}, {\"step\": 1004, \"robot\": \"Justina\", \"action\": \"say\", \"params\": [\"task completed\"]}], \"end_note\": \"GPSR_DONE\"}",
  "raw_output_kind": "provider_output_text",
  "timing": {
    "total_ms": 1300.0,
    "model_request_ms": 1250.0,
    "adaptation_ms": null,
    "planning_ms": null,
    "extraction_ms": 20.0,
    "validation_ms": 5.0
  },
  "validation": {
    "response_schema_valid": true,
    "goals_schema_valid": true,
    "plan_contract_valid": true,
    "issues": []
  },
  "error": null,
  "qwen_clips": null,
  "gpt": {
    "requested_model": "gpt-5.6-terra",
    "returned_model": "gpt-5.6-terra",
    "response_id": "EX-RESPONSE-001",
    "provider_status": "completed",
    "domain_status": "executable",
    "usage": {
      "input_tokens": 4000,
      "output_tokens": 300,
      "total_tokens": 4300,
      "cached_input_tokens": 0,
      "reasoning_tokens": 50
    },
    "provider_response_artifact": null
  },
  "reference_clips": null
}
```

En una ejecución real, `provider_response_artifact` puede ser un objeto con `path` y `sha256` del JSON completo del proveedor; alternativamente se puede añadir `provider_response` con ese objeto completo dentro de `gpt`. El ejemplo no incluye un payload del proveedor fabricado. Los 50 tokens de razonamiento ilustrativos ya están incluidos en los 300 de salida.

## 7. Ejemplo de aclaración de GPT

Esta respuesta está terminada y tiene formato válido, pero no contiene un plan. Las listas vacías son parte explícita del contrato de aclaración.

```json
{
  "schema_version": "1.0",
  "example_only": true,
  "campaign_id": "EX-CAMPAIGN-01",
  "run_id": "EX-002-GPT-R01-A01",
  "case_id": "EX-002",
  "intent_id": "EX-INT-02",
  "architecture": "gpt_direct",
  "config_id": "EX-CFG-GPT-01",
  "repetition": 1,
  "attempt": 1,
  "started_at_utc": "2026-09-24T12:02:00.000Z",
  "finished_at_utc": "2026-09-24T12:02:01.300Z",
  "input_original": "Go to the kitchen and bring it to me.",
  "execution_status": "completed",
  "response_kind": "clarification",
  "goals_pred": [],
  "plan": [],
  "message": "What object should I bring you?",
  "raw_output": "{\"status\": \"clarification\", \"message\": \"What object should I bring you?\", \"goals\": [], \"start_note\": \"\", \"plan\": [], \"end_note\": \"\"}",
  "raw_output_kind": "provider_output_text",
  "timing": {
    "total_ms": 1300.0,
    "model_request_ms": 1250.0,
    "adaptation_ms": null,
    "planning_ms": null,
    "extraction_ms": 20.0,
    "validation_ms": 5.0
  },
  "validation": {
    "response_schema_valid": true,
    "goals_schema_valid": null,
    "plan_contract_valid": null,
    "issues": []
  },
  "error": null,
  "qwen_clips": null,
  "gpt": {
    "requested_model": "gpt-5.6-terra",
    "returned_model": "gpt-5.6-terra",
    "response_id": "EX-RESPONSE-002",
    "provider_status": "completed",
    "domain_status": "clarification",
    "usage": {
      "input_tokens": null,
      "output_tokens": null,
      "total_tokens": null,
      "cached_input_tokens": null,
      "reasoning_tokens": null
    },
    "provider_response_artifact": null
  },
  "reference_clips": null
}
```

Una respuesta de rechazo del dominio usa el mismo formato, con `response_kind: rejected`, `gpt.domain_status: rejected` y una razón en `message`. Por ejemplo, para `EX-003`: “Flying is outside the available action repertoire.” Se mantienen vacíos objetivos y plan en la respuesta GPT. Un bloqueo o negativa del proveedor se registra como incidencia diferenciada y no se convierte automáticamente en rechazo correcto de la tarea.

## 8. Ejemplo de tiempo agotado en Qwen

El intento debe aparecer en `resultados.jsonl` aunque no haya producido objetivos ni plan. `limit_ms` es el límite efectivamente aplicado.

```json
{
  "schema_version": "1.0",
  "example_only": true,
  "campaign_id": "EX-CAMPAIGN-01",
  "run_id": "EX-001-QWEN-R02-A01",
  "case_id": "EX-001",
  "intent_id": "EX-INT-01",
  "architecture": "qwen_clips",
  "config_id": "EX-CFG-QWEN-01",
  "repetition": 2,
  "attempt": 1,
  "started_at_utc": "2026-09-24T12:03:00.000Z",
  "finished_at_utc": "2026-09-24T12:04:00.000Z",
  "input_original": "Go to the kitchen.",
  "execution_status": "timeout",
  "response_kind": null,
  "goals_pred": null,
  "plan": null,
  "message": null,
  "raw_output": null,
  "raw_output_kind": null,
  "timing": {
    "total_ms": 60000.0,
    "model_request_ms": 60000.0,
    "adaptation_ms": null,
    "planning_ms": null,
    "extraction_ms": null,
    "validation_ms": null
  },
  "validation": {
    "response_schema_valid": null,
    "goals_schema_valid": null,
    "plan_contract_valid": null,
    "issues": []
  },
  "error": {
    "stage": "model_request",
    "type": "TimeoutError",
    "message": "No response before the configured request limit.",
    "limit_ms": 60000.0
  },
  "qwen_clips": null,
  "gpt": null,
  "reference_clips": null
}
```

Este ejemplo corresponde a la segunda repetición prevista en el manifiesto. Si se reintenta una solicitud fallida, se conserva su fila y se añade otra con igual `case_id` y `repetition`, `attempt` incrementado y nuevo `run_id`. La política del manifiesto debe autorizar ese reintento; con `automatic_retries: 0` no se reintenta automáticamente.

Antes de continuar tras un timeout, cancelar o aislar el trabajo pendiente. Si el servidor continúa procesando, su respuesta tardía no debe asignarse a otra orden. Si falla una etapa posterior a Qwen, conservar sus objetivos y todos los datos obtenidos antes del error.

## 9. Ejemplo del control con objetivos de referencia

El control recibe directamente los objetivos revisados; `goals_pred` queda en `null`. En una campaña real no se ejecutará como referencia aprobada una ficha que siga pendiente de revisión.

```json
{
  "schema_version": "1.0",
  "example_only": true,
  "campaign_id": "EX-CAMPAIGN-01",
  "run_id": "EX-001-CONTROL-R01-A01",
  "case_id": "EX-001",
  "intent_id": "EX-INT-01",
  "architecture": "reference_clips",
  "config_id": "EX-CFG-CONTROL-01",
  "repetition": 1,
  "attempt": 1,
  "started_at_utc": "2026-09-24T12:05:00.000Z",
  "finished_at_utc": "2026-09-24T12:05:00.008Z",
  "input_original": "Go to the kitchen.",
  "execution_status": "completed",
  "response_kind": "plan",
  "goals_pred": null,
  "plan": [
    {
      "step": 1,
      "robot": "Justina",
      "action": "say",
      "params": [
        "I will navigate to kitchen"
      ]
    },
    {
      "step": 1001,
      "robot": "Justina",
      "action": "go_to",
      "params": [
        "kitchen"
      ]
    },
    {
      "step": 1002,
      "robot": "Justina",
      "action": "say",
      "params": [
        "I have arrived at kitchen"
      ]
    },
    {
      "step": 1003,
      "robot": "Justina",
      "action": "go_to",
      "params": [
        "instruction_point"
      ]
    },
    {
      "step": 1004,
      "robot": "Justina",
      "action": "say",
      "params": [
        "task completed"
      ]
    }
  ],
  "message": "",
  "raw_output": null,
  "raw_output_kind": null,
  "timing": {
    "total_ms": 8.0,
    "model_request_ms": null,
    "adaptation_ms": 1.0,
    "planning_ms": 3.0,
    "extraction_ms": 1.0,
    "validation_ms": 2.0
  },
  "validation": {
    "response_schema_valid": null,
    "goals_schema_valid": true,
    "plan_contract_valid": true,
    "issues": []
  },
  "error": null,
  "qwen_clips": null,
  "gpt": null,
  "reference_clips": {
    "reference_version": "ejemplo-1",
    "goals_reference_input": [
      "go(kitchen)"
    ],
    "goals_after_adapter": [
      "go(kitchen)"
    ],
    "clips_facts": [
      "(gpsr-goal (step 1) (name go) (target \"kitchen\") (kind unknown) (destination \"\") (relation \"\") (value \"\") (qualifier \"\"))"
    ],
    "clips_plan_raw": "Paso 1: Justina say I will navigate to kitchen\nPaso 1001: Justina go_to kitchen\nPaso 1002: Justina say I have arrived at kitchen\nPaso 1003: Justina go_to instruction_point\nPaso 1004: Justina say task completed",
    "rules_fired": null,
    "planning_done": true,
    "remaining_goals": [],
    "diagnostics": []
  }
}
```

El tiempo del control no incluye interpretación por un modelo y se analiza como diagnóstico de la etapa simbólica. La identidad de hechos y reglas debe mantenerse respecto de Qwen–CLIPS.

## 10. Evaluación posterior

El evaluador combinará el resultado con la ficha de referencia. No debe editar la fila original ni consultar de nuevo al modelo. Puede generar nuevas versiones de la evaluación conservando `run_id`, `reference_version` y `evaluator_version`.

Registro inicial, todavía sin calificar:

```json
{
  "schema_version": "1.0",
  "example_only": true,
  "run_id": "EX-001-QWEN-R01-A01",
  "reference_version": "ejemplo-1",
  "evaluator_version": "evaluador-1.0",
  "evaluation_status": "pending",
  "goals_exact_match": null,
  "semantic_correct": null,
  "plan_contract_valid": null,
  "task_fulfillment": "pending",
  "failed_checks": [],
  "error_categories": [],
  "review_notes": "",
  "reviewer": null,
  "reviewed_at_utc": null
}
```

Ejemplo de una evaluación terminada con fallo semántico, correspondiente a un intento hipotético distinto que produjo `go(bedroom)` para la orden de ir a kitchen:

```json
{
  "schema_version": "1.0",
  "example_only": true,
  "run_id": "EX-001-QWEN-R03-A01",
  "reference_version": "ejemplo-1",
  "evaluator_version": "evaluador-1.0",
  "evaluation_status": "completed",
  "goals_exact_match": false,
  "semantic_correct": false,
  "plan_contract_valid": true,
  "task_fulfillment": "fail",
  "failed_checks": [
    "La ubicación solicitada era kitchen; los objetivos y el plan llevan a bedroom."
  ],
  "error_categories": [
    "interpretation"
  ],
  "review_notes": "Ejemplo ficticio: formato correcto con ubicación equivocada.",
  "reviewer": "REVISOR_EJEMPLO",
  "reviewed_at_utc": "2026-09-24T13:00:00Z"
}
```

Valores de `task_fulfillment`: `pending`, `pass`, `fail`, `not_verifiable` y `not_applicable`. El último se reserva para casos sin tarea ejecutable de referencia, como aclaraciones o rechazos esperados. Para esos casos se puede añadir `domain_response_correct` (booleano o null) y explicar si el mensaje pide el dato correcto o justifica el rechazo. No penalizarlos automáticamente por carecer de plan en la métrica del bloque resoluble.

Para `reference_clips`, `goals_exact_match` y `semantic_correct` son `null`: no hubo predicción lingüística. Se calificará su plan. En cualquier arquitectura, la revisión pendiente no se confunde con un fallo. Si una orden resoluble acaba en timeout, la evaluación posterior registra cumplimiento no obtenido y error de infraestructura; la fila de generación mantiene los campos de validación no realizados en `null`.

Las etiquetas de error propuestas son `interpretation`, `adaptation`, `planning`, `infrastructure` y `output_truncation`; pueden coexistir. La etapa técnica en que se captura un error no demuestra por sí sola su causa semántica. No atribuir automáticamente todos los problemas de una ejecución al primer componente que falló.

## 11. Requisitos de implementación y aceptación

1. **Aislamiento.** Una solicitud cada vez, sin historial GPT y con estado CLIPS reiniciado entre órdenes. Conservar el modelo cargado cuando corresponda y medir la carga inicial fuera del tiempo de respuesta.
2. **Trazabilidad.** Cada intento tiene `run_id` único; todas las evaluaciones lo referencian. Registrar versión del conjunto y configuración mediante el manifiesto.
3. **Misma lógica.** La ruta independiente de Qwen–CLIPS reutiliza el adaptador y reglas del sistema integrado. Comprobar con objetivos idénticos que ambas rutas producen hechos y planes equivalentes antes de la prueba final.
4. **Sin correcciones ocultas.** Guardar objetivos originales antes de adaptar; conservar texto crudo y pasos originales. Si se repara una salida, registrar la transformación.
5. **Fallos incluidos.** Toda solicitud iniciada deja un registro de resultado cuando finaliza o falla. Para interrupciones abruptas del proceso, se recomienda un diario separado de inicio/fin que permita detectar intentos incompletos; no convertir una interrupción desconocida en éxito o timeout inventado.
6. **Reanudación.** No sobrescribir datos. Distinguir el intento incompleto de un nuevo intento y evitar duplicar identificadores.
7. **Terminación CLIPS.** Inspeccionar finalización, objetivos pendientes y diagnósticos de falta de soporte. `planning_done: true` no implica cumplimiento de la orden.
8. **Referencias separadas.** Qwen y GPT reciben solo la orden y su configuración fija. El control es la única condición que recibe directamente `goals_ref`.
9. **Contrato de acciones común.** Exportar ambos planes como pasos `step`, `robot`, `action`, `params`. Aplicar la misma evaluación del contenido sin usar automáticamente la salida de CLIPS como respuesta correcta.
10. **Registro verificable.** Antes de procesar todo el conjunto, comprobar una respuesta con plan, una aclaración GPT, una salida inválida y un error técnico, junto con el control. Los ejemplos de este archivo no sustituyen esas comprobaciones reales.

## 12. Prioridad para la primera versión

La primera versión debe permitir leer el JSONL, ejecutar cada condición, guardar una fila por intento y conservar: identificadores, texto original, salida recibida, objetivos originales, hechos CLIPS, plan, estado, error y tiempo total. Debe mantener también la separación de referencias y el reinicio de estado.

Después se puede ampliar la instrumentación de tiempos internos, recursos y diagnósticos. Los campos todavía no disponibles permanecen en `null`; el programa no debe presentarlos como medidos. La evaluación semántica y de cumplimiento se completa en el evaluador, no a partir de un indicador de formato válido.

