import inspect, json, openapi_spec_validator, re, requests
from config import get_config
from datetime import datetime


config = get_config()


class QualityEvaluator:


    def __init__(self, oas_path):

        self.oas_path = oas_path
        self.oas = {}
        self.evaluations = {
            "api-name": oas_path.split("/")[-1].replace(".json", ""),
            "timestamp": str(datetime.now()),
            "evaluation-groups": {}
        }


    def evaluate_validate_json(self):

        try:
            with open(self.oas_path, "r", encoding=config["file-encoding"]) as file:
                self.oas = json.load(file)
                self.add_evaluation("pass")

        except Exception as e:
            self.add_evaluation("fail", {"reason": type(e).__name__})


    def evaluate_validate_oas(self):

        try:
            openapi_spec_validator.validate(self.oas)
            self.add_evaluation("pass")

        except Exception as e:
            self.add_evaluation("fail", {"reason": type(e).__name__})


    def evaluate_oas_version(self):

        if "openapi" in self.oas:
            version = self.oas["openapi"]
            self.add_evaluation("pass", {"version": f"openapi-{version}"})

        elif "swagger" in self.oas:
            version = self.oas["swagger"]
            self.add_evaluation("fail", {"reason": "outdated OAS version", "version": f"swagger-{version}"})

        else:
            self.add_evaluation("fail", {"reason": "unknown OAS version", "version": "unknown"})


    def evaluate_api_title(self):

        if "info" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing info field"})
            return
        
        if "title" not in self.oas["info"]:
            self.add_evaluation("fail", {"reason": "missing title field"})
            return
        
        title = self.oas["info"]["title"]
        
        if not self.has_content(title):
            self.add_evaluation("fail", {"reason": "empty title field"})
            return
        
        self.add_evaluation("pass", {"title": title})


    def evaluate_api_description(self):

        if "info" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing info field"})
            return
        
        if "description" not in self.oas["info"]:
            self.add_evaluation("fail", {"reason": "missing description field"})
            return
        
        description = self.oas["info"]["description"]
        constraints = config["descriptions"]["api"]
        violations = self.check_description(description, constraints)

        if len(violations) > 0:
            self.add_evaluation("fail", {"reason": ", ".join(violations)})
        else:
            self.add_evaluation("pass")


    def evaluate_api_contact(self):

        if "info" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing info field"})
            return

        if "contact" not in self.oas["info"]:
            self.add_evaluation("fail", {"reason": "missing contact field"})
            return
        
        contact = self.oas["info"]["contact"]
        
        if contact == {}:
            self.add_evaluation("fail", {"reason": "empty contact field"})
            return

        if "email" not in contact and "url" not in contact:
            self.add_evaluation("fail", {"reason": "missing email or url field"})
            return
        
        if "email" in contact and not self.has_content(contact["email"]):
            self.add_evaluation("fail", {"reason": "empty email field"})
            return
        
        if "url" in contact and not self.has_content(contact["url"]):
            self.add_evaluation("fail", {"reason": "empty url field"})
            return
        
        self.add_evaluation("pass", {"contact": contact})


    def evaluate_api_version(self):

        if "info" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing info field"})
            return
        
        if "version" not in self.oas["info"]:
            self.add_evaluation("fail", {"reason": "missing version field"})
            return
        
        version = self.oas["info"]["version"]

        if not self.has_content(version):
            self.add_evaluation("fail", {"reason": "empty version field"})
            return
        
        self.add_evaluation("pass", {"version": version})


    def evaluate_api_license(self):

        if "info" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing info field"})
            return
        
        if "license" not in self.oas["info"]:
            self.add_evaluation("fail", {"reason": "missing license field"})
            return
        
        license = self.oas["info"]["license"]

        if license == {}:
            self.add_evaluation("fail", {"reason": "empty license field"})
            return
        
        self.add_evaluation("pass", {"license": license})


    def evaluate_api_terms(self):

        if "info" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing info field"})
            return
        
        if "termsOfService" not in self.oas["info"]:
            self.add_evaluation("fail", {"reason": "missing termsOfService field"})
            return
        
        terms = self.oas["info"]["termsOfService"]

        if terms == {}:
            self.add_evaluation("fail", {"reason": "empty termsOfService field"})
            return
        
        self.add_evaluation("pass", {"terms": terms})


    def evaluate_server_url(self):

        server_urls = self.get_oas_servers()

        if len(server_urls) > 0:
            self.add_evaluation("pass", {"urls": server_urls})

        else:
            self.add_evaluation("fail", {"reason": "missing server URL"})


    def evaluate_server_validity(self):

        server_urls = self.get_oas_servers()

        if len(server_urls) == 0:
            self.add_evaluation("fail", {"reason": "missing server URL"})
            return

        # if at least one of the server URLs is valid, pass the evaluation
        for url in server_urls:
            try:
                response = requests.get(url, timeout=10)
                self.add_evaluation("pass", {"code": response.status_code, "urls": server_urls})
                break
            except:
                self.add_evaluation("fail", {"reason": "invalid server URL", "url": url})


    def evaluate_scheme(self):

        server_urls = self.get_oas_servers()

        if len(server_urls) == 0:
            self.add_evaluation("fail", {"reason": "missing server URL"})
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
            self.add_evaluation("fail", {"reason": "missing or outdated schemes", "nb-http": nb_http, "nb-missing": nb_missing, "urls": server_urls})
        else:
            self.add_evaluation("pass", {"urls": server_urls})


    def evaluate_route_descriptions(self):

        if "paths" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return
        
        counters = {
            "nb-routes-total": 0,
            "nb-routes-with-valid-desc": 0,
            "invalid-details": {}
        }
        constraints = config["descriptions"]["routes"]

        for path in self.oas["paths"]:
            for method in self.oas["paths"][path]:
                route_data = self.oas["paths"][path][method]
                counters["nb-routes-total"] += 1

                violations = self.check_description(route_data, constraints)

                for id in violations:
                        if id not in counters["invalid-details"]:
                            counters["invalid-details"][id] = 0
                        counters["invalid-details"][id] += 1

                if len(violations) == 0:
                    counters["nb-routes-with-valid-desc"] += 1

        percentage = counters["nb-routes-with-valid-desc"] / counters["nb-routes-total"]
        min_percentage = constraints["min-percentage"]

        if percentage < min_percentage:
            self.add_evaluation("fail", {"reason": "not enough valid route descriptions", "percentage": percentage, "min-percentage": min_percentage, **counters})
        else:
            self.add_evaluation("pass", {"percentage": percentage, "min-percentage": min_percentage, **counters})


    def evaluate_response_descriptions(self):

        if "paths" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return
        
        counters = {
            "nb-responses-total": 0,
            "nb-responses-with-valid-desc": 0,
            "invalid-details": {}
        }
        constraints = config["descriptions"]["responses"]
        
        for path in self.oas["paths"]:
            for method in self.oas["paths"][path]:
                route_data = self.oas["paths"][path][method]

                if "responses" not in route_data:
                    counters["nb-responses-total"] += 2 # we suppose 2 because 1 for a valid response and 1 for an invalid response (e.g., 200 and 404)
                    continue

                for response in route_data["responses"]:
                    response_data = route_data["responses"][response]
                    counters["nb-responses-total"] += 1

                    violations = self.check_description(response_data, constraints)

                    for id in violations:
                        if id not in counters["invalid-details"]:
                            counters["invalid-details"][id] = 0
                        counters["invalid-details"][id] += 1

                    if len(violations) == 0:
                        counters["nb-responses-with-valid-desc"] += 1

        percentage = counters["nb-responses-with-valid-desc"] / counters["nb-responses-total"]
        min_percentage = constraints["min-percentage"]

        if percentage < min_percentage:
            self.add_evaluation("fail", {"reason": "not enough valid response descriptions", "percentage": percentage, "min-percentage": min_percentage, **counters})
        else:
            self.add_evaluation("pass", {"percentage": percentage, "min-percentage": min_percentage, **counters})


    def evaluate_parameter_descriptions(self):

        if "paths" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return
        
        counters = {
            "nb-parameters-total": 0,
            "nb-parameters-with-valid-desc": 0,
            "invalid-details": {}
        }
        constraints = config["descriptions"]["parameters"]

        for path in self.oas["paths"]:
            for method in self.oas["paths"][path]:
                route_data = self.oas["paths"][path][method]

                if not "parameters" in route_data:
                    continue
                
                for parameter_data in route_data["parameters"]:
                    counters["nb-parameters-total"] += 1

                    violations = self.check_description(parameter_data, constraints)

                    for id in violations:
                        if id not in counters["invalid-details"]:
                            counters["invalid-details"][id] = 0
                        counters["invalid-details"][id] += 1

                    if len(violations) == 0:
                        counters["nb-parameters-with-valid-desc"] += 1


        percentage = counters["nb-parameters-with-valid-desc"] / counters["nb-parameters-total"]
        min_percentage = constraints["min-percentage"]

        if percentage < min_percentage:
            self.add_evaluation("fail", {"reason": "not enough valid parameter descriptions", "percentage": percentage, "min-percentage": min_percentage, **counters})
        else:
            self.add_evaluation("pass", {"percentage": percentage, "min-percentage": min_percentage, **counters})


    def evaluate_response_examples(self):

        if "paths" not in self.oas:
            self.add_evaluation("fail", {"reason": "missing paths field"})
            return
        
        counters = {
            "nb-media-total": 0,
            "nb-media-with-valid-example": 0
        }
        constraints = config["examples"]["responses"]

        for path in self.oas["paths"]:
            for method in self.oas["paths"][path]:
                route_data = self.oas["paths"][path][method]

                if "responses" not in route_data:
                    counters["nb-media-total"] += 2 # we suppose 2 because 1 for a valid response and 1 for an invalid response (e.g., 200 and 404)
                    continue

                for response in route_data["responses"]:
                    response_data = route_data["responses"][response]

                    if "content" not in response_data or response_data["content"] == {}:
                        counters["nb-media-total"] += 1
                        continue

                    for media in response_data["content"]:
                        media_data = response_data["content"][media]
                        counters["nb-media-total"] += 1

                        if ("examples" in media_data and media_data["examples"] != {}) or ("example" in media_data and media_data["example"] != {}):
                            counters["nb-media-with-valid-example"] += 1

        percentage = counters["nb-media-with-valid-example"] / counters["nb-media-total"]
        min_percentage = constraints["min-percentage"]

        if percentage < min_percentage:
            self.add_evaluation("fail", {"reason": "not enough valid response examples", "percentage": percentage, "min-percentage": min_percentage, **counters})
        else:
            self.add_evaluation("pass", {"percentage": percentage, "min-percentage": min_percentage, **counters})


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
    

    def check_description(self, description_location, constraints):

        if "description" not in description_location:
            return ["missing description field"]

        description = re.sub(r"\s+", " ", description_location["description"]).strip().lower()
        nb_words = len(description.split())
        violations = []

        if not self.has_content(description):
            violations.append("empty description")

        if "min-words" in constraints and nb_words < constraints["min-words"]:
            violations.append("description too short")

        if "max-words" in constraints and nb_words > constraints["max-words"]:
            violations.append("description too long")

        if "keywords" in constraints and not any(keyword in description for keyword in constraints["keywords"]):
            violations.append("no keywords in description")

        return violations
    

    def has_content(self, str):

        return bool(str and str.strip())
    

    def add_evaluation(self, outcome, data={}):

        # get caller name
        evaluation_id = inspect.currentframe().f_back.f_code.co_name.replace("_", "-")
        
        self.evaluations[evaluation_id] = {"outcome": outcome, **data}

        group = self.get_evaluation_group(evaluation_id)

        if group not in self.evaluations["evaluation-groups"]:
            self.evaluations["evaluation-groups"][group] = {
                "total": 0,
                "pass": 0,
                "fail": 0
            }

        self.evaluations["evaluation-groups"][group]["total"] += 1
        self.evaluations["evaluation-groups"][group][outcome] += 1


    def get_evaluation_group(self, evaluation_id):

        groups = config["groups"]

        for group_name, evaluation_ids in groups.items():
            if evaluation_id in evaluation_ids:
                return group_name
            
        return None
        

    def execute(self):

        # TODO: replace OAS refs with their data to avoid false positives in descriptions and examples
        # self.parse_refs()

        # formats
        self.evaluate_validate_json()
        self.evaluate_validate_oas()

        # OAS version
        self.evaluate_oas_version()

        # metadata
        self.evaluate_api_title()
        self.evaluate_api_description()
        self.evaluate_api_contact()
        self.evaluate_api_version()
        self.evaluate_api_license()
        self.evaluate_api_terms()

        # server
        self.evaluate_server_url()
        self.evaluate_server_validity()
        self.evaluate_scheme()

        # descriptions
        self.evaluate_route_descriptions()
        self.evaluate_response_descriptions()
        self.evaluate_parameter_descriptions()

        # examples
        self.evaluate_response_examples()

        # TODO
        # self.evaluate_response_examples()
        # self.evaluate_parameter_examples()
        # ...

        print(json.dumps(self.evaluations, indent=4))