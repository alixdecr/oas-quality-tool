import json, os
from config import get_config
from QualityEvaluator import QualityEvaluator


config = get_config()


def main():

    in_path = config["in-path"]
    # create output folder if it does not exist yet
    out_path = config["out-path"]
    out_path = os.path.dirname(f"{out_path}/")
    if out_path:
        os.makedirs(out_path, exist_ok=True)

    evaluator = QualityEvaluator()

    files = os.listdir(in_path)
    files.sort()

    nb_total = len(files)
    nb_current = 0

    for file_name in files:
        file_path = os.path.join(in_path, file_name)

        nb_current += 1
        api_name = file_name.replace(".json", "")

        evaluator.setup_evaluation_local(file_path)
        evaluator.execute()

        quality = evaluator.evaluations["quality"]

        out_name = f"evaluation-{api_name}.json"
        with open(f"outputs/{out_name}", "w") as file:
            json.dump(evaluator.evaluations, file, indent=4)

        print(f"({nb_current}/{nb_total}) {quality} {api_name}")


if __name__ == "__main__":
    main()