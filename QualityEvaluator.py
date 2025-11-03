import language_tool_python, re, textstat


class QualityEvaluator:


    def __init__(self):
        self.language_tool = language_tool_python.LanguageTool("en-US")


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