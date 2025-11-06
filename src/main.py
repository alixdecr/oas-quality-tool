import json, os, requests
from QualityEvaluator import QualityEvaluator


def main():

    # create output folder if it does not exist yet
    dir_path = os.path.dirname("outputs/")
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    evaluator = QualityEvaluator()

    api_list = requests.get("https://api.apis.guru/v2/list.json").json()
    nb_total = len(api_list)
    nb_current = 0

    for api in api_list:

        nb_current += 1

        api_id = api.replace(" ", "-").replace(".", "-").replace(":", "-")

        if os.path.exists(f"outputs/{api_id}.json"):
            print(f"({nb_current}/{nb_total}) DONE {api}")
            continue

        preferred_version = api_list[api]["preferred"]
        oas_url = api_list[api]["versions"][preferred_version]["swaggerUrl"]

        oas_file = requests.get(oas_url).json()

        evaluator.setup_evaluation_online(api, oas_file)
        evaluator.execute()

        quality = evaluator.evaluations["quality"]

        print(f"({nb_current}/{nb_total}) {quality} {api}")

        file_name = f"{api_id}.json"
        with open(f"outputs/{file_name}", "w") as file:
            json.dump(evaluator.evaluations, file, indent=4)


if __name__ == "__main__":
    main()