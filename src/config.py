import json


CONFIG_PATH = "inputs/config.json"

with open(CONFIG_PATH, "r") as file:
    CONFIG = json.load(file)

def get_config():
    return CONFIG