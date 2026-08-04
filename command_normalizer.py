import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache

from command_constants import (
    COLOR_CLOTHE_LIST,
    COLOR_CLOTHES_LIST,
    GESTURE_PERSON_LIST,
    GESTURE_PERSON_PLURAL_LIST,
    OBJECT_COMP_LIST,
    PERSON_INFO_LIST,
    POSE_PERSON_LIST,
    POSE_PERSON_PLURAL_LIST,
    TALK_LIST,
)
from knowledge import Knowledge, parse_data


DATA_DIR = "./CompetitionTemplate"

FILLER_WORDS = {
    "ah",
    "eh",
    "er",
    "hm",
    "hmm",
    "like",
    "okay",
    "please",
    "robot",
    "uh",
    "um",
}

FILLER_PHRASES = (
    "could you please",
    "would you please",
    "can you please",
    "could you",
    "would you",
    "can you",
    "i need you to",
    "i want you to",
    "please can you",
    "please could you",
)

PHRASE_ALIASES = {
    "afterwards": "then",
    "and after that": "then",
    "and then": "then",
    "apple joos": "apple juice",
    "apple jus": "apple juice",
    "bath room": "bathroom",
    "go and": "go to",
    "grab": "take",
    "head over to": "go to",
    "head to": "go to",
    "livingroom": "living room",
    "look around for": "find",
    "make your way to": "go to",
    "move to": "go to",
    "navigate towards": "navigate to",
    "orange joos": "orange juice",
    "orange jus": "orange juice",
    "pick up": "take",
    "pickup": "take",
    "pick": "take",
    "refridgerator": "refrigerator",
    "refrigirator": "refrigerator",
    "search for": "find",
    "side table": "side tables",
    "team affiliation": "teams affiliation",
    "team country": "teams country",
    "team location": "teams affiliation country",
    "team name": "teams name",
    "team's affiliation": "teams affiliation",
    "team's country": "teams country",
    "team's location": "teams affiliation country",
    "team's name": "teams name",
    "teams location": "teams affiliation country",
    "team country": "teams country",
    "t shirt": "t shirt",
    "tee shirt": "t shirt",
    "the the": "the",
    "trashcan": "trash bin",
    "wastebasket": "waste basket",
}


@dataclass
class NormalizationResult:
    original: str
    normalized: str
    changes: list[str] = field(default_factory=list)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _phrase_pattern(phrase: str) -> re.Pattern:
    escaped = re.escape(phrase).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _canonical_key(text: str) -> str:
    text = text.lower()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s']", " ", text)
    text = text.replace("'", "")
    return _normalize_spaces(text)


def _compact(text: str) -> str:
    return _canonical_key(text).replace(" ", "")


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


class CommandNormalizer:
    def __init__(self, knowledge: Knowledge, fuzzy_threshold: float = 0.86):
        self.knowledge = knowledge
        self.fuzzy_threshold = fuzzy_threshold
        self.entities = self._build_entities()
        self.entity_aliases = self._build_entity_aliases()
        self.max_entity_words = max(len(alias.split()) for alias in self.entity_aliases)

    def normalize(self, text: str, return_debug: bool = False):
        original = text
        changes: list[str] = []

        text = self._basic_cleanup(text, changes)
        text = self._remove_fillers(text, changes)
        text = self._remove_adjacent_repetitions(text, changes)
        text = self._apply_phrase_aliases(text, changes)
        text = self._replace_exact_entity_aliases(text, changes)
        text = self._replace_fuzzy_entities(text, changes)
        text = self._remove_adjacent_repetitions(text, changes)
        text = _normalize_spaces(text)

        result = NormalizationResult(original=original, normalized=text, changes=changes)
        return result if return_debug else result.normalized

    def _basic_cleanup(self, text: str, changes: list[str]) -> str:
        cleaned = text.lower()
        cleaned = cleaned.replace("_", " ").replace("-", " ")
        cleaned = cleaned.replace("’", "'")
        cleaned = re.sub(r"[,.;:!?()\[\]{}]", " ", cleaned)
        cleaned = cleaned.replace("'", "")
        cleaned = _normalize_spaces(cleaned)
        if cleaned != text:
            changes.append(f"cleanup: {text!r} -> {cleaned!r}")
        return cleaned

    def _remove_fillers(self, text: str, changes: list[str]) -> str:
        before = text
        for phrase in FILLER_PHRASES:
            text = _phrase_pattern(phrase).sub(" ", text)
        words = [word for word in text.split() if word not in FILLER_WORDS]
        text = _normalize_spaces(" ".join(words))
        if text != before:
            changes.append(f"fillers: {before!r} -> {text!r}")
        return text

    def _remove_adjacent_repetitions(self, text: str, changes: list[str]) -> str:
        before = text
        words = text.split()
        deduped = []
        for word in words:
            if not deduped or deduped[-1] != word:
                deduped.append(word)
        text = " ".join(deduped)
        text = re.sub(r"\bthe person the ([a-z ]+? person)\b", r"the \1", text)
        text = _normalize_spaces(text)
        if text != before:
            changes.append(f"repetitions: {before!r} -> {text!r}")
        return text

    def _apply_phrase_aliases(self, text: str, changes: list[str]) -> str:
        before = text
        for alias, canonical in sorted(PHRASE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            text = _phrase_pattern(alias).sub(canonical, text)
        text = _normalize_spaces(text)
        if text != before:
            changes.append(f"phrases: {before!r} -> {text!r}")
        return text

    def _replace_exact_entity_aliases(self, text: str, changes: list[str]) -> str:
        before = text
        for alias, canonical in sorted(self.entity_aliases.items(), key=lambda item: len(item[0]), reverse=True):
            if alias == canonical:
                continue
            text = _phrase_pattern(alias).sub(canonical, text)
        text = _normalize_spaces(text)
        if text != before:
            changes.append(f"entities: {before!r} -> {text!r}")
        return text

    def _replace_fuzzy_entities(self, text: str, changes: list[str]) -> str:
        words = text.split()
        output = []
        i = 0
        changed = False

        while i < len(words):
            replacement = None
            replacement_len = 0

            if words[i] in {"a", "an", "the"}:
                output.append(words[i])
                i += 1
                continue

            for span_len in range(min(self.max_entity_words, len(words) - i), 0, -1):
                span = " ".join(words[i : i + span_len])
                if span in self.entity_aliases:
                    continue

                canonical = self._best_entity_match(span, span_len)
                if canonical:
                    replacement = canonical
                    replacement_len = span_len
                    break

            if replacement:
                old = " ".join(words[i : i + replacement_len])
                output.extend(replacement.split())
                changes.append(f"fuzzy entity: {old!r} -> {replacement!r}")
                i += replacement_len
                changed = True
            else:
                output.append(words[i])
                i += 1

        normalized = _normalize_spaces(" ".join(output))
        return normalized if changed else text

    def _best_entity_match(self, span: str, span_len: int) -> str | None:
        if len(span) < 4:
            return None

        best_alias = None
        best_score = 0.0
        for alias in self.entity_aliases:
            alias_len = len(alias.split())
            if alias_len != span_len:
                continue
            score = _similarity(span, alias)
            if score > best_score:
                best_alias = alias
                best_score = score

        threshold = self.fuzzy_threshold
        if span_len > 1:
            threshold -= 0.04

        if best_alias and best_score >= threshold:
            return self.entity_aliases[best_alias]
        return None

    def _build_entities(self) -> list[str]:
        entities = []
        entities.extend(self.knowledge.names)
        entities.extend(self.knowledge.locations)
        entities.extend(self.knowledge.rooms)
        entities.extend(self.knowledge.objects)
        entities.extend(self.knowledge.object_categories_singular)
        entities.extend(self.knowledge.object_categories_plural)
        entities.extend(GESTURE_PERSON_LIST)
        entities.extend(GESTURE_PERSON_PLURAL_LIST)
        entities.extend(POSE_PERSON_LIST)
        entities.extend(POSE_PERSON_PLURAL_LIST)
        entities.extend(PERSON_INFO_LIST)
        entities.extend(OBJECT_COMP_LIST)
        entities.extend(TALK_LIST)
        entities.extend(COLOR_CLOTHE_LIST)
        entities.extend(COLOR_CLOTHES_LIST)

        deduped = {}
        for entity in entities:
            key = _canonical_key(entity)
            if key:
                deduped[key] = entity if entity in self.knowledge.names else key
        return list(deduped.values())

    def _build_entity_aliases(self) -> dict[str, str]:
        aliases = {}
        for entity in self.entities:
            canonical = entity if entity in self.knowledge.names else _canonical_key(entity)
            key = _canonical_key(entity)
            if not key:
                continue

            aliases[key] = canonical
            compact = _compact(entity)
            if compact != key:
                aliases[compact] = canonical

            if key.endswith("s") and len(key) > 4:
                aliases.setdefault(key[:-1], canonical)

        aliases.update(
            {
                "kichen": "kitchen",
                "kit chen": "kitchen",
                "ofice": "office",
                "livin room": "living room",
                "living rom": "living room",
                "bed room": "bedroom",
                "bath room": "bathroom",
                "refridgerator": "refrigerator",
                "fridge": "refrigerator",
                "trash can": "trash bin",
                "trashbin": "trash bin",
                "wastebasket": "waste basket",
                "coat rack": "coatrack",
                "side table": "side tables",
                "apple joos": "apple juice",
                "orange joos": "orange juice",
                "rubik cube": "rubiks cube",
                "rubiks cubes": "rubiks cube",
            }
        )
        return aliases


@lru_cache(maxsize=1)
def get_default_normalizer() -> CommandNormalizer:
    return CommandNormalizer(parse_data(DATA_DIR))


def normalize_command(text: str, return_debug: bool = False):
    return get_default_normalizer().normalize(text, return_debug=return_debug)


if __name__ == "__main__":
    examples = [
        "uh could you go to the the kichen and grab the apple joos",
        "please head to the living_room then look around for Robin",
        "robot pick up the cleanser from the refridgerator",
        "follow the person the waving person in the ofice",
    ]
    for example in examples:
        result = normalize_command(example, return_debug=True)
        print(f"IN : {result.original}")
        print(f"OUT: {result.normalized}")
        print(f"CHG: {result.changes}")
        print("-" * 50)
