import json, sys
from pathlib import Path

from config import get_config
from QualityEvaluator import QualityEvaluator

def main():
    """
    Main entry point for the OAS Quality Tool.

    This script iterates through all OpenAPI JSON files located in the input directory,
    runs the QualityEvaluator pipeline on each, and exports the results to the 
    configured output directory.
    """

    # ---------------------------------------------------------
    # 1. Load Configuration
    # ---------------------------------------------------------
    try:
        config = get_config()
    except Exception as e:
        print(f"[CRITICAL] Cannot load configuration: {e}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 2. Setup Directories (using Pathlib)
    # ---------------------------------------------------------
    try:
        # .resolve() ensures we work with absolute paths
        in_dir = Path(config["in-path"]).resolve()
        out_dir = Path(config["out-path"]).resolve()
    except KeyError as e:
        print(f"[CRITICAL] Missing required configuration key: {e}")
        sys.exit(1)

    # Ensure output directory exists (mkdir -p)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[CRITICAL] Could not create output directory: {e}")
        sys.exit(1)

    # Verify input directory existence
    if not in_dir.exists():
        print(f"[ERROR] Input directory does not exist: {in_dir}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 3. Initialize Evaluator
    # ---------------------------------------------------------
    # Inject configuration once via the constructor
    evaluator = QualityEvaluator(configuration=config)

    # ---------------------------------------------------------
    # 4. Retrieve Files
    # ---------------------------------------------------------
    # Filter for .json files only to avoid processing system files (like .DS_Store)
    files = sorted([f for f in in_dir.iterdir() if f.is_file() and f.suffix == ".json"])
    
    nb_total = len(files)
    if nb_total == 0:
        print(f"[INFO] No .json files found in {in_dir}")
        return

    print(f"[INFO] Starting evaluation of {nb_total} files...\n")

    # ---------------------------------------------------------
    # 5. Processing Loop
    # ---------------------------------------------------------
    for index, file_path in enumerate(files, 1):
        try:
            # Clean extraction of the API name (e.g., "my-api.v1.json" -> "my-api.v1")
            api_name = file_path.stem 

            # Setup & Execution
            evaluator.setup_evaluation_local(file_path)
            report = evaluator.execute()

            # Retrieve score (default to N/A if calculation failed)
            standard_quality = "{:.2f}".format(round(report.get("quality", {}).get("standard", 0) * 100, 2)) + "%"
            normalized_quality = "{:.2f}".format(round(report.get("quality", {}).get("normalized", 0) * 100, 2)) + "%"

            # Export Report
            out_file = out_dir / f"evaluation-{api_name}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=4)

            # Console Logging
            print(f"[{index}/{nb_total}] Score: {standard_quality} (standard) | {normalized_quality} (normalized) -> {api_name}")

        except Exception as e:
            # Batch processing resilience: If one file fails, log it and continue to the next.
            print(f"[{index}/{nb_total}] ERROR processing {file_path.name}: {e}")

    print(f"\n[DONE] Reports generated in: {out_dir}")

if __name__ == "__main__":
    main()