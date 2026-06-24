# OAS Quality Tool: An Automated Framework for OpenAPI Specification Auditing

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License](https://img.shields.io/badge/license-CC%20BY%20NC%20ND%204.0-green.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

**A rigorous, rule-based static analysis tool designed to evaluate, grade, and improve the quality of RESTful API definitions.**

---

## Citation

If you use this tool in your research or find it useful in your work, please cite our paper:

Decrop, A., Vandeloise, M., Heymans, P. and Perrouin, G., 2026. OASQuali: Automated Quality Analysis of OpenAPI Specifications. In Proceedings of the 26th International Conference on Web Engineering, ICWE 2026.

```bibtex
@inproceedings{decrop2026oasquali,
    title={OASQuali: Automated Quality Analysis of OpenAPI Specifications},
    author={Decrop, Alix and Vandeloise, Mikel and Heymans, Patrick and Perrouin, Gilles},
    booktitle={Proceedings of the 26th International Conference on Web Engineering, ICWE 2026},
    year={2026}
}
```

## Abstract

The **OAS Quality Tool** is a Python-based framework developed to automate the assessment of **OpenAPI Specifications (OAS)**. In the context of API governance and service-oriented architectures, the quality of interface documentation is paramount for developer experience (DX), system interoperability, and maintainability.

This tool goes beyond simple syntactic validation. It performs a comprehensive **qualitative audit** based on industry best practices, assessing specifications across four dimensions: structural integrity, metadata compliance, documentation completeness, and functional reachability. It produces granular, machine-readable JSON reports for each API, culminating in a global quality score.

---

## Key Capabilities

The framework evaluates specifications using a modular rule engine:

### 1. Structural & Syntactic Integrity
* **Schema Validation:** Strict validation against official OAS 2.0 (Swagger) and OAS 3.x schemas using `openapi-spec-validator`.
* **JSON Syntax Analysis:** Detection of malformed structures and encoding issues with precise error localization (line/column).
* **Reference Resolution:** Automated resolution of internal and external `$ref` pointers using `jsonref`.

### 2. Metadata & Governance
* **Semantic Versioning (SemVer):** Enforcement of `Major.Minor.Patch` versioning formats via Regex.
* **Descriptive Adequacy:** Heuristic analysis of API titles and descriptions (length constraints, detection of default template values).
* **Legal & Contact Compliance:** Verification of License validity and Maintainer contact details (Email/URL pattern validation).

### 3. Documentation Quality
* **Route Coverage:** Analysis of meaningful descriptions across all HTTP operations (GET, POST, PUT, DELETE, etc.).
* **Parameter Documentation:** Validation of input parameters for existence and descriptive quality.
* **Response Clarity:** Verification of response object descriptions and status codes.

### 4. Functional & Implementation Analysis
* **Server Reachability:** Dynamic connectivity checks (HTTP ping with timeout) to verify environment availability.
* **Security Protocol:** Strict enforcement of HTTPS schemes for production endpoints.
* **Example Density:** Calculation of coverage ratios for parameter examples and response media-type examples.

---

## Methodology & Scoring

The tool employs a **Quality Evaluator Engine** (`QualityEvaluator.py`) that ingests an OAS file and applies a set of configurable rules.

### The Scoring Algorithm
The final quality score (0-100%) is calculated as a ratio of **passed rules** versus **total applicable rules**.
* **Fail-Fast Mechanism:** Critical errors (e.g., invalid JSON syntax, missing root paths) trigger an immediate halt of the evaluation for that specific file, resulting in a 0% score.
* **Weighted Evaluation:** The tool distinguishes between structural failures (blocking) and quality warnings (non-blocking).

### Configuration
The tool is driven by a configuration file (`inputs/config.json`) allowing researchers and API managers to define strictness thresholds:
* **`min-words`**: Minimum word count for descriptions.
* **`min-percentage`**: Minimum required coverage for examples (e.g., 0.8 for 80%).
* **`keywords`**: Required vocabulary in descriptions (optional).

---

## Directory Structure

The project adheres to a modular architecture separating logic, configuration, and data.

```text
oas-quality-tool/
├── inputs/
│   ├── config.json       # Configuration thresholds and paths
│   └── oas/              # Directory for input .json OpenAPI files
├── outputs/              # Generated JSON quality reports
├── src/
│   ├── main.py           # Entry point script (Orchestrator)
│   ├── config.py         # Configuration loader (Singleton pattern)
│   └── QualityEvaluator.py # Core analysis logic & Rule definitions
├── requirements.txt      # Project dependencies
└── README.md             # Project documentation
```

---

## Installation

### Prerequisites
* **Python 3.8** or higher
* `pip` package manager

### Setup
It is recommended to use a virtual environment to isolate project dependencies and avoid conflicts with system-wide packages.

```bash
# 1. Clone the repository
git clone [https://github.com/your-username/oas-quality-tool.git](https://github.com/your-username/oas-quality-tool.git)
cd oas-quality-tool

# 2. Create a virtual environment
# This creates a hidden folder '.venv' containing a standalone Python environment
python3 -m venv .venv

# 3. Activate the environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows (PowerShell):
# .venv\Scripts\Activate.ps1
# On Windows (Command Prompt):
# .venv\Scripts\activate.bat

# 4. Install dependencies
# This reads the 'requirements.txt' file and installs the necessary libraries
pip install -r requirements.txt
```

---

## Usage

1.  **Prepare Input Data:**
    Place your OpenAPI JSON files in the `inputs/oas/` directory.

2.  **Configure (Optional):**
    Adjust thresholds in `inputs/config.json` if necessary (sensible defaults are provided).

3.  **Run the Audit:**
    Execute the main script from the project root:

    ```bash
    python src/main.py
    ```

4.  **Analyze Results:**
    The tool will log progress in the console. Detailed JSON reports for each API are generated in the `outputs/` directory.

    *Example Console Output:*
    ```text
    [INFO] Starting evaluation of 5 files...
    [1/5] Score: 85% -> payment-api.v1
    [2/5] Score: 42% -> legacy-service.v2
    [3/5] ERROR processing broken-api.json: invalid JSON syntax
    ...
    [DONE] Reports generated in: /.../oas-quality-tool/outputs
    ```

---

## Output Format

The generated reports provide granular details useful for debugging and statistical analysis.

```json
{
    "api-name": "payment-api.v1",
    "timestamp": "2023-10-27T14:30:00",
    "quality": "84%",
    "overall": {
        "total": 25,
        "pass": 21,
        "fail": 4
    },
    "evaluate-oas-version": {
        "outcome": "pass",
        "version": "openapi-3.0.1"
    },
    "evaluate-route-descriptions": {
        "outcome": "fail",
        "reason": "insufficient route descriptions",
        "percentage": 0.5,
        "min-percentage": 1.0,
        "invalid-details": {
            "description too short": 5
        }
    }
}
```

---

## Contribution

Contributions are welcome to enhance the rule set or support additional API specification formats (e.g., YAML support, AsyncAPI). Please ensure any pull request maintains the current **type hinting standards** (`typing` module) and adheres to the existing architectural patterns.

## License

This project is distributed under the **MIT License**. See the `LICENSE` file for more information.

## Citation

If you use this tool in your research, please cite it as follows:

> Alix Decrop and Mikel Vandeloise, "OAS Quality Tool: A Framework for Automated API Governance," 2025, GitHub Repository.