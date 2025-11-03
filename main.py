from QualityEvaluator import QualityEvaluator


def main():

    description = "Lists all global security advisories that match the specified parameters. If no other parameters are defined, the request will return only GitHub-reviewed advisories that are not malware. By default, all responses will exclude advisories for malware, because malware are not standard vulnerabilities. To list advisories for malware, you must include the type parameter in your request, with the value malware."

    evaluator = QualityEvaluator()

    description_quality = evaluator.evaluate_description_quality(description)
    print(description_quality)


if __name__ == "__main__":
    main()