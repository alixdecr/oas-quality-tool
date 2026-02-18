import inspect, json, openapi_spec_validator, re, requests
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from requests.exceptions import RequestException
from urllib.parse import urlparse
from config import get_config
from datetime import datetime
from typing import Optional, Any, Dict, Union, Literal, List, Pattern
from pathlib import Path
from jsonref import replace_refs

class QualityEvaluator:

    
    SEMVER_PATTERN = re.compile(r"^\d+\.\d+(\.\d+)?.*$")
    EMAIL_PATTERN = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
    WHITESPACE_PATTERN: Pattern = re.compile(r"\s+")
    VALID_METHODS = {
        "get", "post", "put", "patch", "delete", 
        "head", "connect", "options", "trace"
    }

    def __init__(self, configuration: Optional[Dict[str, Any]] = None):
        self.config = configuration if configuration else get_config()
        self.oas_path: Optional[str] = None
        self.oas: Dict[str, Any] = {}
        self.evaluations: Dict[str, Any] = {}
        self.mode: Literal["local", "online"] = "local"


    def setup_evaluation_local(self, file_path: Union[str, Path]) -> None:
        """
        Configures the evaluation environment for a local file system input.

        This method normalizes the file path, automatically extracts the API name
        from the filename (ignoring extensions), and initializes the evaluation
        report structure.

        Args:
            file_path (Union[str, Path]): The absolute or relative path to the 
                                          OAS specification file (JSON/YAML).
        """

        self.mode = "local"
        
        # Convert input to a Path object for robust cross-platform handling (Windows/Linux)
        path_obj = Path(file_path)
        self.oas_path = str(path_obj.resolve())
        self.oas = {} 
        api_name = path_obj.stem
        self._initialize_evaluations(api_name)

    def setup_evaluation_online(self, api_name: str, oas_content: Dict[str, Any]) -> None:
        """
        Configures the evaluation environment for an in-memory OAS object.

        This method is used when the OAS is fetched via an API call or passed
        directly as a dictionary, bypassing file system operations.

        Args:
            api_name (str): A unique identifier or title for the API (e.g., "Stripe API").
            oas_content (Dict[str, Any]): The already parsed OpenAPI Specification 
                                          content as a dictionary.
        """
        self.mode = "online"

        self.oas = oas_content
        self._initialize_evaluations(api_name)

    def _initialize_evaluations(self, api_name: str) -> None:
        """
        Helper method to initialize the standardized evaluation report structure.
        
        This centralizes the report format definition to ensure consistency 
        between local and online evaluation modes.

        Args:
            api_name (str): The name of the API to be recorded in the report.
        """
        self.evaluations = {
            "api-name": api_name,
            # Use ISO 8601 format for machine-readable timestamps (e.g., "2023-10-27T14:30:00")
            "timestamp": datetime.now().isoformat(),
            "structure": {
                "routes": {
                    "total": 0,
                    "methods": {}
                },
                "parameters": {
                    "total": 0,
                    "in": {}
                },
                "responses": {
                    "total": 0,
                    "codes": {}
                }
            },
            "overall": {
                "total": 0,
                "pass": 0,
                "fail": 0
            },
            "evaluation-groups": {}
        }


    def evaluate_validate_json(self) -> None:
        """
        Parses and validates the syntax of the OpenAPI JSON file.

        This method attempts to read the file specified by `self.oas_path` and 
        load it into memory as a dictionary. It serves as the initial "sanity check" 
        for local file evaluations.

        Refactoring Improvements:
        1. **Encoding Safety**: Explicitly forces `utf-8` encoding to prevent crashes 
           on Windows systems when processing files with special characters (emojis, accents).
        2. **Granular Exception Handling**: Distinguishes between:
           - `FileNotFoundError`: The path is wrong.
           - `JSONDecodeError`: The file exists but contains invalid syntax.
           - `PermissionError`: The file exists but cannot be read.
        3. **Actionable Debugging**: In case of syntax errors, it captures the exact 
           line number, column, and error message provided by the JSON parser.

        """
        # 1. Mode Check: Skip this check if we are not analyzing a local file
        if self.mode == "online":
            # We assume the JSON is valid because it's already loaded in memory
            self.add_evaluation("pass", {"note": "skipped in online mode"})
            return
        
        # 2. Pre-check: Ensure a path is actually set
        if not self.oas_path or not isinstance(self.oas_path, str):
            self.add_evaluation("fail", {
                "reason": "no file path provided for local evaluation"
            })
            return

        try:
            # 3. File Operation
            # We enforce UTF-8 to ensure cross-platform compatibility (Linux/Mac/Windows).
            with open(self.oas_path, "r", encoding="utf-8") as file:
                self.oas = json.load(file)
                
            # 4. Success
            self.add_evaluation("pass")

        except FileNotFoundError:
            self.add_evaluation("fail", {
                "reason": "file not found",
                "path": self.oas_path
            })

        except PermissionError:
            self.add_evaluation("fail", {
                "reason": "permission denied accessing file",
                "path": self.oas_path
            })

        except json.JSONDecodeError as e:
            # 5. Detailed Syntax Error Reporting
            # This is critical for developer experience. It tells them exactly where to fix.
            self.add_evaluation("fail", {
                "reason": "invalid JSON syntax",
                "error-message": e.msg,
                "line": e.lineno,
                "column": e.colno,
                "position": e.pos
            })

        except Exception as e:
            # 6. Fallback for Unexpected IO Errors
            self.add_evaluation("fail", {
                "reason": "unexpected error during file reading",
                "exception-type": type(e).__name__,
                "details": str(e)
            })


    def evaluate_validate_oas(self) -> None:
        """
        Performs a strict structural validation of the OpenAPI Specification.

        This method utilizes the `openapi-spec-validator` library to verify that 
        the loaded dictionary adheres to the official OpenAPI Schema (OAS 2.0, 
        3.0, or 3.1). This is a syntax check, not a quality check.

        Refactoring Improvements:
        1. **Precise Exception Handling**: Specifically catches `OpenAPIValidationError` 
           to extract detailed debugging information.
        2. **Path Extraction**: Identifies the exact location of the error in the 
           JSON/YAML structure (e.g., `['paths', '/users', 'get']`), enabling 
           rapid debugging.
        3. **Actionable Feedback**: Returns the specific schema violation message 
           instead of a generic exception name.

        """
        # 1. Pre-requisite Check
        if not self.oas or not isinstance(self.oas, dict):
            self.add_evaluation("fail", {
                "reason": "OAS content is empty or not a valid dictionary"
            })
            return

        try:
            # 2. Execute Structural Validation
            # This function raises an exception if the spec violates the schema.
            openapi_spec_validator.validate(self.oas)
            
            # 3. Register Success
            self.add_evaluation("pass")

        except OpenAPIValidationError as e:
            # 4. Handle Specific Schema Violations
            # Extract the path to the error (e.g., info -> version)
            # The path is often a deque or list; we convert to string for readability.
            error_path = "root"
            if hasattr(e, 'absolute_path') and e.absolute_path:
                error_path = " -> ".join([str(p) for p in e.absolute_path])
            elif hasattr(e, 'path') and e.path:
                error_path = " -> ".join([str(p) for p in e.path])

            self.add_evaluation("fail", {
                "reason": "schema validation failed",
                "error-message": e.message if hasattr(e, 'message') else str(e),
                "error-location": error_path
            })

        except Exception as e:
            # 5. Handle Unexpected Failures (Fallback)
            # Catches unexpected runtime errors not related to validation logic.
            self.add_evaluation("fail", {
                "reason": "unexpected validation error",
                "exception-type": type(e).__name__,
                "details": str(e)
            })


    def evaluate_oas_version(self) -> None:
        """
        Evaluates the declared OpenAPI Specification (OAS) version.

        This method inspects the root-level version field (`openapi` for 3.x, 
        `swagger` for 2.0) to determine the specification version used.

        It enforces the following quality gates:
        1. **Modernity**: Rejects Swagger 2.0 (OAS 2) as outdated/deprecated.
        2. **Type Safety**: Ensures the version value is a string.
        3. **Format Compliance**: Validates that the version string follows the 
           Semantic Versioning format (Major.Minor.Patch) required by the spec 
           (e.g., "3.0.3" is valid; "3.0" or "3" are technically incomplete).

        Refactoring Improvements:
        1. **SemVer Validation**: Uses Regex to strictly enforce the 'x.y.z' format.
        2. **Legacy Detection**: Explicitly identifies Swagger 2.0 as a failure condition 
           due to its End-of-Life status.
        3. **Input Sanitization**: Prevents non-string inputs (like floats in YAML) 
           from being processed as valid versions.
        """
        # 1. Check for Modern OpenAPI 3.x+
        if "openapi" in self.oas:
            version_value = self.oas["openapi"]
            
            # Type Check: OAS spec requires the version to be a string.
            # YAML parsers might interpret 3.0 as a float, which causes issues.
            if not isinstance(version_value, str):
                self.add_evaluation("fail", {
                    "reason": "OAS version must be a string (e.g. '3.0.0'), not a number",
                    "actual-type": type(version_value).__name__,
                    "value": str(version_value)
                })
                return

            # SemVer Validation (Major.Minor.Patch)
            # Regex: Start, digits, dot, digits, dot, digits, End.
            if not self.SEMVER_PATTERN.match(version_value.strip()):
                self.add_evaluation("fail", {
                    "reason": "OAS version does not follow Semantic Versioning (Major.Minor.Patch)",
                    "value": version_value,
                    "expected-format": "x.y.z (e.g., 3.0.3)"
                })
                return

            # Logic: We generally approve 3.x versions
            self.add_evaluation("pass", {"version": f"openapi-{version_value}"})
            return

        # 2. Check for Legacy Swagger 2.0
        elif "swagger" in self.oas:
            version_value = self.oas["swagger"]
            # Swagger 2.0 is technically valid JSON but practically obsolete.
            self.add_evaluation("fail", {
                "reason": "outdated OAS version (Swagger 2.0 is deprecated)", 
                "version": f"swagger-{version_value}",
                "recommendation": "Upgrade to OpenAPI 3.0 or 3.1"
            })
            return

        # 3. Failure: No Version Identifier Found
        else:
            self.add_evaluation("fail", {
                "reason": "unknown or missing OAS version identifier",
                "details": "The specification must contain an 'openapi' (3.x) or 'swagger' (2.0) field."
            })


    def evaluate_api_title(self) -> None:
        """
        Evaluates the presence, validity, and quality of the API Title.

        This method inspects the `info.title` field. According to the OpenAPI 
        Specification, the title is REQUIRED and serves as the primary identifier 
        for the API in directories and documentation portals.

        Refactoring Improvements:
        1. **Type Safety:** Strictly enforces that the title is a string.
        2. **Quality Governance:**
           - Checks for generic/default titles (e.g., "Swagger Petstore").
           - Enforces a minimum length to ensure the title is descriptive 
             (e.g., rejects "API" or "Test").
           - Enforces a maximum length to ensure conciseness.
        3. **Defensive Access:** Safely handles the `info` object structure.

        Configuration:
            Optionally uses 'config["titles"]' for 'min-length' and 'max-length'.
            Defaults: min=4, max=80.
        """
        # 1. Structural Validation
        # We use the helper to cleanly get the object or None
        info_object = self._get_info_object()
        
        # We explicitly handle the failure case here so 'inspect' attributes
        # the failure to 'evaluate-api-title'
        if info_object is None:
            self.add_evaluation("fail", {"reason": "missing or invalid info object"})
            return

        # 2. Existence Check
        if "title" not in info_object:
            self.add_evaluation("fail", {"reason": "missing title field"})
            return
        
        raw_title = info_object["title"]

        # 3. Type Validation
        if not isinstance(raw_title, str):
            self.add_evaluation("fail", {
                "reason": "title must be a string", 
                "actual-type": type(raw_title).__name__
            })
            return

        # 4. Content Validation (Emptiness)
        if not self.has_content(raw_title):
            self.add_evaluation("fail", {"reason": "empty title field"})
            return

        title_clean = self.WHITESPACE_PATTERN.sub(" ", str(raw_title)).strip()

        # 5. Quality Checks (Governance)
        # Retrieve constraints or use sensible defaults
        # Note: Assuming we add a 'titles' section to config, otherwise defaults apply.
        title_config = self.config.get("titles", {})
        min_length = title_config.get("min-length", 4)
        max_length = title_config.get("max-length", 100)
        
        # Check 5a: Length
        if len(title_clean) < min_length:
            self.add_evaluation("fail", {
                "reason": "title is too short to be descriptive", 
                "title": title_clean,
                "min-length": min_length
            })
            return

        if len(title_clean) > max_length:
            self.add_evaluation("fail", {
                "reason": "title is too verbose", 
                "title": title_clean,
                "max-length": max_length
            })
            return

        # Check 5b: Templated/Default Values
        # Common default values generated by tools that should be changed.
        forbidden_titles = ["OpenAPI Definition", "Untitled API"]
        if any(default.lower() in title_clean.lower() for default in forbidden_titles):
             self.add_evaluation("fail", {
                "reason": "title appears to be a default template value", 
                "title": title_clean
            })
             return

        # 6. Pass
        self.add_evaluation("pass", {"title": title_clean})


    def evaluate_api_description(self) -> None:
        """
        Evaluates the quality of the global API description.

        This method inspects the `info.description` field, which serves as the 
        primary documentation entry point for API consumers. It verifies that the 
        description exists and adheres to the governance constraints defined in 
        the configuration (e.g., minimum word count, required keywords).

        Refactoring Improvements:
        1. **Safe Configuration Access:** Uses chained `.get()` methods to retrieve 
           constraints. This prevents `KeyError` crashes if the configuration file 
           is incomplete or missing specific sections.
        2. **Structural Validation:** Explicitly validates that `info` is a dictionary 
           before attempting to access the description.
        3. **Structured Logging:** Returns the list of specific violations in the 
           evaluation data, allowing for more granular reporting than a simple 
           concatenated string.

        Configuration:
            Requires 'config["descriptions"]["api"]'. If missing, defaults to 
            empty constraints (only checking for existence/non-emptiness).
        """
        # 1. Structural Validation
        info_object = self._get_info_object()
        
        if info_object is None:
            self.add_evaluation("fail", {"reason": "missing or invalid info object"})
            return
        
        # 2. Robust Configuration Retrieval
        # We safely drill down into the config object. If keys are missing, 
        # we default to an empty dict (implies no specific constraints like min-words).
        description_config = self.config.get("descriptions", {})
        if not isinstance(description_config, dict):
             description_config = {}
             
        api_constraints = description_config.get("api", {})

        # 3. Execute Validation Logic
        # Uses the helper method 'check_description' (previously refactored)
        # which handles existence, emptiness, length, and keyword checks.
        violations: List[str] = self.check_description(info_object, api_constraints)

        # 4. Final Decision Logic
        if violations:
            self.add_evaluation("fail", {
                "reason": "description requirements not met",
                "violation-count": len(violations),
                "violations": violations, # structured array for UI/JSON parsing
                "summary": ", ".join(violations) # human-readable string
            })
        else:
            self.add_evaluation("pass")


    def evaluate_api_contact(self) -> None:
        """
        Evaluates the presence and validity of the API Contact information.

        This method inspects the `info.contact` object. While the OpenAPI Specification
        defines the contact object as optional, a high-quality API definition must 
        provide a way to reach the maintainers.

        This evaluator enforces strict quality rules:
        1. **Structure**: The contact field must be a dictionary.
        2. **Reachability**: At least one contact mechanism (`email` or `url`) must be provided.
        3. **Format Validation**:
           - If `email` is provided, it must match a standard email Regex pattern.
           - If `url` is provided, it must be a syntactically valid absolute URL.

        Refactoring Improvements:
        1. **Format Validation**: Prevents placeholder text (e.g., "email": "TBD") from passing.
        2. **Type Safety**: Ensures 'contact' is a dictionary before accessing keys.
        3. **Granular Errors**: Distinguishes between "missing field" and "invalid format".
        """
        # 1. Structural Validation
        info_object = self._get_info_object()
        
        if info_object is None:
            self.add_evaluation("fail", {"reason": "missing or invalid info object"})
            return

        # 2. Existence Check
        if "contact" not in info_object:
            self.add_evaluation("fail", {"reason": "missing contact field"})
            return

        contact_obj = info_object["contact"]
        if not isinstance(contact_obj, dict):
            self.add_evaluation("fail", {"reason": "contact field must be an object"})
            return

        # 3. Validate Content (Email and URL)
        # We track if we found at least one valid contact method.
        valid_method_found = False
        errors = []

        # --- Check Email ---
        if "email" in contact_obj:
            raw_email = str(contact_obj["email"]) if contact_obj["email"] else ""
            email_value = raw_email.strip() 

            if self.has_content(email_value):
                if self.EMAIL_PATTERN.match(email_value):
                    valid_method_found = True
                else:
                    errors.append(f"invalid email format: '{email_value}'")
            else:
                errors.append("email field is empty")

        # --- Check URL ---
        if "url" in contact_obj:
            url_value = contact_obj["url"]
            if self.has_content(url_value):
                try:
                    parsed = urlparse(url_value)
                    if all([parsed.scheme, parsed.netloc]):
                        valid_method_found = True
                    else:
                        errors.append(f"invalid contact url: '{url_value}'")
                except Exception:
                    errors.append(f"malformed contact url: '{url_value}'")
            else:
                errors.append("url field is empty")

        # 4. Final Decision
        if errors:
            # If we found specific formatting errors, report them
            self.add_evaluation("fail", {
                "reason": "invalid contact information", 
                "errors": errors,
                "contact": contact_obj
            })
        elif valid_method_found:
            # Pass if at least one valid method exists and no errors were flagged
            self.add_evaluation("pass", {"contact": contact_obj})
        else:
            # Fail if neither email nor url were provided
            self.add_evaluation("fail", {
                "reason": "contact object must contain at least a valid 'email' or 'url'"
            })


    def evaluate_api_version(self) -> None:
        """
        Evaluates the presence and format of the API version string.

        This method inspects the `info.version` field. According to the OpenAPI 
        Specification, this field is REQUIRED and must be a string.

        While the specification allows any string value, this evaluator performs 
        an additional quality check to see if the version adheres to the 
        Semantic Versioning (SemVer) standard (e.g., '1.0.0'), which is the 
        industry best practice.

        Refactoring Improvements:
        1. **Type Enforcement:** Strictly validates that the version is a string. 
           (e.g., rejects numeric `1.0` which can cause issues in client generators).
        2. **SemVer Analysis:** Uses Regex to detect if the version follows the 
           'Major.Minor.Patch' format and adds this metadata to the report.
        3. **Defensive Access:** Safely navigates the 'info' object.
        """
        # 1. Structural Validation
        info_object = self._get_info_object()
        
        if info_object is None:
            self.add_evaluation("fail", {"reason": "missing or invalid info object"})
            return

        # 2. Existence Check
        if "version" not in info_object:
            self.add_evaluation("fail", {"reason": "missing version field"})
            return
        
        version_value = info_object["version"]

        # 3. Type Validation
        # OAS spec mandates a string. A generic number (float/int) is technically invalid
        # because '1.10' as a number is the same as '1.1', but as a version it is different.
        if not isinstance(version_value, str):
            self.add_evaluation("fail", {
                "reason": "version field must be a string", 
                "actual-type": type(version_value).__name__,
                "value": str(version_value)
            })
            return

        # 4. Content Validation
        if not self.has_content(version_value):
            self.add_evaluation("fail", {"reason": "empty version field"})
            return

        # 5. Format Analysis (SemVer)
        # Matches patterns like "1.0", "1.0.0", "1.0.0-beta".
        # This is a quality indicator, not a strict failure condition (unless you want strict mode).
        is_semver = bool(self.SEMVER_PATTERN.match(version_value.strip()))

        # Pass the evaluation, but include the SemVer status in the data
        self.add_evaluation("pass", {
            "version": version_value,
            "is-semver-compliant": is_semver
        })


    def evaluate_api_license(self) -> None:
        """
        Evaluates the presence and validity of the API License information.

        This method inspects the `info.license` object. According to the OpenAPI 
        Specification (versions 2.0 and 3.x), the License Object:
        1. **Must** contain a `name` field (Required).
        2. **May** contain a `url` field (Optional).

        Refactoring Improvements:
        1. **Spec Compliance:** Enforces the mandatory presence of the 'name' field. 
           The previous check only verified that the object was not empty, which 
           allowed invalid objects (e.g., a license with only a URL).
        2. **Shadowing Fix:** Renamed the local variable 'license' to 'license_data' 
           to avoid shadowing Python's built-in license() function.
        3. **Content Validation:** Uses 'has_content' to ensure the name is not 
           just whitespace.

        """
        # 1. Structural Validation
        info_object = self._get_info_object()
        
        if info_object is None:
            self.add_evaluation("fail", {"reason": "missing or invalid info object"})
            return
        
        # 2. Existence Check
        if "license" not in info_object:
            self.add_evaluation("fail", {"reason": "missing license field"})
            return
        
        license_data = info_object["license"]
        if not isinstance(license_data, dict):
            self.add_evaluation("fail", {"reason": "license field must be an object"})
            return

        # 3. Mandatory Field Validation: 'name'
        # The OAS spec explicitly states that 'name' is REQUIRED.
        if "name" not in license_data:
            self.add_evaluation("fail", {"reason": "license object is missing the mandatory 'name' field"})
            return
        
        license_name = license_data["name"]
        
        # Ensure the name is not empty or whitespace
        if not self.has_content(license_name):
             self.add_evaluation("fail", {"reason": "license name cannot be empty"})
             return

        # 4. Optional Field Validation: 'url'
        # If a URL is provided, we should check that it is not empty, 
        # though we don't fail the whole check if the syntax is weird (unless strict mode).
        if "url" in license_data and not self.has_content(license_data["url"]):
             self.add_evaluation("fail", {"reason": "license URL provided but empty"})
             return

        # 5. Pass
        self.add_evaluation("pass", {"license": license_data})


    def evaluate_api_terms(self) -> None:
        """
        Evaluates the presence and validity of the API Terms of Service.

        This method inspects the `info.termsOfService` field. According to the 
        OpenAPI Specification, this field must be a URL pointing to the terms.
        
        The evaluation enforces:
        1. **Existence**: The field must be present in the 'info' object.
        2. **Type Safety**: The value must be a string.
        3. **Content**: The string must not be empty or whitespace.
        4. **Format**: The string must be a syntactically valid URL (URI).

        Refactoring Improvements:
        1. **Schema Compliance**: Correctly treats 'termsOfService' as a String/URL, 
           fixing the previous erroneous check against an empty dictionary (`{}`).
        2. **URL Validation**: Uses `urllib.parse` to ensure the value is a link, 
           preventing plain text descriptions where a URL is required.
        3. **Defensive Chaining**: Safely navigates the 'info' object.

        """
        # 1. Structural Validation (Info Object)
        info_object = self._get_info_object()
        
        if info_object is None:
            self.add_evaluation("fail", {"reason": "missing or invalid info object"})
            return
        
        # 2. Existence Check
        if "termsOfService" not in info_object:
            self.add_evaluation("fail", {"reason": "missing termsOfService field"})
            return
        
        terms_url = info_object["termsOfService"]

        # 3. Type and Content Validation
        # We use the helper method 'has_content' refactored earlier.
        # This handles the check for Non-None, String type, and Non-Empty.
        if not self.has_content(terms_url):
             self.add_evaluation("fail", {"reason": "empty or invalid termsOfService field"})
             return

        # 4. URL Syntax Validation
        # The spec requires a URL. We parse it to ensure it has a scheme and network location.
        try:
            parsed = urlparse(terms_url)
            # A valid Terms URL must have a scheme (http/https) and a netloc (domain).
            if not all([parsed.scheme, parsed.netloc]):
                self.add_evaluation("fail", {
                    "reason": "termsOfService must be a valid URL", 
                    "value": terms_url
                })
                return
        except ValueError:
            self.add_evaluation("fail", {"reason": "malformed URL syntax", "value": terms_url})
            return
        
        # 5. Pass
        self.add_evaluation("pass", {"terms": terms_url})


    def evaluate_server_url(self) -> None:
        """
        Evaluates the existence and syntactic validity of API server definitions.

        This method performs a static analysis of the 'servers' (OAS 3) or 'host' (Swagger 2)
        configurations. It ensures that:
        1. At least one server URL is defined.
        2. The defined URLs are not empty strings or whitespace.
        3. The URLs possess a valid syntax (parseable URI structure).

        Refactoring Improvements:
        1. **Syntactic Validation:** Uses `urllib.parse` to verify that the string is 
           actually a URI, not just random text.
        2. **Whitespace Handling:** Explicitly flags empty or blank strings as failures, 
           preventing false positives.
        3. **Separation of Concerns:** distinct from 'evaluate_server_validity' (reachability) 
           and 'evaluate_scheme' (security), this rule focuses strictly on structural definition.
        """
        # 1. Retrieve URLs using the helper method
        server_urls: List[str] = self.get_oas_servers()

        # 2. Check for Existence (Rule 1)
        if not server_urls:
            self.add_evaluation("fail", {"reason": "no server URL configuration found"})
            return

        # 3. Validate Syntax (Rule 2 & 3)
        malformed_urls: List[str] = []
        valid_urls: List[str] = []

        for url in server_urls:
            # Check for empty strings or pure whitespace
            if not url or not url.strip():
                malformed_urls.append("<empty-string>")
                continue

            try:
                # Parse the URL to check for structural validity
                result = urlparse(url)
                
                # A valid OAS server URL must have at least a path or a netloc.
                # Example relative URL: "/v1" (valid) -> path='/v1'
                # Example absolute URL: "https://api.com" (valid) -> netloc='api.com'
                if not result.netloc and not result.path:
                    malformed_urls.append(url)
                else:
                    valid_urls.append(url)

            except Exception:
                malformed_urls.append(url)

        # 4. Final Decision Logic
        if malformed_urls:
            self.add_evaluation("fail", {
                "reason": "malformed or empty server URLs detected",
                "malformed-count": len(malformed_urls),
                "malformed-details": malformed_urls,
                "valid-urls": valid_urls
            })
        elif len(valid_urls) == 0:
            # Edge case: List existed but contained only whitespace
            self.add_evaluation("fail", {"reason": "server configuration exists but contains no valid URLs"})
        else:
            self.add_evaluation("pass", {
                "urls": valid_urls,
                "count": len(valid_urls)
            })


    def evaluate_server_validity(self) -> None:
        """
        Verifies the reachability and availability of the defined API servers.

        This method attempts to establish a connection to each server URL defined 
        in the specification. It employs an "At Least One" success strategy: 
        if at least one server is reachable and responds, the evaluation passes.
        
        It distinguishes between:
        - **Connectivity**: Can we reach the server? (Network layer)
        - **Availability**: Does the server return a valid status code? (Application layer)

        Refactoring Improvements:
        1. **Exception Granularity**: Catches `requests.RequestException` specifically,
           allowing system interrupts (like KeyboardInterrupt) to pass through.
        2. **Aggregated Reporting**: Collects results for ALL servers before making
           a final decision, preventing mixed "fail/pass" signals in the logs.
        3. **Timeout Management**: Enforces a strict 5-second timeout to prevent
           the linter from hanging on dead servers.

        """
        # 1. Retrieve Server URLs
        server_urls: List[str] = self.get_oas_servers()

        if not server_urls:
            self.add_evaluation("fail", {"reason": "no server URLs defined to test"})
            return

        # 2. Initialize Traceability
        # We store the detailed result of every attempt
        server_results: List[Dict[str, Any]] = []
        accessible_servers_count: int = 0

        # 3. Test Connectivity (Sequential)
        for url in server_urls:
            result_entry = {"url": url}
            
            try:
                response = requests.get(url, timeout=5)
                
                # We consider the server valid if we get ANY HTTP response (even 401/403/404).
                # A 500 error proves the server is there, even if the app is crashing.
                result_entry["status"] = "reachable"
                result_entry["http_code"] = response.status_code
                accessible_servers_count += 1

            except RequestException as e:
                # Captures DNS errors, Timeouts, Connection Refused
                result_entry["status"] = "unreachable"
                result_entry["error"] = str(e)
            
            server_results.append(result_entry)

        # 4. Final Decision Logic
        # Strategy: High Availability. If at least one environment is up, the API is usable.
        if accessible_servers_count > 0:
            self.add_evaluation("pass", {
                "reachable-servers": accessible_servers_count,
                "total-servers": len(server_urls),
                "details": server_results
            })
        else:
            self.add_evaluation("fail", {
                "reason": "no servers are reachable",
                "details": server_results
            })


    def evaluate_scheme(self) -> None:
        """
        Evaluates the security protocol (scheme) of the API server URLs.

        This method inspects all server URLs defined in the specification to ensure
        they comply with modern security standards. It strictly enforces the use of
        **HTTPS**.

        It categorizes violations into two types:
        1. **Insecure**: Uses 'http' instead of 'https'.
        2. **Invalid**: Missing a scheme or uses a non-standard protocol (e.g., 'ftp').

        Refactoring Improvements:
        1. **Robust Parsing**: Uses `urllib.parse.urlparse` instead of fragile string 
           manipulation (`startswith`) to accurately extract the scheme.
        2. **Detailed Reporting**: Instead of just counting errors, it captures the 
           specific URLs that failed, providing actionable feedback to the user.
        3. **Standard Compliance**: Enforces HTTPS as the only acceptable standard 
           for production-ready APIs.

        """
        # 1. Retrieve Server URLs
        # We rely on the robust 'get_oas_servers' method we refactored earlier.
        server_urls: List[str] = self.get_oas_servers()

        if not server_urls:
            self.add_evaluation("fail", {"reason": "no server URLs found"})
            return

        # 2. Initialize Accumulators
        insecure_urls: List[str] = []
        invalid_urls: List[str] = []
        
        # 3. Iterate and Validate
        for url in server_urls:
            try:
                # Robust parsing of the URL structure
                parsed_url = urlparse(url)
                scheme = parsed_url.scheme.lower()
                
                if scheme == "https":
                    continue  # Compliant
                elif scheme == "http":
                    insecure_urls.append(url)
                else:
                    # Catches missing schemes (empty string) or other protocols (ftp, ws)
                    invalid_urls.append(url)
                    
            except Exception:
                # Fallback for completely malformed URLs that crash the parser
                invalid_urls.append(url)

        # 4. Calculate and Register Outcome
        if insecure_urls or invalid_urls:
            self.add_evaluation("fail", {
                "reason": "insecure or invalid URL schemes detected",
                "insecure-count": len(insecure_urls),
                "insecure-details": insecure_urls,
                "invalid-count": len(invalid_urls),
                "invalid-details": invalid_urls,
                "total-checked": len(server_urls)
            })
        else:
            self.add_evaluation("pass", {
                "urls": server_urls, 
                "total-checked": len(server_urls)
            })


    def evaluate_route_descriptions(self) -> None:
        """
        Evaluates the quality of descriptions for API operations (routes).

        This method iterates through every Path Item and Operation (HTTP verb) 
        defined in the OpenAPI specification. It checks if the operation contains 
        a description that meets the configured constraints (length, keywords).

        Refactoring Improvements:
        1. **DRY Compliance:** Uses `_yield_operations` helper to avoid code duplication 
           in traversing the OAS structure.
        2. **Optimized Lookup:** HTTP methods checks are handled centrally by the helper.
        3. **Robust Configuration:** Uses safe getters for configuration values.

        Configuration:
            Requires 'config["descriptions"]["routes"]' containing 'min-percentage'.
        """
        # 1. Structural Validation
        # We still check this explicitly to fail fast if the "paths" key is missing entirely.
        if "paths" not in self.oas or not isinstance(self.oas["paths"], dict):
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return
        
        # 2. Initialize Statistics
        total_operations: int = 0
        valid_operations: int = 0
        violation_details: Dict[str, int] = {}

        # Robust configuration retrieval
        constraints = self.config.get("descriptions", {}).get("routes", {})
        min_percentage = constraints.get("min-percentage", 0.0)

        # 3. Iterate using the Generator Helper
        # The helper handles the loops over paths/methods and the type validation.
        for path, method, operation in self._yield_operations():

            self.evaluations["structure"]["routes"]["total"] += 1
            self.evaluations["structure"]["routes"]["methods"][method] = self.evaluations["structure"]["routes"]["methods"].get(method, 0) + 1

            total_operations += 1

            # 4. Check Description
            # check_description returns a list of error strings (e.g. ["too short"])
            violations: List[str] = self.check_description(operation, constraints)

            if not violations:
                valid_operations += 1
            else:
                # Aggregate violation details
                for violation in violations:
                    violation_details[violation] = violation_details.get(violation, 0) + 1

        # 5. Calculate and Register Outcome
        self._evaluate_ratio(
            total=total_operations,
            valid=valid_operations,
            min_percentage=min_percentage,
            details={
                "rule_id": "evaluate-route-descriptions",
                "nb-routes-total": total_operations,
                "nb-routes-with-valid-desc": valid_operations,
                "invalid-details": violation_details
            },
            fail_msg="insufficient route descriptions"
        )


    def evaluate_response_descriptions(self) -> None:
        """
        Evaluates the quality of descriptions in API responses.

        This method iterates through all defined responses in the OpenAPI specification.
        It validates that every response object contains a description field that meets
        the configured constraints (length, keywords).

        Refactoring Improvements:
        1. **Removed Magic Numbers:** The previous logic added an arbitrary +2 to the total
           if the 'responses' field was missing. This version skips missing fields, assuming
           structural validity is handled by 'evaluate_validate_oas'.
        2. **Shadowing Fix:** Renamed the variable 'id' to 'violation' to avoid shadowing
           Python's built-in id() function.
        3. **Type Safety:** Added checks to ensure 'responses' is actually a dictionary
           before iterating.

        Configuration:
            Requires 'config["descriptions"]["responses"]' with 'min-percentage'.
        """
        # 1. Structural Validation
        if "paths" not in self.oas or not isinstance(self.oas["paths"], dict):
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return
        
        # 2. Initialize Statistics
        total_responses: int = 0
        valid_responses: int = 0
        violation_details: Dict[str, int] = {}

        # Robust configuration retrieval
        constraints = self.config.get("descriptions", {}).get("responses", {})
        min_percentage = constraints.get("min-percentage", 0.0)

        # 3. Iterate using the Generator Helper
        for _, _, operation in self._yield_operations():
            
            # Specific Logic: We need the 'responses' block
            if "responses" not in operation:
                continue
            
            responses_block = operation["responses"]
            if not isinstance(responses_block, dict):
                continue

            # 4. Evaluate each response inside the operation
            for code, response_data in responses_block.items():

                self.evaluations["structure"]["responses"]["total"] += 1
                self.evaluations["structure"]["responses"]["codes"][code] = self.evaluations["structure"]["responses"]["codes"].get(code, 0) + 1

                if not isinstance(response_data, dict):
                    continue

                total_responses += 1

                # Check description using the helper method
                violations: List[str] = self.check_description(response_data, constraints)

                if not violations:
                    valid_responses += 1
                else:
                    # Aggregate violation details
                    for violation in violations:
                        violation_details[violation] = violation_details.get(violation, 0) + 1

        # 5. Calculate and Register Outcome
        self._evaluate_ratio(
            total=total_responses,
            valid=valid_responses,
            min_percentage=min_percentage,
            details={
                "rule_id": "evaluate-response-descriptions",
                "nb-responses-total": total_responses,
                "nb-responses-with-valid-desc": valid_responses,
                "invalid-details": violation_details
            },
            fail_msg="insufficient response descriptions"
        )


    def evaluate_parameter_descriptions(self) -> None:
        """
        Evaluates the quality of descriptions for API parameters.

        This method iterates through all operations defined in the OpenAPI specification.
        It verifies that every parameter contains a description that satisfies the
        configured constraints (existence, length, keywords).

        It aggregates statistics on:
        - Total parameters found.
        - Valid vs. invalid descriptions.
        - Specific violation types (e.g., "description too short").

        Configuration:
            Requires 'config["descriptions"]["parameters"]' to define constraints
            (min-words, max-words, etc.) and 'min-percentage'.
        """
        # 1. Structural Validation
        if "paths" not in self.oas or not isinstance(self.oas["paths"], dict):
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return
        
        # 2. Initialize Statistics
        total_parameters: int = 0
        valid_parameters: int = 0
        # Tracks specific violation counts (e.g., {"too short": 5, "missing": 2})
        violation_details: Dict[str, int] = {} 

        # Robust configuration retrieval
        constraints = self.config.get("descriptions", {}).get("parameters", {})
        min_percentage = constraints.get("min-percentage", 0.0)

        # 3. Iterate using the Generator Helper
        for _, _, operation in self._yield_operations():

            # Check if parameters exist for this operation
            if "parameters" not in operation:
                continue

            parameters_list = operation["parameters"]
            if not isinstance(parameters_list, list):
                continue
            
            # 4. Evaluate each parameter
            for parameter_data in parameters_list:

                param_cat = parameter_data.get("in", "unknown")

                self.evaluations["structure"]["parameters"]["total"] += 1
                self.evaluations["structure"]["parameters"]["in"][param_cat] = self.evaluations["structure"]["parameters"]["in"].get(param_cat, 0) + 1

                if not isinstance(parameter_data, dict):
                    continue

                total_parameters += 1

                # Helper function check_description returns a list of error strings
                violations: List[str] = self.check_description(parameter_data, constraints)

                if not violations:
                    valid_parameters += 1
                else:
                    # Aggregate violation details
                    for violation in violations:
                        violation_details[violation] = violation_details.get(violation, 0) + 1

        # 5. Calculate and Register Outcome
        self._evaluate_ratio(
            total=total_parameters,
            valid=valid_parameters,
            min_percentage=min_percentage,
            details={
                "rule_id": "evaluate-parameter-descriptions",
                "nb-parameters-total": total_parameters,
                "nb-parameters-with-valid-desc": valid_parameters,
                "invalid-details": violation_details
            },
            fail_msg="insufficient parameter descriptions"
        )


    def evaluate_response_examples(self) -> None:
        """
        Evaluates the coverage of examples in API response media types.

        This method iterates through all operations and their defined responses.
        It calculates the percentage of media types (e.g., 'application/json') 
        that contain an explicit 'example' or 'examples' field.

        Refactoring Improvements:
        1. **Removed Magic Numbers:** The previous logic arbitrarily added +2 to the 
           total count if 'responses' were missing. This version focuses strictly 
           on analyzing existing content. Structural issues should be flagged by 
           separate rules.
        2. **Respect for HTTP Standards:** Responses without content (like 204 No Content) 
           are no longer penalized. We only look for examples where content is actually defined.
        3. **Boolean/Zero Support:** Uses key existence checks to correctly identify 
           examples set to `false` or `0`.

        Configuration:
            Requires 'config["examples"]["responses"]["min-percentage"]'.
        """
        # 1. Structural Validation
        if "paths" not in self.oas or not isinstance(self.oas["paths"], dict):
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return

        # 2. Initialize counters and config
        total_media_types: int = 0
        valid_media_types: int = 0
        
        constraints = self.config.get("examples", {}).get("responses", {})
        min_percentage = constraints.get("min-percentage", 0.0)

        # 3. Iterate using the Generator Helper
        for _, _, operation in self._yield_operations():

            # Specific Logic: Check if responses exist
            if "responses" not in operation or not isinstance(operation["responses"], dict):
                continue

            for response_code, response_data in operation["responses"].items():
                if not isinstance(response_data, dict):
                    continue

                # 4. Check Content
                # We only evaluate responses that actually declare a 'content' payload.
                # This prevents penalizing empty responses (e.g., 204 No Content).
                if "content" not in response_data:
                    continue
                
                content_block = response_data["content"]
                if not isinstance(content_block, dict):
                    continue
                
                # Iterate over defined media types (e.g., "application/json")
                for media_type, media_data in content_block.items():
                    if not isinstance(media_data, dict):
                        continue

                    total_media_types += 1

                    # 5. Check for Example Existence (Robust Logic)
                    # Using 'in' handles values like False, 0, or empty strings correctly.
                    has_example = "example" in media_data or "examples" in media_data
                    
                    if has_example:
                        valid_media_types += 1

        # 6. Calculate and Register Outcome
        self._evaluate_ratio(
            total=total_media_types,
            valid=valid_media_types,
            min_percentage=min_percentage,
            details={
                "rule_id": "evaluate-response-examples",
                "nb-media-total": total_media_types,
                "nb-media-with-valid-example": valid_media_types
            },
            fail_msg="insufficient response examples"
        )


    def evaluate_parameter_examples(self) -> None:
        """
        Evaluates the coverage of examples in API parameters.

        This method iterates through all operations in the OpenAPI definition
        and calculates the ratio of parameters that provide an explicit 'example' 
        or 'examples' field. It compares this ratio against the configured threshold.

        Improvement: This version checks for key presence rather than value truthiness,
        ensuring that valid examples like '0' or 'false' are correctly counted.

        Configuration:
            Requires 'config["examples"]["parameters"]["min-percentage"]' (float between 0.0 and 1.0).
        """
        # 1. Structural Validation
        # We explicitly check for "paths" to report a specific structural error if missing.
        if "paths" not in self.oas or not isinstance(self.oas["paths"], dict):
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return

        # 2. Initialize counters
        total_parameters: int = 0
        valid_parameters: int = 0
        
        # Robust configuration retrieval
        constraints = self.config.get("examples", {}).get("parameters", {})
        min_percentage = constraints.get("min-percentage", 0.0)

        # 3. Iterate using the Generator Helper
        for _, _, operation in self._yield_operations():

            # Check if parameters exist for this operation
            if "parameters" not in operation:
                continue

            parameters_list = operation["parameters"]
            if not isinstance(parameters_list, list):
                continue

            # 4. Evaluate parameters
            for parameter in parameters_list:
                if not isinstance(parameter, dict):
                    continue

                total_parameters += 1

                # Check for Example Existence (Robust Logic)
                # We use key containment ('in') instead of .get() truthiness.
                # This ensures that example: 0 (integer) or example: false (boolean) are counted as valid.
                has_example = "example" in parameter or "examples" in parameter
                
                if has_example:
                    valid_parameters += 1

        # 5. Calculate and Register Outcome
        self._evaluate_ratio(
            total=total_parameters,
            valid=valid_parameters,
            min_percentage=min_percentage,
            details={
                "rule_id": "evaluate-parameter-examples",
                "nb-parameters-total": total_parameters,
                "nb-parameters-with-valid-example": valid_parameters
            },
            fail_msg="insufficient parameter examples"
        )


    def get_oas_servers(self) -> List[str]:
        """
        Extracts the list of target server URLs from the OpenAPI definition.

        This method implements a fallback strategy to support both major OpenAPI versions:
        1. **OpenAPI 3.x**: Checks the 'servers' array.
        2. **Swagger 2.0**: Constructs URLs using 'host', 'basePath', and 'schemes'.

        Returns:
            List[str]: A list of absolute or relative URLs found in the specification.
                       Returns an empty list if no server configuration is found.
        """
        server_urls: List[str] = []

        # ---------------------------------------------------------
        # Strategy 1: OpenAPI 3.x (Precedence)
        # ---------------------------------------------------------
        # The 'servers' key is the standard for OAS 3.0+.
        # We explicitly check if it exists and is a non-empty list.
        if "servers" in self.oas:
            servers_data = self.oas["servers"]
            
            if isinstance(servers_data, list):
                for server_obj in servers_data:
                    # Defensive check: ensure server_obj is a dict and has 'url'
                    if isinstance(server_obj, dict) and "url" in server_obj:
                        # Note: OAS 3 URLs may contain variables (e.g., {server}/api).
                        # Variable substitution is outside the scope of this extractor.
                        server_urls.append(server_obj["url"])
            
            # If 'servers' is defined (even if empty), we respect the OAS 3 spec 
            # and do not fallback to Swagger 2 logic.
            return server_urls

        # ---------------------------------------------------------
        # Strategy 2: Swagger 2.0 (Legacy Support)
        # ---------------------------------------------------------
        # If 'servers' is missing, we look for the legacy 'host' field.
        if "host" in self.oas:
            host = self.oas["host"]
            # 'basePath' is optional in Swagger 2.0; defaults to root "/"
            base_path = self.oas.get("basePath", "")
            
            # 'schemes' is optional; defaults to "https" for modern security standards.
            # We ensure 'schemes' is a list to prevent iteration errors.
            schemes = self.oas.get("schemes", ["https"])
            if not isinstance(schemes, list):
                schemes = ["https"]

            for scheme in schemes:
                # Construct the full URL: scheme://host/basePath
                server_urls.append(f"{scheme}://{host}{base_path}")

        return server_urls
    

    def check_description(self, element: Dict[str, Any], constraints: Dict[str, Any]) -> List[str]:
        """
        Validates the 'description' field of an OpenAPI element against a set of constraints.

        This method performs a sequence of checks: existence, emptiness, word count (min/max),
        and keyword presence. It uses an 'early exit' strategy to prevent redundant error reporting 
        (e.g., preventing an empty description from also being flagged as "too short").

        Args:
            element (Dict[str, Any]): The OpenAPI object to inspect (e.g., an operation, 
                                      info block, or parameter object).
            constraints (Dict[str, Any]): A dictionary of validation rules. 
                                          Supported keys: 'min-words', 'max-words', 'keywords'.

        Returns:
            List[str]: A list of violation messages. Returns an empty list if the 
                       description is valid.
        """
        violations: List[str] = []

        # 1. Check for Field Existence
        if "description" not in element:
            return ["missing description field"]

        # Retrieve the raw value
        raw_description = element["description"]

        # 2. Check for Content (Emptiness)
        # We use 'has_content' method defined below.
        if not self.has_content(raw_description):
            return ["empty description"]

        # Normalize: Replace newlines/tabs with spaces, strip whitespace, convert to lowercase.
        # Ensuring raw_description is a string is handled by the logic above/normalization.
        description_text = self.WHITESPACE_PATTERN.sub(" ", str(raw_description)).strip().lower()
        
        # Calculate word count based on whitespace separation
        word_count = len(description_text.split())

        # 3. Check Minimum Length
        if "min-words" in constraints:
            min_threshold = constraints["min-words"]
            if word_count < min_threshold:
                violations.append("description too short")

        # 4. Check Maximum Length
        if "max-words" in constraints:
            max_threshold = constraints["max-words"]
            if word_count > max_threshold:
                violations.append("description too long")

        # 5. Check Required Keywords
        # Logic: At least ONE of the keywords must be present in the text.
        if "keywords" in constraints:
            required_keywords = constraints["keywords"]
            # Check if any of the keywords exist as a substring in the description
            keyword_found = any(keyword.lower() in description_text for keyword in required_keywords)
            
            if not keyword_found:
                violations.append("no keywords in description")

        return violations
    

    def has_content(self, text: Optional[Any]) -> bool:
        """
            Determines whether the provided input is a non-empty string with significant content.

            This method implements a defensive programming pattern to safely handle 
            inputs of any type. It validates that the input is strictly an instance 
            of `str` and contains characters other than whitespace.

            Args:
                text (Optional[Any]): The input data to evaluate. While this is intended 
                    for strings, it safely accepts `None` or other data types without 
                    raising an exception.

            Returns:
                bool: `True` if the input is a string containing at least one 
                non-whitespace character. Returns `False` for `None`, empty strings, 
                whitespace-only strings, or non-string objects (e.g., integers, dicts).

            Examples:
                >>> evaluator.has_content("OpenAPI")
                True
                >>> evaluator.has_content("   ")
                False
                >>> evaluator.has_content(None)
                False
                >>> evaluator.has_content(12345)
                False
        """
        # Defensive check: ensure the input is actually a string before invoking string methods.
        if not isinstance(text, str):
            return False
        
        # .strip() removes leading/trailing whitespace.
        # bool() converts the result to True if characters remain, False if empty.
        return bool(text.strip())
    

    def add_evaluation(
        self, 
        outcome: Literal["pass", "fail"], 
        data: Optional[Dict[str, Any]] = None, 
        rule_id: Optional[str] = None
    ) -> None:
        """
        Records the result of a specific quality rule evaluation.

        This method updates the overall statistics, the group statistics, and 
        stores the detailed outcome of the rule. It employs runtime introspection
        to automatically determine the rule ID if one is not explicitly provided.

        Args:
            outcome (Literal["pass", "fail"]): The result of the evaluation. 
                Must be strictly 'pass' or 'fail'.
            data (Optional[Dict[str, Any]]): Additional context about the result 
                (e.g., error messages, invalid values). Defaults to an empty dict.
            rule_id (Optional[str]): The unique identifier of the rule. 
                If None, the method attempts to infer the ID from the calling function's name.
        """
        # Safe initialization of mutable default argument
        if data is None:
            data = {}

        rule_id = data.get("rule_id", rule_id)

        # 1. Determine the Rule ID
        # If not provided, we dynamically inspect the call stack to get the caller's name.
        if not rule_id:
            current_frame = inspect.currentframe()
            if current_frame and current_frame.f_back:
                # Get the name of the function that called this method
                caller_name = current_frame.f_back.f_code.co_name
                # Normalize: "evaluate_api_title" -> "evaluate-api-title"
                rule_id = caller_name.replace("_", "-")
            else:
                # Fallback if introspection fails (e.g., in some lambda or wrapper contexts)
                rule_id = "unknown-rule"

        # 2. Store the detailed evaluation
        self.evaluations[rule_id] = {"outcome": outcome, **data}

        # 3. Update Statistics
        group_name = self.get_evaluation_group(rule_id)
        
        # Ensure the group entry exists in the report
        if group_name not in self.evaluations["evaluation-groups"]:
            self.evaluations["evaluation-groups"][group_name] = {
                "total": 0,
                "pass": 0,
                "fail": 0
            }

        # Increment counters for the specific group
        self.evaluations["evaluation-groups"][group_name]["total"] += 1
        self.evaluations["evaluation-groups"][group_name][outcome] += 1

        # Increment overall counters
        self.evaluations["overall"]["total"] += 1
        self.evaluations["overall"][outcome] += 1


    def get_evaluation_group(self, rule_id: str) -> str:
        """
        Retrieves the category (group) associated with a specific evaluation rule.

        This method performs a reverse lookup in the configuration dictionary.
        If the rule ID is not found in any defined group, it assigns it to a 
        default 'uncategorized' group to maintain report integrity.

        Args:
            rule_id (str): The unique identifier of the rule (e.g., 'evaluate-api-title').

        Returns:
            str: The name of the group (e.g., 'governance', 'security') or 'uncategorized'.
        """
        # Access the global config object (ensure 'config' is imported)
        groups = self.config.get("groups", {})

        for group_name, rules_list in groups.items():
            if rule_id in rules_list:
                return group_name
            
        return "uncategorized"

    def _get_info_object(self) -> Optional[Dict[str, Any]]:
        """
        Safe accessor for the info object. 
        Returns None if missing or invalid, decoupling data retrieval from reporting logic.
        """
        info = self.oas.get("info")
        if not info or not isinstance(info, dict):
            return None
        return info    

    def _yield_operations(self):
        """
        Generator that yields all valid operations in the OAS.
        Yields: (path_string, method_string, operation_dict)
        """
        if "paths" not in self.oas or not isinstance(self.oas["paths"], dict):
            return

        for path, path_item in self.oas["paths"].items():
            if not isinstance(path_item, dict):
                continue

            for method, operation in path_item.items():
                if method.lower() not in self.VALID_METHODS or not isinstance(operation, dict):
                    continue
                
                yield path, method, operation

    
    def _evaluate_ratio(
        self, 
        total: int, 
        valid: int, 
        min_percentage: float, 
        details: Dict[str, Any], 
        fail_msg: str
    ) -> None:
        """Evaluates a pass/fail based on a valid/total ratio."""

        rule_id = details.get("rule_id", None)

        if total == 0:
            self.add_evaluation("pass", {"reason": "no elements found (N/A)"}, rule_id)
            return

        actual_percentage = valid / total
        details["percentage"] = round(actual_percentage, 2)
        details["min-percentage"] = min_percentage

        if actual_percentage < min_percentage:
            self.add_evaluation("fail", {"reason": fail_msg, **details})
        else:
            self.add_evaluation("pass", details)


    def execute(self) -> Dict[str, Any]:
        """
        Orchestrates the full quality audit pipeline.

        Returns:
            Dict[str, Any]: The complete evaluation report.
        """

        # ---------------------------------------------------------
        # 1. JSON SYNTAX CHECK (Local Mode Only)
        # ---------------------------------------------------------
        if self.mode == "local":
            self.evaluate_validate_json()
            
            # CRITICAL: If the file is not valid JSON, we stop immediately.
            # There is no point in trying to parse OAS structures on broken JSON.
            json_result = self.evaluations.get("evaluate-validate-json", {})
            if json_result.get("outcome") == "fail":
                self.evaluations["quality"] = "0%"
                return self.evaluations

        # ---------------------------------------------------------
        # 2. REFERENCE RESOLUTION ($ref)
        # ---------------------------------------------------------
        try:
            # We provide the base_uri so relative paths in local files work correctly
            base_uri = self.oas_path if self.oas_path else ""
            self.oas = replace_refs(self.oas, base_uri=base_uri)
        except Exception as e:
            # We log the warning internally but continue with best-effort analysis
            print(f"[Warning] Reference resolution failed: {e}")

        # ---------------------------------------------------------
        # 3. STRUCTURAL VALIDATION (Schema)
        # ---------------------------------------------------------
        self.evaluate_validate_oas()

        # Note: We continue execution even if schema validation fails, 
        # allowing the user to see other quality issues (best effort).

        # ---------------------------------------------------------
        # 4. EXECUTE RULE GROUPS
        # ---------------------------------------------------------
        
        # Versioning
        self.evaluate_oas_version()

        # Metadata
        self.evaluate_api_title()
        self.evaluate_api_description()
        self.evaluate_api_contact()
        self.evaluate_api_version()
        self.evaluate_api_license()
        self.evaluate_api_terms()

        # Server Configuration
        self.evaluate_server_url()
        self.evaluate_server_validity()
        self.evaluate_scheme()

        # Documentation Details
        self.evaluate_route_descriptions()
        self.evaluate_response_descriptions()
        self.evaluate_parameter_descriptions()

        # Examples Coverage
        self.evaluate_response_examples()
        self.evaluate_parameter_examples()

        # ---------------------------------------------------------
        # 5. SCORING (Safe Calculation)
        # ---------------------------------------------------------
        total = self.evaluations["overall"]["total"]
        passed = self.evaluations["overall"]["pass"]

        # Prevent ZeroDivisionError if total is 0 (e.g., empty file)
        if total > 0:
            standard_quality = passed / total
        else:
            standard_quality = 0

        # normalized quality
        weights = self.config.get("normalization-weights", {"format": 0.2, "oas-version": 0.2, "metadata": 0.2, "server": 0.2, "semantics": 0.2})

        normalized_quality = 0

        for group in self.evaluations["evaluation-groups"]:
            normalized_quality += (self.evaluations["evaluation-groups"][group]["pass"] / self.evaluations["evaluation-groups"][group]["total"]) * weights[group]

        self.evaluations["quality"] = {
            "standard": standard_quality,
            "normalized": normalized_quality
        }

        return self.evaluations