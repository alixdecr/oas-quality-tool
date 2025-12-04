import json, sys
from pathlib import Path
from typing import Any, Dict

THIS_FILE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_FILE_DIR.parent
CONFIG_FILE_PATH = PROJECT_ROOT / "inputs" / "config.json"
_CONFIG_CACHE: Dict[str, Any] = {}

def get_config() -> Dict[str, Any]:
    """
    Safely loads the configuration from the JSON file and caches it in memory.

    This function implements the Singleton pattern via a global cache variable.
    It strictly validates the existence of the file and the integrity of the JSON
    syntax before returning the data.

    Returns:
        Dict[str, Any]: A dictionary containing the configuration data.

    Raises:
        SystemExit: If the configuration file is missing, unreadable, or contains 
                    invalid JSON syntax. The program will terminate with exit code 1.
    """
    global _CONFIG_CACHE

    if _CONFIG_CACHE:
        return _CONFIG_CACHE

    if not CONFIG_FILE_PATH.exists():
        print(f"\n[FATAL ERROR] Configuration file not found.")
        print(f"  -> Expected path: {CONFIG_FILE_PATH}")
        print(f"  -> Please ensure the 'inputs' directory exists at the project root.\n")
        sys.exit(1)

    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as file:
            _CONFIG_CACHE = json.load(file)
            return _CONFIG_CACHE

    except json.JSONDecodeError as e:
        print(f"\n[FATAL ERROR] The config.json file contains invalid syntax.")
        print(f"  -> Details: {e}")
        print(f"  -> Please validate your JSON structure (commas, brackets, quotes).\n")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n[FATAL ERROR] An unexpected error occurred while reading the configuration.")
        print(f"  -> Error: {e}\n")
        sys.exit(1)