"""Curvas de pérdida desde un estado de Trainer o un archivo trainer_state.json."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter


def graficar_perdidas(estado, salida="curva_perdida_qwen", desde=1000):
    """Recibe un dict con log_history y best_model_checkpoint; devuelve PNG y PDF.

    salida es una ruta base sin extensión. No carga ni entrena el modelo.
    """
    historial = estado["log_history"]
    ent = [(r["step"], r["loss"]) for r in historial if "loss" in r]
    val = [(r["step"], r["eval_loss"]) for r in historial if "eval_loss" in r]
    if not ent or not val:
        raise ValueError("El archivo debe contener pérdidas de entrenamiento y validación.")

    # Utilizar el checkpoint seleccionado por Trainer, no inferirlo de la imagen.
    checkpoint = estado.get("best_model_checkpoint")
    if not checkpoint:
        raise ValueError("El estado no registra un checkpoint seleccionado.")
    paso = int(Path(checkpoint).name.rsplit("-", 1)[1])
    perdida = next((y for x, y in val if x == paso), None)
    if perdida is None:
        raise ValueError("El historial no contiene la evaluación del checkpoint seleccionado.")
    # Incluir el mejor paso incluso en entrenamientos más cortos.
    desde = min(desde, paso)
    detalle = [(x, y) for x, y in val if x >= desde]
    if len(detalle) < 2:
        desde = val[0][0]
        detalle = val
    estilo = {"font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False}
    with plt.rc_context(estilo):
        fig, (ax, zoom) = plt.subplots(2, 1, figsize=(10, 7), layout="constrained")
        ax.plot(*zip(*ent), color="#1764a0", label="Entrenamiento", linewidth=1.5)
        ax.plot(*zip(*val), color="#d65f00", label="Validación", linewidth=1.8)
        ax.set_title("Evolución de la pérdida durante el entrenamiento")
        ax.legend(loc="upper right")
        zoom.plot(*zip(*detalle), color="#d65f00", marker=".", linewidth=1.5)
        zoom.set_title(f"Detalle de validación desde el paso {desde:,}".replace(",", " "))
        zoom.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
        zoom.ticklabel_format(axis="y", style="plain", useOffset=False)
        zoom.margins(y=0.25)

        for eje in (ax, zoom):
            eje.axvline(paso, color="#454545", linestyle="--", linewidth=1)
            eje.scatter(paso, perdida, color="#454545", s=45, zorder=5)
            eje.set_xlabel("Pasos de actualización")
            eje.set_ylabel("Pérdida")
            eje.grid(alpha=0.25)
        zoom.annotate(f"Checkpoint seleccionado: {paso}\nPérdida: {perdida:.10f}",
                      xy=(paso, perdida), xycoords="data", xytext=(0.62, 0.82),
                      textcoords="axes fraction", fontsize=10,
                      arrowprops={"arrowstyle": "->", "color": "#454545"},
                      bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": "#cccccc"})

        salida = Path(salida)
        salida.parent.mkdir(parents=True, exist_ok=True)
        rutas = []
        try:
            for extension in ("png", "pdf"):
                ruta = Path(f"{salida}.{extension}")
                fig.savefig(ruta, dpi=300)
                rutas.append(ruta)
        finally:
            plt.close(fig)
        return rutas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("estado", type=Path, help="trainer_state.json del último checkpoint")
    parser.add_argument("--salida", type=Path, default=Path("curva_perdida_qwen"),
                        help="Ruta base de salida, sin extensión")
    parser.add_argument("--desde", type=int, default=1000, help="Inicio del detalle ampliado")
    args = parser.parse_args()
    estado = json.loads(args.estado.read_text(encoding="utf-8"))
    try:
        rutas = graficar_perdidas(estado, args.salida, args.desde)
    except ValueError as exc:
        parser.error(str(exc))
    for ruta in rutas:
        print(f"Guardado: {ruta}")


if __name__ == "__main__":
    main()
