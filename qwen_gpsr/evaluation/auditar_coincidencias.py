"""Comprueba coincidencias de órdenes de desarrollo con el dataset completo."""
from qwen_gpsr.paths import REPORTS_DIR

import argparse
import hashlib
import importlib
import json
import re
from collections import defaultdict
from pathlib import Path


def leer_jsonl(ruta):
    with ruta.open(encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, 1):
            if not linea.strip():
                continue
            registro = json.loads(linea)
            if not isinstance(registro.get("input"), str) or not registro["input"].strip():
                raise ValueError(f"{ruta}, línea {numero}: input inválido")
            yield numero, registro


def limpieza_basica(texto):
    return " ".join(re.sub(r"[^\w\s]", " ", texto.casefold().replace("_", " ")).split())


def huella(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desarrollo", type=Path)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--normalizador", help="Función local con formato modulo:funcion")
    parser.add_argument("--salida", type=Path, default=REPORTS_DIR / "evaluation" / "auditoria_desarrollo.json")
    args = parser.parse_args()
    funciones = {"literal": lambda x: x, "limpieza_basica": limpieza_basica}
    if args.normalizador:
        modulo, funcion = args.normalizador.split(":", 1)
        funciones["normalizador_real"] = getattr(importlib.import_module(modulo), funcion)
    casos = list(leer_jsonl(args.desarrollo))
    ids = [c["id"] for _, c in casos]
    if len(ids) != len(set(ids)):
        parser.error("Hay identificadores duplicados en el conjunto de desarrollo.")
    indices = {nombre: defaultdict(list) for nombre in funciones}
    for _, caso in casos:
        for nombre, funcion in funciones.items():
            clave = funcion(caso["input"])
            if not isinstance(clave, str) or not clave.strip():
                raise ValueError(f"El normalizador {nombre} no devuelve texto válido.")
            indices[nombre][clave].append(caso["id"])
    coincidencias = {nombre: [] for nombre in funciones}
    total = 0
    for numero, fila in leer_jsonl(args.dataset):
        total += 1
        for nombre, funcion in funciones.items():
            clave = funcion(fila["input"])
            if not isinstance(clave, str) or not clave.strip():
                raise ValueError(f"El normalizador {nombre} falló en la línea {numero}.")
            for identificador in indices[nombre].get(clave, []):
                coincidencias[nombre].append({"id": identificador, "linea_dataset": numero})
    informe = {
        "desarrollo_sha256": huella(args.desarrollo),
        "dataset_sha256": huella(args.dataset),
        "casos_desarrollo": len(casos), "filas_dataset": total,
        "normalizador_real": args.normalizador,
        "estado_normalizador_real": "comprobado" if args.normalizador else "pendiente",
        "coincidencias": coincidencias,
        "ids_con_coincidencia": sorted({x["id"] for valores in coincidencias.values() for x in valores}),
        "alcance": "Igualdad literal y de transformaciones indicadas; no certifica independencia semántica ni novedad de plantilla.",
    }
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Revisadas {total} filas y {len(casos)} órdenes de desarrollo.")
    print(f"Casos con coincidencias: {len(informe['ids_con_coincidencia'])}")
    print(f"Informe: {args.salida}")
    if not args.normalizador:
        print("Pendiente: comparación con el normalizador real del sistema.")


if __name__ == "__main__":
    main()
