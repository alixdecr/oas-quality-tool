import json, openapi_spec_validator, re, requests
from config import get_config
from datetime import datetime


config = get_config()


class QualityEvaluator:


    def __init__(self, oas_path):

        self.oas_path = oas_path
        self.oas = {}
        self.evaluations = {
            "api-name": oas_path.split("/")[-1].replace(".json", ""),
            "timestamp": str(datetime.now())
        }


    def evaluate_validate_json(self):

        try:
            with open(self.oas_path, "r", encoding=config["file-encoding"]) as file:
                self.oas = json.load(file)
                self.evaluations["validate-json"] = {"result": "pass"}

        except Exception as e:
            self.evaluations["validate-json"] = {"result": "fail", "reason": type(e).__name__}


    def evaluate_validate_oas(self):

        try:
            openapi_spec_validator.validate(self.oas)
            self.evaluations["validate-oas"] = {"result": "pass"}

        except Exception as e:
            self.evaluations["validate-oas"] = {"result": "fail", "reason": type(e).__name__}


    def evaluate_oas_version(self):

        if "openapi" in self.oas:
            version = self.oas["openapi"]
            self.evaluations["oas-version"] = {"result": "pass", "version": f"openapi-{version}"}

        elif "swagger" in self.oas:
            version = self.oas["swagger"]
            self.evaluations["oas-version"] = {"result": "fail", "reason": "outdated OAS version", "version": f"swagger-{version}"}

        else:
            self.evaluations["oas-version"] = {"result": "fail", "reason": "unknown OAS version", "version": "unknown"}


    def evaluate_server_url(self):

        server_urls = self.get_oas_servers()

        if len(server_urls) > 0:
            self.evaluations["server-url"] = {"result": "pass", "urls": server_urls}

        else:
            self.evaluations["server-url"] = {"result": "fail", "reason": "missing server URL"}


    def evaluate_server_validity(self):

        server_urls = self.get_oas_servers()

        if len(server_urls) == 0:
            self.evaluations["server-valid"] = {"result": "fail", "reason": "missing server URL"}
            return

        # if at least one of the server URLs is valid, pass the evaluation
        for url in server_urls:
            try:
                response = requests.get(url, timeout=10)
                self.evaluations["server-valid"] = {"result": "pass", "code": response.status_code, "urls": server_urls}
                break
            except:
                self.evaluations["server-valid"] = {"result": "fail", "reason": "invalid server URL", "url": url}


    def evaluate_secure_https(self):

        server_urls = self.get_oas_servers()

        if len(server_urls) == 0:
            self.evaluations["secure-https"] = {"result": "fail", "reason": "missing server URL"}
            return

        nb_http = 0
        nb_missing = 0

        for url in server_urls:
            if not url.startswith("https"):
                if not url.startswith("http"):
                    nb_missing += 1
                else:
                    nb_http += 1

        if nb_http > 0 or nb_missing > 0:
            self.evaluations["secure-https"] = {"result": "fail", "reason": "missing or outdated schemes", "nb-http": nb_http, "nb-missing": nb_missing, "urls": server_urls}
        else:
            self.evaluations["secure-https"] = {"result": "pass", "urls": server_urls}


    def evaluate_api_description(self):

        if "info" not in self.oas:
            self.evaluations["api-description"] = {"result": "fail", "reason": "missing info field"}
            return
        
        if "description" not in self.oas["info"]:
            self.evaluations["api-description"] = {"result": "fail", "reason": "missing description field"}
            return
        
        description = self.oas["info"]["description"]
        constraints = config["descriptions"]["api"]
        violations = self.check_description(description, constraints)

        if len(violations) > 0:
            self.evaluations["api-description"] = {"result": "fail", "reason": ", ".join(violations)}
        else:
            self.evaluations["api-description"] = {"result": "pass"}


    def evaluate_api_contact(self):

        if "info" not in self.oas:
            self.evaluations["api-contact"] = {"result": "fail", "reason": "missing info field"}
            return

        if "contact" not in self.oas["info"]:
            self.evaluations["api-contact"] = {"result": "fail", "reason": "missing contact field"}
            return
        
        if self.oas["info"]["contact"] == {}:
            self.evaluations["api-contact"] = {"result": "fail", "reason": "empty contact field."}
            return

        if "email" not in self.oas["info"]["contact"] and "url" not in self.oas["info"]["contact"]:
            self.evaluations["api-contact"] = {"result": "fail", "reason": "missing email or url field"}
            return
        
        if "email" in self.oas["info"]["contact"] and self.oas["info"]["contact"]["email"] == "":
            self.evaluations["api-contact"] = {"result": "fail", "reason": "empty email field"}
            return
        
        if "url" in self.oas["info"]["contact"] and self.oas["info"]["contact"]["url"] == "":
            self.evaluations["api-contact"] = {"result": "fail", "reason": "empty url field"}
            return

        self.evaluations["api-contact"] = {"result": "pass", "contact": self.oas["info"]["contact"]}


    def evaluate_route_descriptions(self):

        if "paths" not in self.oas:
            self.evaluations["route-descriptions"] = {"result": "fail", "reason": "missing paths field"}
            return
        
        counters = {
            "nb-routes": 0,
            "nb-desc-missing": 0,
            "nb-desc-invalid" : 0,
            "invalid-details": {}
        }
        constraints = config["descriptions"]["routes"]

        for path in self.oas["paths"]:
            for method in self.oas["paths"][path]:
                route_data = self.oas["paths"][path][method]
                counters["nb-routes"] += 1

                if "description" not in route_data:
                    counters["nb-desc-missing"] += 1
                    continue

                description = route_data["description"]
                violations = self.check_description(description, constraints)

                if len(violations) > 0:
                    counters["nb-desc-invalid"] += 1

                    for id in violations:
                        if id not in counters["invalid-details"]:
                            counters["invalid-details"][id] = 0
                        counters["invalid-details"][id] += 1

        percentage = (counters["nb-desc-missing"] + counters["nb-desc-invalid"]) / counters["nb-routes"]
        threshold = constraints["invalid-threshold"]

        if percentage > threshold:
            self.evaluations["route-descriptions"] = {"result": "fail", "reason": "too many missing or invalid descriptions", "percentage": percentage, "threshold": threshold, **counters}
        else:
            self.evaluations["route-descriptions"] = {"result": "pass", "percentage": percentage, "threshold": threshold, **counters}


    def evaluate_response_descriptions(self):

        if "paths" not in self.oas:
            self.evaluations["response-descriptions"] = {"result": "fail", "reason": "Missing paths field."}
            return
        
        counters = {
            "nb-routes": 0,
            "nb-routes-without-responses": 0,
            "nb-responses": 0,
            "nb-desc-missing": 0,
            "nb-desc-invalid": 0,
            "invalid-details": {}
        }
        constraints = config["descriptions"]["responses"]
        
        for path in self.oas["paths"]:
            for method in self.oas["paths"][path]:
                route_data = self.oas["paths"][path][method]
                counters["nb-routes"] += 1

                if "responses" not in route_data:
                    counters["nb-routes-without-responses"] += 1
                    continue

                for response in route_data["responses"]:
                    response_data = route_data["responses"][response]
                    counters["nb-responses"] += 1

                    if "description" not in response_data:
                        counters["nb-desc-missing"] += 1
                        continue

                    description = response_data["description"]
                    violations = self.check_description(description, constraints)

                    if len(violations) > 0:
                        counters["nb-desc-invalid"] += 1

                        for id in violations:
                            if id not in counters["invalid-details"]:
                                counters["invalid-details"][id] = 0
                            counters["invalid-details"][id] += 1

        percentage = (counters["nb-desc-missing"] + counters["nb-desc-invalid"]) / counters["nb-responses"]
        threshold = constraints["invalid-threshold"]

        if percentage > threshold:
            self.evaluations["response-descriptions"] = {"result": "fail", "reason": "too many missing or invalid descriptions", "percentage": percentage, "threshold": threshold, **counters}
        else:
            self.evaluations["response-descriptions"] = {"result": "pass", "percentage": percentage, "threshold": threshold, **counters}


    def get_oas_servers(self):

        server_urls = []

        if "servers" in self.oas and len(self.oas["servers"]) > 0:
            for server in self.oas["servers"]:
                if "url" in server:
                    server_urls.append(server["url"])

        elif "host" in self.oas:
            host = self.oas["host"]
            base_path = self.oas.get("basePath", "")
            schemes = self.oas.get("schemes", ["https"])

            for scheme in schemes:
                server_urls.append(f"{scheme}://{host}{base_path}")

        return server_urls
    

    def check_description(self, description, constraints):

        description = re.sub(r"\s+", " ", description).strip().lower()
        nb_words = len(description.split())
        violations = []

        if description == "" or description == " ":
            violations.append("empty description")

        if "min-words" in constraints and nb_words < constraints["min-words"]:
            violations.append("description too short")

        if "max-words" in constraints and nb_words > constraints["max-words"]:
            violations.append("description too long")

        if "keywords" in constraints and not any(keyword in description for keyword in constraints["keywords"]):
            violations.append("no keywords in description")

        return violations
        

    def execute(self):

        self.evaluate_validate_json()

        self.evaluate_validate_oas()

        self.evaluate_oas_version()

        self.evaluate_server_url()

        self.evaluate_server_validity()

        self.evaluate_secure_https()

        self.evaluate_api_description()

        self.evaluate_api_contact()

        self.evaluate_route_descriptions()

        self.evaluate_response_descriptions()

        print(json.dumps(self.evaluations, indent=4))