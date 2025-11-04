from QualityEvaluator import QualityEvaluator


def main():

    evaluator = QualityEvaluator("inputs/github.json")
    evaluator.execute()


if __name__ == "__main__":
    main()