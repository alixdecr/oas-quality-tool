import json


class Utils:


    def load_json(path):

        try:
            with open(path, "r", encoding="utf-8-sig") as file:
                return json.load(file)

        except:
            return None