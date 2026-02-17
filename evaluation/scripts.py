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


# -------------
# GENERAL DATA
# -------------
qualities = []
lowest = {
    "api": None,
    "value": 1
}
highest = {
    "api": None,
    "value": 0
}

for json_path in OUTPUTS_PATH.glob("*.json"):
    with open(json_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    api_name = data["api-name"]
    quality = data["quality"]["normalized"]
    qualities.append(quality)

    if quality < lowest["value"]:
        lowest["api"] = api_name
        lowest["value"] = quality
    if quality > highest["value"]:
        highest["api"] = api_name
        highest["value"] = quality

print("Best: " + str(round(highest["value"] * 100, 2)) + "% (" + highest["api"] + ")")
print("Worst: " + str(round(lowest["value"] * 100, 2)) + "% (" + lowest["api"] + ")")
print("Average: " + str(round(np.average(qualities) * 100, 2)) + "%")


# --------------
# API SIZE BINS
# --------------
routes = []

for json_path in OUTPUTS_PATH.glob("*.json"):
    with open(json_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    nb_routes = data["structure"]["routes"]["total"]
    routes.append(nb_routes)

    quality = data["quality"]["normalized"]

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
qualities = []
colors = []
routes = []

for json_path in OUTPUTS_PATH.glob("*.json"):
    with open(json_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

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


# ------------------
# EVALUATIONS CHART
# ------------------
evaluations = {}

for json_path in OUTPUTS_PATH.glob("*.json"):
    with open(json_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    for entry in data:
        if "evaluate" in entry:
            if data[entry]["outcome"] == "fail":
                evaluations[entry] = evaluations.get(entry, 0) + 1

evaluations = sorted(evaluations.items(), key=lambda x: x[1])
ids, counts = zip(*evaluations)
ids = list(ids)
counts = list(counts)

plt.figure(figsize=(20, 12))
plt.barh(ids, counts, color="tab:orange")

plt.xlabel("Count of Failing Evaluations", fontweight="bold", fontsize=16, labelpad=20)
plt.ylabel("Evaluation ID", fontweight="bold", fontsize=16, labelpad=20)

ax = plt.gca()
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["bottom"].set_visible(False)
ax.set_axisbelow(True)
ax.grid(axis="x", linestyle="--")

plt.tight_layout()
plt.savefig(CHARTS_PATH / "chart-evaluation-count.pdf", format="pdf")
plt.close()


# ------------------------------
# API SIZE CATEGORY RECAP CHART
# ------------------------------
qualities = {}

for json_path in OUTPUTS_PATH.glob("*.json"):
    with open(json_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    nb_routes = data["structure"]["routes"]["total"]

    if nb_routes <= p5:
        category = "Micro"
    elif nb_routes <= p35:
        category = "Small"
    elif nb_routes <= p65:
        category = "Medium"
    elif nb_routes <= p95:
        category = "Large"
    else:
        category = "Very Large"

    if category not in qualities:
        qualities[category] = {"general": []}

    qualities[category]["general"].append(data["quality"]["normalized"])

    for evaluation in data["evaluation-groups"]:
        if evaluation not in qualities[category]:
            qualities[category][evaluation] = []

        qualities[category][evaluation].append(data["evaluation-groups"][evaluation]["pass"] / data["evaluation-groups"][evaluation]["total"])

for category in qualities:
    for evaluation in qualities[category]:
        qualities[category][evaluation] = np.mean(qualities[category][evaluation])

categories = ["Micro", "Small", "Medium", "Large", "Very Large"]
evaluations = ["general", "format", "oas-version", "metadata", "server", "descriptions", "examples"]

plt.figure(figsize=(20, 12))

for eval in evaluations:
    values = [qualities[cat][eval] for cat in categories]

    if eval == "general":
        line_width = 3.5
        z_order = 3
    else:
        line_width = 2
        z_order = 2

    plt.plot(categories, values, marker="o", linewidth=line_width, alpha=0.9, zorder=z_order)

plt.xlabel("API Size Category", fontweight="bold", fontsize=16, labelpad=20)
plt.ylabel("Quality", fontweight="bold", fontsize=16, labelpad=20)

ax = plt.gca()
ax.set_axisbelow(True)
ax.grid(axis="y", linestyle="--")

plt.legend(
    ["General", "Format", "OAS Version", "Metadata", "Server", "Descriptions", "Examples"],
    title="Evaluation Dimensions",
    title_fontsize=15,
    fontsize=14,
    loc="lower left"
)

plt.tight_layout()
plt.savefig(CHARTS_PATH / "chart-quality.pdf", format="pdf")
plt.close()