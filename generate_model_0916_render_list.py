import csv
from pathlib import Path


metadata_path = Path("/Users/mlty/Downloads/metadata_cg.csv")
previous_model_names = (
    "model_0630",
    "model_0707",
    "model_0721",
    "model_0729",
    "model_0805",
    "model_0812",
    "model_0819",
)
new_model_names = (
    "model_0826",
    "model_0902",
    "model_0908",
    "model_0916",
    "model_1015",
)
jiaguyi_model_names = (
    "model_jiaguyi_1",
    "model_jiaguyi_2",
    "model_jiaguyi_3",
    "model_jiaguyi_4",
)
model_names = previous_model_names + new_model_names + jiaguyi_model_names

sha256_by_model = {model_name: set() for model_name in model_names}
with metadata_path.open(encoding="utf-8", newline="") as handle:
    for row in csv.DictReader(handle):
        if row["cond_rendered"].strip().lower() != "true":
            continue

        for model_name in model_names:
            if row["local_path"].startswith(f"raw/{model_name}/"):
                sha256_by_model[model_name].add(row["sha256"])
                break

for model_name, sha256_values in sha256_by_model.items():
    output_path = Path(f"{model_name}_render_sha256_cond_rendered.txt")
    output_path.write_text("\n".join(sorted(sha256_values)) + "\n", encoding="utf-8")
    print(f"model={model_name} assets={len(sha256_values)} output={output_path}")

combined_sha256_values = set().union(
    *(sha256_by_model[model_name] for model_name in previous_model_names)
)
combined_output_path = Path("models_0630_to_0819_render_sha256_cond_rendered.txt")
combined_output_path.write_text(
    "\n".join(sorted(combined_sha256_values)) + "\n",
    encoding="utf-8",
)
print(f"combined_assets={len(combined_sha256_values)} output={combined_output_path}")

new_combined_sha256_values = set().union(
    *(sha256_by_model[model_name] for model_name in new_model_names)
)
new_combined_output_path = Path("models_0826_to_1015_render_sha256_cond_rendered.txt")
new_combined_output_path.write_text(
    "\n".join(sorted(new_combined_sha256_values)) + "\n",
    encoding="utf-8",
)
print(
    f"new_combined_assets={len(new_combined_sha256_values)} "
    f"output={new_combined_output_path}"
)

jiaguyi_combined_sha256_values = set().union(
    *(sha256_by_model[model_name] for model_name in jiaguyi_model_names)
)
jiaguyi_combined_output_path = Path(
    "models_jiaguyi_1_to_4_render_sha256_cond_rendered.txt"
)
jiaguyi_combined_output_path.write_text(
    "\n".join(sorted(jiaguyi_combined_sha256_values)) + "\n",
    encoding="utf-8",
)
print(
    f"jiaguyi_combined_assets={len(jiaguyi_combined_sha256_values)} "
    f"output={jiaguyi_combined_output_path}"
)