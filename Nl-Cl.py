"""Ajuste QLoRA de Qwen2.5-7B para traducir comandos GPSR a goals.

El entrenamiento es *completion-only*: el comando forma el turno ``user`` y
el modelo aprende únicamente el JSON del turno ``assistant``. Los tokens del
prompt se mantienen como contexto, pero reciben label ``-100`` y no participan
en la pérdida.

Flujo: validar JSONL -> split -> chat template -> Qwen 4-bit + LoRA -> Trainer
-> mejor checkpoint -> métricas semánticas/CLIPS -> ``loss_curve.png``.
"""

import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib
import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dataset_evaluation import (
    DEFAULT_CLIPS_RULES,
    ClipsPlanValidator,
    evaluate_predictions,
    print_evaluation_report,
)
from goal_schema import validate_goals as validate_goal_schema


# =====================================================
# 1. CONFIGURACION: valores que normalmente cambian entre experimentos
# =====================================================
MODEL_NAME = "Qwen/Qwen2.5-7B"
DATA_PATH = "dataset_gpsr.jsonl"
# DATA_PATH = "dataset_gpsr_augmented.jsonl"
OUTPUT_DIR = "nl2cd_qwen7b"
LOSS_CURVE_PATH = "loss_curve.png"

# Longitud combinada máxima de comando y respuesta. Reducirla puede truncar los
# goals finales de órdenes compuestas.
MAX_LENGTH = 512
# Con 40,000 muestras, 0.1 produce 36,000 para train y 4,000 para evaluación.
TEST_SIZE = 0.1
RANDOM_SEED = 42
# Esta evaluación generativa es una alarma rápida. Para una evaluación estable
# y con gráficas se usa después ``evaluate_model.py``.
EXACT_MATCH_SAMPLES = 50

INVALID_MARKERS = ("WARNING", "None", "{", "}")


# =====================================================
# 2. DATASET Y FORMATO CHAT
# =====================================================
def goals_to_json(item):
    """Serializa solamente la respuesta supervisada, nunca los metadatos."""
    return json.dumps({"goals": item["goals"]}, ensure_ascii=False)


def validate_source_item(item, line_no):
    """Valida una fila antes de cargar el modelo y reservar memoria de GPU."""
    if not isinstance(item, dict):
        raise ValueError(f"Linea {line_no}: el registro no es un objeto JSON")
    if not isinstance(item.get("input"), str) or not item["input"].strip():
        raise ValueError(f"Linea {line_no}: 'input' debe ser texto no vacio")
    if not isinstance(item.get("goals"), list) or not item["goals"]:
        raise ValueError(f"Linea {line_no}: 'goals' debe ser una lista no vacia")
    if not all(isinstance(goal, str) and goal.strip() for goal in item["goals"]):
        raise ValueError(f"Linea {line_no}: todos los goals deben ser strings no vacios")

    # Fallar durante la carga es preferible a entrenar durante horas con labels
    # ambiguos o imposibles de convertir en un plan de Justina.
    schema_issues = validate_goal_schema(item["goals"])
    if schema_issues:
        raise ValueError(
            f"Linea {line_no}: etiqueta fuera del esquema canónico: "
            + "; ".join(map(str, schema_issues))
        )

    joined = item["input"] + " " + " ".join(item["goals"])
    for marker in INVALID_MARKERS:
        if marker in joined:
            raise ValueError(f"Linea {line_no}: contiene marcador invalido {marker!r}")


def load_jsonl_dataset(path):
    """Carga el JSONL conservando family/category para métricas posteriores."""
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            item = json.loads(line)
            validate_source_item(item, line_no)
            # family/category se conservan para las métricas, pero no se agregan
            # al target del modelo: la respuesta aprendida sigue siendo goals.
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
            data.append(
                {
                    "input": item["input"],
                    "response": goals_to_json(item),
                    "family": str(meta.get("family", "unknown")),
                    "category": str(meta.get("category", "unknown")),
                }
            )
    return Dataset.from_list(data)


def build_prompt(tokenizer, command):
    """Construye el mismo prefijo de chat que se utilizará en inferencia."""
    messages = [{"role": "user", "content": command}]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


def build_training_text(tokenizer, command, response):
    """Construye la conversación completa user/assistant para supervisión."""
    messages = [
        {"role": "user", "content": command},
        {"role": "assistant", "content": response},
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    if tokenizer.eos_token and not text.endswith(tokenizer.eos_token):
        text += tokenizer.eos_token
    return text


def tokenize_function(examples, tokenizer):
    """Tokeniza un lote y enmascara con ``-100`` todos los tokens del prompt."""
    batch = {"input_ids": [], "attention_mask": [], "labels": []}

    for command, response in zip(examples["input"], examples["response"]):
        prompt = build_prompt(tokenizer, command)
        full_text = build_training_text(tokenizer, command, response)

        prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
        tokenized = tokenizer(
            full_text,
            add_special_tokens=False,
            truncation=True,
            max_length=MAX_LENGTH,
            padding=False,
        )

        input_ids = tokenized["input_ids"]
        # CrossEntropyLoss ignora -100: Qwen ve el comando, pero aprende solo a
        # producir la respuesta JSON a partir de prompt_len.
        prompt_len = min(len(prompt_ids), len(input_ids))
        labels = [-100] * prompt_len + input_ids[prompt_len:]

        batch["input_ids"].append(input_ids)
        batch["attention_mask"].append(tokenized["attention_mask"])
        batch["labels"].append(labels)

    return batch


class CompletionOnlyCollator:
    """Padding dinámico que mantiene alineados input_ids, máscara y labels.

    Los labels añadidos como padding también usan -100. Redondear a múltiplos
    de 8 suele aprovechar mejor Tensor Cores sin paddear todo a MAX_LENGTH.
    """
    def __init__(self, tokenizer, pad_to_multiple_of=8):
        self.tokenizer = tokenizer
        self.pad_to_multiple_of = pad_to_multiple_of

    def __call__(self, features):
        pad_token_id = self.tokenizer.pad_token_id
        if pad_token_id is None:
            pad_token_id = self.tokenizer.eos_token_id

        seq_len = max(len(feature["input_ids"]) for feature in features)
        if self.pad_to_multiple_of:
            remainder = seq_len % self.pad_to_multiple_of
            if remainder:
                seq_len += self.pad_to_multiple_of - remainder

        padded_input_ids = []
        padded_attention_mask = []
        padded_labels = []

        for feature in features:
            input_ids = feature["input_ids"]
            attention_mask = feature["attention_mask"]
            labels = feature["labels"]
            pad_len = seq_len - len(input_ids)

            if self.tokenizer.padding_side == "left":
                padded_input_ids.append([pad_token_id] * pad_len + input_ids)
                padded_attention_mask.append([0] * pad_len + attention_mask)
                padded_labels.append([-100] * pad_len + labels)
            else:
                padded_input_ids.append(input_ids + [pad_token_id] * pad_len)
                padded_attention_mask.append(attention_mask + [0] * pad_len)
                padded_labels.append(labels + [-100] * pad_len)

        return {
            "input_ids": torch.tensor(padded_input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(padded_attention_mask, dtype=torch.long),
            "labels": torch.tensor(padded_labels, dtype=torch.long),
        }


# =====================================================
# 3. MODELO Y TOKENIZER
# =====================================================
def configure_cuda():
    """Falla temprano sin CUDA y reserva un margen para el resto del sistema."""
    if not torch.cuda.is_available():
        raise RuntimeError("Este entrenamiento QLoRA 4-bit requiere CUDA disponible.")
    torch.cuda.set_per_process_memory_fraction(0.9)


def get_compute_dtype():
    """Prefiere BF16 cuando existe soporte; FP16 es el fallback compatible."""
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float16


def load_tokenizer():
    """Carga el tokenizer base que después se guarda junto con el adaptador."""
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def load_model_config():
    """Desactiva sliding-window para esta configuración de Qwen/Transformers."""
    config = AutoConfig.from_pretrained(MODEL_NAME, trust_remote_code=True)
    config.use_sliding_window = False
    config.sliding_window = None
    config.max_window_layers = 0
    return config


def load_model(compute_dtype):
    """Carga Qwen cuantizado en NF4 y lo prepara para entrenamiento QLoRA.

    Double quantization reduce memoria adicionalmente. Gradient checkpointing
    reduce activaciones almacenadas a cambio de volver a calcular algunas.
    """
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
    )

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        config=load_model_config(),
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=compute_dtype,
        attn_implementation="eager",
        trust_remote_code=True,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    return model


def apply_lora(model):
    """Inserta adaptadores LoRA en atención y MLP; el modelo base queda fijo."""
    peft_config = LoraConfig(
        # r determina capacidad/tamaño; alpha escala el aporte de LoRA.
        r=32,
        lora_alpha=64,
        lora_dropout=0.05,
        # Ajustar atención + MLP aumenta capacidad respecto a usar solo
        # q_proj/v_proj, con un adaptador final cercano a 309 MB.
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    return model


# =====================================================
# 4. EXTRACCION, VALIDACION E INFERENCIA
# =====================================================
def extract_json(text):
    """Extrae el primer objeto JSON completo balanceando llaves."""
    start = text.find("{")
    if start == -1:
        return None

    bracket_count = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            bracket_count += 1
        elif text[i] == "}":
            bracket_count -= 1

        if bracket_count == 0:
            try:
                return json.loads(text[start : i + 1])
            except json.JSONDecodeError:
                return None
    return None


def validate_goals(data):
    """Exige JSON correcto y el mismo contrato canónico usado por el dataset."""
    if not isinstance(data, dict):
        return False
    goals = data.get("goals")
    if not isinstance(goals, list) or not goals:
        return False
    if not all(isinstance(goal, str) and goal.strip() for goal in goals):
        return False
    joined = " ".join(goals)
    return (
        not any(marker in joined for marker in INVALID_MARKERS)
        and not validate_goal_schema(goals)
    )


def generation_eos_ids(tokenizer):
    """Permite detenerse tanto en EOS como al final del turno de Qwen."""
    eos_ids = []
    if tokenizer.eos_token_id is not None:
        eos_ids.append(tokenizer.eos_token_id)

    im_end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
    if isinstance(im_end_id, int) and im_end_id >= 0 and im_end_id not in eos_ids:
        eos_ids.append(im_end_id)

    return eos_ids[0] if len(eos_ids) == 1 else eos_ids


def translate_to_json(model, tokenizer, command_str):
    """Inferencia determinista usada para evaluar el modelo al terminar."""
    prompt = build_prompt(tokenizer, command_str)
    inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            repetition_penalty=1.05,
            eos_token_id=generation_eos_ids(tokenizer),
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[-1] :]
    decoded = tokenizer.decode(generated_ids, skip_special_tokens=False)
    decoded = decoded.split("<|im_end|>")[0]
    if tokenizer.eos_token:
        decoded = decoded.split(tokenizer.eos_token)[0]

    parsed = extract_json(decoded)
    if parsed and validate_goals(parsed):
        return parsed
    return {"error": "Invalid JSON", "raw": decoded[:200]}


def evaluate_exact_match(model, tokenizer, raw_eval_dataset, max_samples=50):
    """Mide exact match, kinds, slots y CLIPS sobre una muestra del holdout."""
    sample_count = min(max_samples, len(raw_eval_dataset))
    if sample_count == 0:
        print("No hay muestras de validacion para exact match.")
        return

    clips_validator = None
    try:
        clips_validator = ClipsPlanValidator(DEFAULT_CLIPS_RULES)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Validación CLIPS no disponible durante evaluación: {exc}")

    rows = raw_eval_dataset.select(range(sample_count))
    # Además de exact match se miden familia, kind, slots y planificabilidad.
    report = evaluate_predictions(
        rows,
        predict=lambda command: translate_to_json(model, tokenizer, command),
        clips_validator=clips_validator,
        max_samples=sample_count,
    )
    if clips_validator is not None:
        clips_validator.close()
    print_evaluation_report(report, "Evaluación semántica del modelo")

    totals = report["totals"]
    correct = totals.get("exact", 0)
    accuracy = correct / sample_count
    print(f"Exact match JSON: {correct}/{sample_count} ({accuracy:.1%})")


# =====================================================
# 5. VISUALIZACION
# =====================================================
def plot_losses(trainer):
    """Grafica el historial que Trainer conserva en ``state.log_history``.

    La pérdida de entrenamiento se registra cada ``logging_steps`` y la de
    validación cada ``eval_steps``; por eso no necesariamente tienen el mismo
    número de puntos. La selección del mejor checkpoint usa directamente
    ``eval_loss`` y no depende de esta imagen.
    """
    logs = trainer.state.log_history
    train_steps, train_loss = [], []
    eval_steps, eval_loss = [], []

    for log in logs:
        if "loss" in log and "step" in log:
            train_steps.append(log["step"])
            train_loss.append(log["loss"])
        if "eval_loss" in log and "step" in log:
            eval_steps.append(log["step"])
            eval_loss.append(log["eval_loss"])

    plt.figure(figsize=(10, 5.5))
    if train_steps:
        plt.plot(train_steps, train_loss, label="Train Loss")
    if eval_steps:
        plt.plot(eval_steps, eval_loss, label="Validation Loss")
    plt.xlabel("Steps")
    plt.ylabel("Loss")
    plt.title("Training vs Validation Loss")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(LOSS_CURVE_PATH, dpi=160)
    plt.close()


# =====================================================
# 6. ENTRENAMIENTO
# =====================================================
def main():
    """Ejecuta de principio a fin un experimento reproducible de QLoRA."""
    # Primero se hacen comprobaciones baratas. Si el dataset es inválido, el
    # proceso falla antes de reservar los varios GB que necesita Qwen en GPU.
    configure_cuda()
    compute_dtype = get_compute_dtype()

    print("Cargando tokenizer...")
    tokenizer = load_tokenizer()

    print("Cargando dataset...")
    raw_dataset = load_jsonl_dataset(DATA_PATH)
    # El seed mantiene estable el holdout entre ejecuciones con el mismo JSONL.
    split_dataset = raw_dataset.train_test_split(test_size=TEST_SIZE, seed=RANDOM_SEED)
    raw_train_dataset = split_dataset["train"]
    raw_eval_dataset = split_dataset["test"]

    print("Tokenizando dataset con labels solo en la respuesta...")
    train_dataset = raw_train_dataset.map(
        lambda examples: tokenize_function(examples, tokenizer),
        batched=True,
        remove_columns=raw_train_dataset.column_names,
    )
    eval_dataset = raw_eval_dataset.map(
        lambda examples: tokenize_function(examples, tokenizer),
        batched=True,
        remove_columns=raw_eval_dataset.column_names,
    )

    print("Cargando modelo Qwen2.5-7B en 4-bit...")
    model = load_model(compute_dtype)
    model = apply_lora(model)

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        # Batch efectivo = 1 muestra * 8 acumulaciones = 8. Cambiar cualquiera
        # de ambos valores modifica memoria, pasos totales y dinámica del LR.
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        num_train_epochs=2,
        learning_rate=1e-4,
        fp16=compute_dtype == torch.float16,
        bf16=compute_dtype == torch.bfloat16,
        logging_steps=50,
        save_strategy="steps",
        save_steps=500,
        eval_strategy="steps",
        eval_steps=250,
        # Trainer conserva/restituye el checkpoint con menor eval_loss. Para
        # que funcione, save_steps debe ser múltiplo de eval_steps.
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        # El warmup evita un cambio brusco al comenzar; después el scheduler
        # coseno reduce gradualmente el learning rate casi hasta cero.
        warmup_steps=150,
        lr_scheduler_type="cosine",
        report_to="none",
        save_total_limit=2,
        label_names=["labels"],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=CompletionOnlyCollator(tokenizer),
    )

    print("Entrenando modelo Qwen2.5-7B...")
    trainer.train()

    # save_model escribe los pesos LoRA seleccionados, no otra copia completa
    # de Qwen2.5-7B. El modelo base se vuelve a obtener de MODEL_NAME.
    print("Guardando adaptador LoRA y tokenizer...")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print("Evaluando exact match en muestras de validacion...")
    model.eval()
    evaluate_exact_match(model, tokenizer, raw_eval_dataset, EXACT_MATCH_SAMPLES)

    # Se grafica después de train para incluir el historial completo, aunque el
    # modelo en memoria ya corresponda al mejor checkpoint restaurado.
    plot_losses(trainer)
    print(f"Curva de perdida guardada en {LOSS_CURVE_PATH}")

    test_phrases = [
        "go to the kitchen",
        "find a sitting person in the office and follow them",
        "tell me what is the largest object on the sofa",
        "bring a sponge from the refrigerator to the sofa",
        "answer the question of the waving person in the office",
    ]

    print("\nPRUEBAS\n")
    for phrase in test_phrases:
        result = translate_to_json(model, tokenizer, phrase)
        print(f"Entrada: {phrase}")
        print("Salida:", json.dumps(result, indent=2, ensure_ascii=False))
        print("-" * 50)


if __name__ == "__main__":
    main()
