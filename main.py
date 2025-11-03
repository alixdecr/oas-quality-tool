from QualityEvaluator import QualityEvaluator


def main():

    evaluator = QualityEvaluator("inputs/amadeus-hotel.json")
    evaluator.execute()


if __name__ == "__main__":
    main()