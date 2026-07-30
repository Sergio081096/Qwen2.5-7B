#!/usr/bin/env python3
"""
Script para generar un dataset balanceado de comandos GPSR con metas (goals).
Configuración manual: modifica NUM_SAMPLES y PERSON_RATIO según necesidad.
"""

import json
import random
from collections import Counter

from catalog_validation import DEFAULT_JUSTINA_NAMES, print_catalog_report, validate_catalogs
from dataset_evaluation import (
    DEFAULT_CLIPS_RULES,
    ClipsPlanValidator,
    evaluate_dataset_rows,
    print_evaluation_report,
)
from goal_schema import entity_kinds, goal_signature, slot_names, validate_goals
from gpsr_commands import CommandGenerator
from knowledge import parse_data

# ================= CONFIGURACIÓN MANUAL =================
DATA_DIR = "./CompetitionTemplate"       # Directorio con los datos del mundo
NUM_SAMPLES = 40000                      # Número total de comandos a generar
PERSON_RATIO = 0.5                       # Proporción de comandos de personas
RANDOM_SEED = 42                         # Semilla para reproducibilidad
OUTPUT_FILE = "dataset_gpsr.jsonl"       # Archivo de salida
DEDUPLICATE = True                       # Evita fuga de inputs exactos entre splits
MAX_ATTEMPTS_PER_SAMPLE = 50             # Límite antes de considerar saturación
CLIPS_VALIDATION_SAMPLES = 200           # 0 valida todas las muestras
JUSTINA_NAMES_FILE = DEFAULT_JUSTINA_NAMES
CLIPS_RULES_FILE = DEFAULT_CLIPS_RULES
# ========================================================

def enumerate_and_save(knowledge, output_file="command_variants.jsonl"):
    """
    Genera todas las variantes posibles de todas las plantillas principales
    (y sus follow‑ups) y las guarda en un archivo JSONL.
    """
    gen = CommandGenerator(knowledge, debug=True)
    all_variants = []

    # Recorremos todas las plantillas de comandos principales
    for cmd_key in gen.templates:
        # Probar las categorías people, objects y mixta (cadena vacía).
        for cat in ["people", "objects", ""]:
            try:
                variants = gen.enumerate_command_variants(cmd_key, cat)
                # for v in variants:
                #     v["command_type"] = cmd_key
                #     v["category"] = cat
                all_variants.extend(
                    _enrich_sample(item, cmd_key, cat or "mixed")
                    for item in variants
                )
            except Exception as e:
                print(f"Error con {cmd_key}/{cat}: {e}")

    with open(output_file, "w", encoding="utf-8") as f:
        for item in all_variants:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Se escribieron {len(all_variants)} variantes en {output_file}")

def _normalized_input(text):
    """Crea la clave usada para detectar frases exactamente equivalentes."""
    return " ".join(text.casefold().split())


def _enrich_sample(sample, command_key, category):
    """Valida la etiqueta y añade metadatos que no se envían al modelo."""
    goals = sample.get("goals", [])
    issues = validate_goals(goals)
    if issues:
        raise ValueError("; ".join(map(str, issues)))
    return {
        "input": sample["input"],
        "goals": goals,
        "meta": {
            "family": command_key,
            "category": category,
            "surface_template_id": sample.get(
                "surface_template_id", f"{command_key}:unknown"
            ),
            "goal_signature": goal_signature(goals),
            "entity_kinds": entity_kinds(goals),
            "slot_names": slot_names(goals),
        },
    }


def _signature_key(goals):
    return tuple(goal_signature(goals))


def _try_add_unique_sample(
    generator,
    command_key,
    category,
    dataset,
    seen_inputs,
    target_signature=None,
):
    """Genera una muestra y devuelve la razón por la que se aceptó o rechazó."""
    sample = _generate_specific_command(generator, command_key, category)
    if not sample:
        return "generation_error"
    try:
        sample = _enrich_sample(sample, command_key, category)
    except ValueError as exc:
        print(f"Etiqueta inválida en {command_key}: {exc}")
        return "invalid_label"

    if target_signature is not None and _signature_key(sample["goals"]) != target_signature:
        return "signature_mismatch"

    # La deduplicación se basa en el texto, no solo en el par texto/etiqueta.
    # Así se detecta también el caso peligroso de un input con dos labels.
    input_key = _normalized_input(sample["input"])
    goals_key = tuple(sample["goals"])
    if seen_inputs is not None and input_key in seen_inputs:
        if seen_inputs[input_key] != goals_key:
            return "label_conflict"
        return "duplicate"

    if seen_inputs is not None:
        seen_inputs[input_key] = goals_key
    dataset.append(sample)
    return "added"


def discover_family_signatures(generator, command_key, category):
    """Obtiene las firmas alcanzables sin acoplarlas a frases concretas."""
    variants = generator.enumerate_command_variants(
        command_key, category, include_invalid_combinations=True
    )
    # La enumeración usa valores deterministas y puede elegir por casualidad el
    # mismo origen/destino. La firma sigue siendo alcanzable con otros valores;
    # la generación aleatoria valida después cada instancia concreta.
    signatures = sorted({_signature_key(item["goals"]) for item in variants})
    if not signatures:
        raise ValueError(
            f"La familia {command_key}/{category} no produce firmas semánticas"
        )
    return signatures


def generate_balanced_dataset(
    generator,
    n_samples,
    person_ratio,
    seed=None,
    deduplicate=DEDUPLICATE,
    max_attempts_per_sample=MAX_ATTEMPTS_PER_SAMPLE,
):
    """
    Genera un dataset balanceado de comandos GPSR con estructura {input, goals}.

    Args:
        generator: instancia de CommandGenerator
        n_samples: número total de comandos a generar
        person_ratio: proporción de comandos de tipo 'people' (resto para 'objects')
        seed: semilla aleatoria para reproducibilidad
    """
    if seed is not None:
        random.seed(seed)

    if not 0.0 <= person_ratio <= 1.0:
        raise ValueError("person_ratio debe estar entre 0.0 y 1.0")
    if n_samples < 1:
        raise ValueError("n_samples debe ser mayor que cero")

    dataset = []
    seen_inputs = {} if deduplicate else None
    rejection_stats = Counter()

    # Obtener los tipos de comando por categoría (sin pesos)
    person_commands = [cmd for cmd, _ in generator.person_cmd_list]
    object_commands = [cmd for cmd, _ in generator.object_cmd_list]

    n_person = int(n_samples * person_ratio)
    n_object = n_samples - n_person

    def distribute_evenly(total, items):
        """Reparte una cuota preservando diferencias de como máximo una muestra."""
        if not items:
            return []
        base, remainder = divmod(total, len(items))
        return [base + int(index < remainder) for index in range(len(items))]

    category_commands = {
        "people": person_commands,
        "objects": object_commands,
    }
    category_targets = {"people": n_person, "objects": n_object}
    strata = []
    discovered_signatures = {}

    # Balance jerárquico: categoría -> familia -> firma. Una familia con siete
    # planes posibles recibe la misma cuota total que otra familia, y dentro de
    # ella esa cuota se reparte entre sus firmas alcanzables.
    for category, commands in category_commands.items():
        family_counts = distribute_evenly(category_targets[category], commands)
        print(
            f"Distribución por familia y firma de {category} "
            f"({category_targets[category]} muestras):"
        )
        for command_key, family_target in zip(commands, family_counts):
            signatures = discover_family_signatures(
                generator, command_key, category
            )
            discovered_signatures[(category, command_key)] = signatures
            signature_counts = distribute_evenly(family_target, signatures)
            print(
                f"  {command_key}: {family_target} "
                f"({len(signatures)} firmas)"
            )
            for signature, signature_target in zip(signatures, signature_counts):
                strata.append(
                    (command_key, category, signature, signature_target)
                )

    # Primero intenta respetar cada cuota. Si una familia agota sus variantes
    # únicas, el déficit se redistribuye entre las demás familias.
    actual_counts = Counter()
    active_fill_strata = set()
    for cmd_type, category, signature, requested in strata:
        added = 0
        consecutive_rejections = 0
        while added < requested and consecutive_rejections < max_attempts_per_sample:
            before = len(dataset)
            status = _try_add_unique_sample(
                generator,
                cmd_type,
                category,
                dataset,
                seen_inputs,
                target_signature=signature,
            )
            if status != "added":
                rejection_stats[status] += 1
            if len(dataset) > before:
                added += 1
                actual_counts[(category, cmd_type, signature)] += 1
                consecutive_rejections = 0
            else:
                consecutive_rejections += 1
            if added and added % 100 == 0:
                print(f"  Progreso {cmd_type}/{category}: {added}/{requested}")
        if added == requested:
            active_fill_strata.add((cmd_type, category, signature))

    fill_attempts = 0
    max_fill_attempts = max(n_samples, 1) * max_attempts_per_sample
    # Los déficits se rellenan dentro de la misma categoría para conservar
    # exactamente PERSON_RATIO incluso cuando una familia se satura.
    for fill_category, target in category_targets.items():
        fill_rejections = Counter()
        active_category_strata = {
            stratum for stratum in active_fill_strata if stratum[1] == fill_category
        }
        current = sum(
            count
            for (category, _, _), count in actual_counts.items()
            if category == fill_category
        )
        while (
            current < target
            and fill_attempts < max_fill_attempts
            and active_category_strata
        ):
            fill_attempts += 1
            # Elegir primero la familia menos representada y después su firma
            # menos representada mantiene el balance durante redistribuciones.
            family_totals = {
                command_key: sum(
                    count
                    for (cat, family, _), count in actual_counts.items()
                    if cat == fill_category and family == command_key
                )
                for command_key, _, _ in active_category_strata
            }
            minimum_family_count = min(family_totals.values())
            candidate_families = {
                family
                for family, count in family_totals.items()
                if count == minimum_family_count
            }
            candidate_strata = [
                stratum
                for stratum in active_category_strata
                if stratum[0] in candidate_families
            ]
            minimum_signature_count = min(
                actual_counts[(fill_category, command_key, signature)]
                for command_key, _, signature in candidate_strata
            )
            candidate_strata = [
                stratum
                for stratum in candidate_strata
                if actual_counts[(fill_category, stratum[0], stratum[2])]
                == minimum_signature_count
            ]
            cmd_type, category, signature = random.choice(candidate_strata)
            before = len(dataset)
            status = _try_add_unique_sample(
                generator,
                cmd_type,
                category,
                dataset,
                seen_inputs,
                target_signature=signature,
            )
            if status != "added":
                rejection_stats[status] += 1
                fill_rejections[(cmd_type, category, signature)] += 1
            if len(dataset) > before:
                current += 1
                actual_counts[(category, cmd_type, signature)] += 1
                fill_rejections[(cmd_type, category, signature)] = 0
            elif (
                fill_rejections[(cmd_type, category, signature)]
                >= max_attempts_per_sample
            ):
                active_category_strata.discard((cmd_type, category, signature))

    if len(dataset) != n_samples:
        raise RuntimeError(
            f"No se pudieron generar {n_samples} inputs únicos: "
            f"se obtuvieron {len(dataset)} después de {fill_attempts} reintentos "
            f"de redistribución. Rechazos={dict(rejection_stats)}"
        )

    print("Distribución real después de deduplicación y redistribución:")
    for category in category_commands:
        for cmd_type in category_commands[category]:
            signature_counts = {
                " -> ".join(signature): actual_counts[
                    (category, cmd_type, signature)
                ]
                for signature in discovered_signatures[(category, cmd_type)]
            }
            family_total = sum(signature_counts.values())
            print(
                f"  {category}/{cmd_type}: {family_total} "
                f"| firmas={signature_counts}"
            )
    print(f"Rechazos controlados: {dict(rejection_stats)}")

    # Barajar para mezclar personas y objetos
    random.shuffle(dataset)
    return dataset

def _generate_specific_command(generator, command_key, category):
    """
    Genera un comando específico forzando el tipo (command_key) y la categoría.
    Evita la selección aleatoria del comando principal.
    """
    # Guardar método original
    original_weighted_choice = generator._weighted_choice

    # Parche temporal para forzar el comando deseado
    def forced_weighted_choice(weighted_list):
        # Solo se llama al inicio de generate_command_start para elegir el comando base
        return command_key

    generator._weighted_choice = forced_weighted_choice

    try:
        # Generar con metas activadas
        result = generator.generate_command_start(cmd_category=category, return_goals=True)
        return result
    except Exception as e:
        print(f"Error generando {command_key}: {e}")
        return None
    finally:
        # Restaurar método original
        generator._weighted_choice = original_weighted_choice

def main():
    print("Cargando conocimiento desde:", DATA_DIR)
    knowledge = parse_data(DATA_DIR)
    # Las diferencias entre catálogos quedan visibles antes de crear ejemplos.
    catalog_issues = validate_catalogs(knowledge, JUSTINA_NAMES_FILE)
    print_catalog_report(catalog_issues)
    catalog_errors = [issue for issue in catalog_issues if issue.severity == "error"]
    if catalog_errors:
        raise ValueError("Errores de catálogo: " + "; ".join(map(str, catalog_errors)))
    generator = CommandGenerator(knowledge, debug=False)

    print(
        f"Iniciando generación de {NUM_SAMPLES} comandos "
        f"(proporción personas={PERSON_RATIO})..."
    )
    dataset = generate_balanced_dataset(
        generator,
        NUM_SAMPLES,
        PERSON_RATIO,
        seed=RANDOM_SEED,
        deduplicate=DEDUPLICATE,
        max_attempts_per_sample=MAX_ATTEMPTS_PER_SAMPLE,
    )

    # Se valida antes de escribir: un fallo no deja un JSONL parcial etiquetado
    # como si fuera apto para entrenamiento.
    clips_validator = None
    try:
        clips_validator = ClipsPlanValidator(CLIPS_RULES_FILE)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Validación CLIPS no disponible: {exc}")
    report = evaluate_dataset_rows(
        dataset,
        clips_validator=clips_validator,
        max_clips_samples=CLIPS_VALIDATION_SAMPLES,
    )
    if clips_validator is not None:
        clips_validator.close()
    print_evaluation_report(report, "Calidad del dataset generado")
    if report["totals"].get("invalid", 0):
        raise ValueError("El dataset contiene etiquetas inválidas")
    if report["totals"].get("clips_failed", 0):
        raise ValueError("Hay secuencias que CLIPS no puede planificar")

    # Guardar como JSONL
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for sample in dataset:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"\n✅ Dataset guardado en '{OUTPUT_FILE}' con {len(dataset)} muestras.")

    # Mostrar algunas estadísticas adicionales
    total_goals = sum(len(sample["goals"]) for sample in dataset)
    avg_goals = total_goals / len(dataset) if dataset else 0
    print(f"Promedio de goals por comando: {avg_goals:.2f}")

    category_counter = Counter(sample["meta"]["category"] for sample in dataset)

    print("\nDistribución por categoría de generación:")
    for cat, count in category_counter.items():
        pct = 100 * count / len(dataset)
        print(f"  {cat}: {count} ({pct:.1f}%)")

if __name__ == "__main__":
    # Elige el modo de ejecución
    ENUMERATE_MODE = False   # Cambia a False para generar dataset aleatorio

    knowledge = parse_data(DATA_DIR)

    if ENUMERATE_MODE:
        enumerate_and_save(knowledge, output_file="all_command_variants.jsonl")
    else:
        main()
