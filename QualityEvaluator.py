import json, language_tool_python, openapi_spec_validator, re, requests, textstat
from datetime import datetime


class QualityEvaluator:


    def __init__(self, oas_path):

        #self.language_tool = language_tool_python.LanguageTool("en-US")
        self.oas_path = oas_path
        self.oas = {}
        self.evaluations = {
            "api-name": oas_path.split("/")[-1].replace(".json", ""),
            "timestamp": str(datetime.now())
        }


    def evaluate_description_quality(self, description):

        score = 0
        feedback = []

        # replace any whitespace (line break, tab, etc.) with a single space
        description = re.sub(r"\s+", " ", description).strip()

        # description length
        nb_words = len(description.split())
        if nb_words < 5:
            feedback.append(("Description is too short."))
        elif nb_words > 100:
            feedback.append(("Description is too long."))
        else:
            score += 1

        # grammar and spelling
        matches = self.language_tool.check(description)
        if len(matches) > 0:
            feedback.append(("Description contains grammar and/or spelling issue(s)."))
        else:
            score += 1

        # readability
        readability = textstat.flesch_reading_ease(description)
        if readability < 30:
            feedback.append(("Description is not readable enough."))
        else:
            score += 1

        # action verb presence
        verbs = ("get", "post", "put", "patch", "retrieve", "create", "read", "update", "delete", "list", "fetch", "remove", "return", "add")
        if not any(verb in description.lower() for verb in verbs):
            feedback.append(("Description does not contain any action verb."))
        else:
            score += 1

        return {
            "score": score,
            "feedback": feedback
        }
    

    def evaluate_validate_json(self):

        try:
            with open(self.oas_path, "r", encoding="utf-8-sig") as file: # maybe later check if unsupported utf8 is a bad thing for oas files?
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
            self.evaluations["oas-version"] = {"result": "fail", "reason": "Outdated OAS version.", "version": f"swagger-{version}"}

        else:
            self.evaluations["oas-version"] = {"result": "fail", "reason": "Unknown OAS version.", "version": "unknown"}


    def evaluate_server_url(self):

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

        if len(server_urls) > 0:
            self.evaluations["server-url"] = {"result": "pass", "urls": server_urls}

        else:
            self.evaluations["server-url"] = {"result": "fail", "reason": "Missing server URL(s)."}


    def evaluate_server_validity(self):

        if self.evaluations["server-url"]["result"] == "fail":
            self.evaluations["server-valid"] = {"result": "fail", "reason": "Missing server URL(s) to verify."}
            return

        server_urls = self.evaluations["server-url"]["urls"]

        # if at least one of the server URLs is valid, pass the evaluation
        for url in server_urls:
            try:
                response = requests.get(url, timeout=10)
                self.evaluations["server-valid"] = {"result": "pass", "code": response.status_code}
                break
            except:
                self.evaluations["server-valid"] = {"result": "fail", "reason": "Invalid server URL.", "url": url}


    def evaluate_secure_https(self):

        server_urls = self.evaluations["server-url"]["urls"]

        http_urls = []

        for url in server_urls:
            if not url.startswith("https"):
                http_urls.append(url)

        if len(http_urls) > 0:
            self.evaluations["secure-https"] = {"result": "fail", "reason": "One or more server(s) contains outdated HTTP or a non-specified scheme.", "urls": http_urls}
        else:
            self.evaluations["secure-https"] = {"result": "pass"}


    def evaluate_api_description(self):

        if "info" not in self.oas:
            self.evaluations["api-description"] = {"result": "fail", "reason": "Missing info field."}
            return
        
        if "description" not in self.oas["info"]:
            self.evaluations["api-description"] = {"result": "fail", "reason": "Missing API description field."}
            return
        
        description = re.sub(r"\s+", " ", self.oas["info"]["description"]).strip()
        nb_words = len(description.split())

        if nb_words < 10:
            self.evaluations["api-description"] = {"result": "fail", "reason": "API description is too short."}

        elif nb_words > 500:
            self.evaluations["api-description"] = {"result": "fail", "reason": "API description is too long."}

        else:
            self.evaluations["api-description"] = {"result": "pass"}


    def evaluate_api_contact(self):

        if "info" not in self.oas:
            self.evaluations["api-contact"] = {"result": "fail", "reason": "Missing info field."}
            return

        if "contact" not in self.oas["info"]:
            self.evaluations["api-contact"] = {"result": "fail", "reason": "Missing contact field."}
            return
        
        if self.oas["info"]["contact"] == {}:
            self.evaluations["api-contact"] = {"result": "fail", "reason": "Empty contact field."}
            return

        if "email" not in self.oas["info"]["contact"] and "url" not in self.oas["info"]["contact"]:
            self.evaluations["api-contact"] = {"result": "fail", "reason": "Missing email or url field."}
            return
        
        if "email" in self.oas["info"]["contact"] and self.oas["info"]["contact"]["email"] == "":
            self.evaluations["api-contact"] = {"result": "fail", "reason": "Empty email field."}
            return
        
        if "url" in self.oas["info"]["contact"] and self.oas["info"]["contact"]["url"] == "":
            self.evaluations["api-contact"] = {"result": "fail", "reason": "Empty url field."}
            return

        self.evaluations["api-contact"] = {"result": "pass", "contact": self.oas["info"]["contact"]}


    def evaluate_route_descriptions(self):

        if "paths" not in self.oas:
            self.evaluations["route-descriptions"] = {"result": "fail", "reason": "Missing paths field."}
            return

        nb_routes = 0
        nb_missing_descriptions = 0
        nb_too_short_descriptions = 0
        nb_too_long_descriptions = 0
        nb_without_action_descriptions = 0

        for path_name, path_data in self.oas["paths"].items():
            for method_name, method_data in path_data.items():
                nb_routes += 1

                if "description" not in method_data:
                    nb_missing_descriptions += 1
                    continue

                description = re.sub(r"\s+", " ", method_data["description"]).strip()
                nb_words = len(description.split())

                if nb_words < 5:
                    nb_too_short_descriptions += 1

                if nb_words > 150:
                    nb_too_long_descriptions += 1

                verbs = ("get", "post", "put", "patch", "retrieve", "create", "read", "update", "delete", "list", "fetch", "remove", "return", "add")
                if not any(verb in description.lower() for verb in verbs):
                    nb_without_action_descriptions += 1

        if nb_missing_descriptions > 0 or nb_too_short_descriptions > 0 or nb_too_long_descriptions > 0 or nb_without_action_descriptions > 0:
            self.evaluations["route-descriptions"] = {"result": "fail", "reason": "Missing or invalid route descriptions.", "nb-routes": nb_routes, "nb-missing-descriptions": nb_missing_descriptions, "nb-too-short-descriptions": nb_too_short_descriptions, "nb-too-long-descriptions": nb_too_long_descriptions, "nb-without-action-descriptions": nb_without_action_descriptions}
            return

        self.evaluations["route-descriptions"] = {"result": "pass", "nb-routes": nb_routes}


    def evaluate_response_descriptions(self):

        if "paths" not in self.oas:
            self.evaluations["response-descriptions"] = {"result": "fail", "reason": "Missing paths field."}
            return
        
        nb_routes_without_responses = 0
        nb_responses = 0
        nb_missing_descriptions = 0
        nb_invalid_descriptions = 0
        
        for path_name, path_data in self.oas["paths"].items():
            for method_name, method_data in path_data.items():
                if "responses" not in method_data:
                    nb_routes_without_responses += 1
                    continue
                
                for response_name, response_data in method_data["responses"].items():
                    nb_responses += 1

                    if "description" not in response_data:
                        nb_missing_descriptions += 1
                        continue

                    nb_words = len(response_data["description"].split())
                    if nb_words < 2:
                        nb_invalid_descriptions += 1

        if nb_routes_without_responses > 0 or nb_missing_descriptions > 0 or nb_invalid_descriptions > 0:
            self.evaluations["response-descriptions"] = {"result": "fail", "reason": "Missing or invalid response descriptions in routes.", "nb-routes-without-responses": nb_routes_without_responses, "nb-responses": nb_responses, "nb-missing-descriptions": nb_missing_descriptions, "nb-invalid-descriptions": nb_invalid_descriptions}
            return
        
        self.evaluations["response-descriptions"] = {"result": "pass", "nb-responses": nb_responses}
    

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