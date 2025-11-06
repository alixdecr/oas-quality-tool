from QualityEvaluator import QualityEvaluator


def main():

    evaluator = QualityEvaluator()
    evaluator.setup_evaluation("inputs/openapi/amadeus-hotel.json")
    evaluator.execute()


if __name__ == "__main__":
    main()