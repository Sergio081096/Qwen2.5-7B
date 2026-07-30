import argparse
import json
import os
import resource
import time
from typing import Any

import torch
from command_normalizer import get_default_normalizer
from goal_schema import validate_goals as validate_goal_schema
from peft import PeftModel
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


# =====================================================
# CONFIGURACION
# =====================================================
BASE_MODEL_NAME = "Qwen/Qwen2.5-7B"
# Debe apuntar al mismo OUTPUT_DIR con el que terminó Nl-Cl.py.
ADAPTER_PATH = "nl2cd_qwen7b"
MAX_NEW_TOKENS = 128
INVALID_MARKERS = ("WARNING", "None", "{", "}")
AUTO_DEVICE_MAPS = {"auto", "balanced", "balanced_low_0", "sequential"}
DEFAULT_DEVICE_MAP = "cuda:0"


# =====================================================
# MEDICION DE RECURSOS
# =====================================================
def default_cpu_threads():
    return os.cpu_count() or 1


def configure_runtime_resources(cpu_threads=None, cuda_device=None, allow_tf32=True):
    if cpu_threads is None:
        cpu_threads = default_cpu_threads()
    cpu_threads = max(1, int(cpu_threads))

    torch.set_num_threads(cpu_threads)
    try:
        torch.set_num_interop_threads(max(1, min(cpu_threads, 8)))
    except RuntimeError:
        pass

    if cuda_device is not None and torch.cuda.is_available():
        torch.cuda.set_device(cuda_device)

    if torch.cuda.is_available() and allow_tf32:
        matmul_backend = torch.backends.cuda.matmul
        if hasattr(matmul_backend, "fp32_precision"):
            matmul_backend.fp32_precision = "tf32"
        else:
            matmul_backend.allow_tf32 = True

        cudnn_backend = torch.backends.cudnn
        if hasattr(cudnn_backend, "conv") and hasattr(cudnn_backend.conv, "fp32_precision"):
            cudnn_backend.conv.fp32_precision = "tf32"
        else:
            cudnn_backend.allow_tf32 = True
    return cpu_threads


def format_gb(num_bytes):
    return num_bytes / 1024**3


def process_cpu_seconds():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def process_peak_rss_mb():
    # En Linux ru_maxrss viene en KiB.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def synchronize_cuda():
    if not torch.cuda.is_available():
        return
    for device_idx in range(torch.cuda.device_count()):
        try:
            torch.cuda.synchronize(device_idx)
        except RuntimeError:
            continue


def reset_cuda_peak_stats():
    if not torch.cuda.is_available():
        return
    for device_idx in range(torch.cuda.device_count()):
        try:
            torch.cuda.reset_peak_memory_stats(device_idx)
        except RuntimeError:
            continue


def gpu_resource_lines():
    if not torch.cuda.is_available():
        return ["GPU: CUDA no disponible"]

    lines = []
    for device_idx in range(torch.cuda.device_count()):
        try:
            allocated = torch.cuda.memory_allocated(device_idx)
            reserved = torch.cuda.memory_reserved(device_idx)
            peak_allocated = torch.cuda.max_memory_allocated(device_idx)
            peak_reserved = torch.cuda.max_memory_reserved(device_idx)
            with torch.cuda.device(device_idx):
                free_bytes, total_bytes = torch.cuda.mem_get_info()
            device_name = torch.cuda.get_device_name(device_idx)
        except RuntimeError as exc:
            lines.append(f"GPU cuda:{device_idx}: metricas no disponibles ({exc})")
            continue

        lines.append(
            "GPU cuda:{idx} {name}: asignada {alloc:.2f} GB, reservada {reserved:.2f} GB, "
            "pico asignada {peak_alloc:.2f} GB, pico reservada {peak_reserved:.2f} GB, "
            "libre/total {free:.2f}/{total:.2f} GB".format(
                idx=device_idx,
                name=device_name,
                alloc=format_gb(allocated),
                reserved=format_gb(reserved),
                peak_alloc=format_gb(peak_allocated),
                peak_reserved=format_gb(peak_reserved),
                free=format_gb(free_bytes),
                total=format_gb(total_bytes),
            )
        )
    return lines


class ResourceTimer:
    def __init__(self, label):
        self.label = label

    def __enter__(self):
        reset_cuda_peak_stats()
        synchronize_cuda()
        self.start_wall = time.perf_counter()
        self.start_cpu = process_cpu_seconds()
        return self

    def __exit__(self, exc_type, exc, traceback):
        synchronize_cuda()
        elapsed_wall = time.perf_counter() - self.start_wall
        elapsed_cpu = process_cpu_seconds() - self.start_cpu
        cpu_percent = (elapsed_cpu / elapsed_wall * 100) if elapsed_wall else 0.0

        print(f"\n[recursos] {self.label}")
        print(
            "Tiempo: {wall:.2f}s | CPU proceso: {cpu:.2f}s ({percent:.1f}%) | "
            "RAM pico proceso: {rss:.1f} MB".format(
                wall=elapsed_wall,
                cpu=elapsed_cpu,
                percent=cpu_percent,
                rss=process_peak_rss_mb(),
            )
        )
        for line in gpu_resource_lines():
            print(line)
        print()
        return False


# =====================================================
# CARGA DE MODELO
# =====================================================
def get_compute_dtype():
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float16


def load_tokenizer(adapter_path=ADAPTER_PATH):
    tokenizer = AutoTokenizer.from_pretrained(adapter_path, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def load_model_config():
    config = AutoConfig.from_pretrained(BASE_MODEL_NAME, trust_remote_code=True)
    config.use_sliding_window = False
    config.sliding_window = None
    config.max_window_layers = 0
    return config


def normalize_max_memory_keys(max_memory):
    normalized = {}
    for key, value in max_memory.items():
        if isinstance(key, str) and key.isdigit():
            key = int(key)
        normalized[key] = value
    return normalized


def parse_max_memory(max_memory):
    if not max_memory:
        return None
    if isinstance(max_memory, dict):
        return normalize_max_memory_keys(max_memory)

    max_memory = str(max_memory).strip()
    if not max_memory:
        return None

    if max_memory.startswith("{"):
        data = json.loads(max_memory)
        if not isinstance(data, dict):
            raise ValueError("max_memory JSON must be an object")
        return normalize_max_memory_keys(data)

    memory = {}
    for item in max_memory.split(","):
        if not item.strip():
            continue
        if "=" not in item:
            raise ValueError("max_memory entries must use key=value, for example 0=10GiB,cpu=24GiB")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key.isdigit():
            key = int(key)
        if key == "" or not value:
            raise ValueError("max_memory entries cannot have empty keys or values")
        memory[key] = value
    return memory or None


def normalize_device_map(device_map):
    if device_map is None:
        return DEFAULT_DEVICE_MAP
    if isinstance(device_map, dict):
        return device_map

    device_map = str(device_map).strip()
    if not device_map or device_map in AUTO_DEVICE_MAPS:
        return device_map or DEFAULT_DEVICE_MAP
    if device_map.isdigit():
        return {"": int(device_map)}
    if device_map.startswith("{"):
        data = json.loads(device_map)
        if not isinstance(data, dict):
            raise ValueError("device_map JSON must be an object")
        return data
    return {"": device_map}


def model_input_device(model):
    device = getattr(model, "device", None)
    if device is not None and getattr(device, "type", None) != "meta":
        return device

    for parameter in model.parameters():
        if parameter.device.type != "meta":
            return parameter.device

    return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def load_model(
    compute_dtype,
    device_map=DEFAULT_DEVICE_MAP,
    max_memory=None,
    cpu_offload=False,
    adapter_path=ADAPTER_PATH,
):
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        llm_int8_enable_fp32_cpu_offload=cpu_offload,
    )
    from_pretrained_kwargs: dict[str, Any] = {
        "config": load_model_config(),
        "quantization_config": bnb_config,
        "device_map": normalize_device_map(device_map),
        "torch_dtype": compute_dtype,
        "attn_implementation": "eager",
        "trust_remote_code": True,
    }
    parsed_max_memory = parse_max_memory(max_memory)
    if parsed_max_memory:
        from_pretrained_kwargs["max_memory"] = parsed_max_memory

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_NAME,
        **from_pretrained_kwargs,
    )
    model = PeftModel.from_pretrained(base_model, adapter_path)
    model.eval()
    return model


# =====================================================
# PROMPT, EXTRACCION Y VALIDACION
# =====================================================
def build_prompt(tokenizer, command):
    messages = [{"role": "user", "content": command}]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


def extract_json(text):
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
    if not isinstance(data, dict):
        return False
    goals = data.get("goals")
    if not isinstance(goals, list) or not goals:
        return False
    if not all(isinstance(goal, str) and goal.strip() for goal in goals):
        return False
    joined = " ".join(goals)
    # La respuesta HTTP solo se considera válida si también cumple el contrato
    # usado para construir el dataset. Esto bloquea find()/count() ambiguos.
    return (
        not any(marker in joined for marker in INVALID_MARKERS)
        and not validate_goal_schema(goals)
    )


def generation_eos_ids(tokenizer):
    eos_ids = []
    if tokenizer.eos_token_id is not None:
        eos_ids.append(tokenizer.eos_token_id)

    im_end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
    if isinstance(im_end_id, int) and im_end_id >= 0 and im_end_id not in eos_ids:
        eos_ids.append(im_end_id)

    return eos_ids[0] if len(eos_ids) == 1 else eos_ids


def translate(command, model, tokenizer, normalizer=None, return_normalized=False):
    normalized_command = normalizer.normalize(command) if normalizer else command
    prompt = build_prompt(tokenizer, normalized_command)
    inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(model_input_device(model))

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            repetition_penalty=1.05,
            eos_token_id=generation_eos_ids(tokenizer),
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][inputs["input_ids"].shape[-1] :]
    assistant_part = tokenizer.decode(generated_ids, skip_special_tokens=False)
    assistant_part = assistant_part.split("<|im_end|>")[0]
    if tokenizer.eos_token:
        assistant_part = assistant_part.split(tokenizer.eos_token)[0]
    assistant_part = assistant_part.strip()

    parsed = extract_json(assistant_part)
    if parsed and validate_goals(parsed):
        if return_normalized:
            return {"normalized_input": normalized_command, "prediction": parsed}
        return parsed
    error = {"error": "Invalid JSON", "raw": assistant_part[:200]}
    if return_normalized:
        error["normalized_input"] = normalized_command
    return error


# =====================================================
# PRUEBAS
# =====================================================
def parse_args():
    parser = argparse.ArgumentParser(description="Run local Qwen GPSR inference tests.")
    parser.add_argument("--device-map", default=DEFAULT_DEVICE_MAP)
    parser.add_argument("--max-memory", default="")
    parser.add_argument("--cpu-offload", action="store_true")
    parser.add_argument("--cpu-threads", type=int, default=default_cpu_threads())
    parser.add_argument("--no-tf32", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    used_threads = configure_runtime_resources(
        cpu_threads=args.cpu_threads,
        allow_tf32=not args.no_tf32,
    )
    print(f"Runtime: CPU threads={used_threads} | device_map={args.device_map}")

    print("Cargando tokenizer...")
    with ResourceTimer("carga tokenizer"):
        tokenizer = load_tokenizer()

    print("Cargando modelo base y adaptador LoRA...")
    with ResourceTimer("carga modelo base y adaptador LoRA"):
        model = load_model(
            get_compute_dtype(),
            device_map=args.device_map,
            max_memory=args.max_memory or None,
            cpu_offload=args.cpu_offload,
        )
    normalizer = get_default_normalizer()

    tests = [
        "uh could you go to the the kichen and grab the apple joos",
        "please head to the living_room then look around for Robin",
        "robot pick up the cleanser from the refridgerator",
        "follow the person the waving person in the ofice",
        "follow the person pointing to the left in the living room",
        "answer the question of the waving person in the office",
        "tell me what is the largest object on the sofa",
        "meet Sarah at the potted plant then locate them in the corridor",
        "bring a cleanser from the refrigerator to the sofa",
        "Go to the kitchen and bring me an apple"
    ]

    print("\nModelo Qwen2.5-7B GPSR\n")
    for test in tests:
        normalized = normalizer.normalize(test)
        with ResourceTimer(f"inferencia: {test[:60]}"):
            result = translate(test, model, tokenizer, normalizer=normalizer)
        print(f"Input: {test}")
        print(f"Normalizado: {normalized}")
        print(f"Output: {json.dumps(result, indent=2, ensure_ascii=False)}")
        print("-" * 50)


if __name__ == "__main__":
    main()
