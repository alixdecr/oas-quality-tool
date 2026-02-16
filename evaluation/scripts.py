import json
import matplotlib.pyplot as plt
import numpy as np
from collections import Counter
from matplotlib.patches import Patch
from pathlib import Path


# ------
# PATHS
# ------
OUTPUTS_PATH = Path(__file__).resolve().parent.parent / "outputs"
EVALUATION_PATH = Path(__file__).resolve().parent
CHARTS_PATH = EVALUATION_PATH / "charts"
CHARTS_PATH.mkdir(parents=True, exist_ok=True)


# --------------
# API SIZE BINS
# --------------
routes = []

for json_path in OUTPUTS_PATH.glob("*.json"):
    with open(json_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    nb_routes = data["structure"]["routes"]["total"]
    routes.append(nb_routes)

routes = sorted(routes)

# create the 5 percentile bins
p5 = round(np.percentile(routes, 5))
p35 = round(np.percentile(routes, 35))
p65 = round(np.percentile(routes, 65))
p95 = round(np.percentile(routes, 95))

print(routes)
print(f"Micro: <= {p5}")
print(f"Small: <= {p35}")
print(f"Medium: <= {p65}")
print(f"Large: <= {p95}")
print(f"Very Large: > {p95}")


# ---------------------
# QUALITY SCATTER PLOT
# ---------------------
index = 0
api_ids = []
qualities = []
colors = []
routes = []

for json_path in OUTPUTS_PATH.glob("*.json"):
    with open(json_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    index += 1
    nb_routes = data["structure"]["routes"]["total"]
    quality = data["quality"]["normalized"]
    color = "tab:blue"

    if nb_routes <= p5:
        color = "tab:blue"
    elif nb_routes <= p35:
        color = "tab:green"
    elif nb_routes <= p65:
        color = "tab:olive"
    elif nb_routes <= p95:
        color = "tab:orange"
    else:
        color = "tab:red"

    api_ids.append(index)
    qualities.append(quality)
    colors.append(color)
    routes.append(nb_routes)

points = list(zip(routes, qualities))
counts = Counter(points)
sizes = [counts[(xi, yi)] * 100 for xi, yi in points]

plt.figure(figsize=(20, 12))
plt.scatter(routes, qualities, c=colors, s=sizes)

plt.xscale("log")
plt.xlabel("API Size", fontweight="bold", fontsize=16, labelpad=20)
plt.ylabel("Quality", fontweight="bold", fontsize=16, labelpad=20)

legend_elements = [
    Patch(facecolor="tab:blue", label=f"Micro (≤ {p5} routes)"),
    Patch(facecolor="tab:green", label=f"Small ({p5}-{p35} routes)"),
    Patch(facecolor="tab:olive", label=f"Medium ({p35 + 1}-{p65} routes)"),
    Patch(facecolor="tab:orange", label=f"Large ({p65 + 1}-{p95} routes)"),
    Patch(facecolor="tab:red", label=f"Very large (> {p95} routes)"),
]

plt.legend(
    handles=legend_elements,
    title="API Size Based on Number of Routes",
    title_fontsize=15,
    fontsize=14,
    loc="upper right"
)

plt.tight_layout()
plt.savefig(CHARTS_PATH / "chart-quality-scatter-plot.pdf", format="pdf")
plt.close()