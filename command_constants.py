"""Catálogo declarativo de superficies, follow-ups y vocabulario GPSR.

Modificar una frase suele requerir tocar solo ``TEMPLATE_VARIANTS``. Modificar
su significado requiere además un método en ``command_goals.py`` y registrarlo
en ``gpsr_commands.py``. Esta separación evita que una paráfrasis cambie el
label por accidente.
"""

import itertools
import re

# ========================= SURFACE TEMPLATES =========================
# La superficie lingüística vive aquí; la semántica canónica se genera en
# command_goals.py. Cada familia conserva exactamente los mismos slots en sus
# variantes para que una paráfrasis no cambie accidentalmente los goals.
TEMPLATE_VARIANTS = {
    "goToLoc": (
        "{goVerb} {toLocPrep} the {loc_room} then {FOLLOWUP:atLoc}",
        "{goVerb} over {toLocPrep} the {loc_room} and {FOLLOWUP:atLoc}",
        "make your way {toLocPrep} the {loc_room}, then {FOLLOWUP:atLoc}",
    ),
    "takeObjFromPlcmt": (
        "{takeVerb} {art} {obj_singCat} {fromLocPrep} the {plcmtLoc} and {FOLLOWUP:hasObj}",
        "{takeVerb} {art} {obj_singCat} located on the {plcmtLoc}, then {FOLLOWUP:hasObj}",
        "{fromLocPrep} the {plcmtLoc}, {takeVerb} {art} {obj_singCat} and {FOLLOWUP:hasObj}",
    ),
    "findPrsInRoom": (
        "{findVerb} a {gestPers_posePers} {inLocPrep} the {room} and {FOLLOWUP:foundPers}",
        "{inLocPrep} the {room}, {findVerb} the {gestPers_posePers} and {FOLLOWUP:foundPers}",
        "search the {room} for the {gestPers_posePers}, then {FOLLOWUP:foundPers}",
    ),
    "findObjInRoom": (
        "{findVerb} {art} {obj_singCat} {inLocPrep} the {room} then {FOLLOWUP:foundObj}",
        "search the {room} for {art} {obj_singCat} and {FOLLOWUP:foundObj}",
        "{inLocPrep} the {room}, {findVerb} {art} {obj_singCat}, then {FOLLOWUP:foundObj}",
    ),
    "meetPrsAtBeac": (
        "{meetVerb} {name} {inLocPrep} the {room} and {FOLLOWUP:foundPers}",
        "{inLocPrep} the {room}, {meetVerb} {name} and {FOLLOWUP:foundPers}",
        "find {name} {inLocPrep} the {room}, then {FOLLOWUP:foundPers}",
    ),
    "countObjOnPlcmt": (
        "{countVerb} {plurCat} there are {onLocPrep} the {plcmtLoc}",
        "count the {plurCat} {onLocPrep} the {plcmtLoc}",
        "{onLocPrep} the {plcmtLoc}, determine how many {plurCat} there are",
    ),
    "countPrsInRoom": (
        "{countVerb} {gestPersPlur_posePersPlur} are {inLocPrep} the {room}",
        "count the {gestPersPlur_posePersPlur} {inLocPrep} the {room}",
        "{inLocPrep} the {room}, determine how many {gestPersPlur_posePersPlur} there are",
    ),
    "tellPrsInfoInLoc": (
        "{tellVerb} me the {persInfo} of the person {inRoom_atLoc}",
        "find the person {inRoom_atLoc} and report their {persInfo} to me",
        "go to the person {inRoom_atLoc}, learn their {persInfo}, and tell me",
    ),
    "tellObjPropOnPlcmt": (
        "{tellVerb} me what is the {objComp} object {onLocPrep} the {plcmtLoc}",
        "identify the {objComp} object {onLocPrep} the {plcmtLoc} and report it",
        "{onLocPrep} the {plcmtLoc}, find the {objComp} object and tell me",
    ),
    "talkInfoToGestPrsInRoom": (
        "{talkVerb} {talk} {talkPrep} the {gestPers} {inLocPrep} the {room}",
        "find the {gestPers} {inLocPrep} the {room} and {talkVerb} them {talk}",
        "{inLocPrep} the {room}, approach the {gestPers} and {talkVerb} {talk}",
    ),
    "followNameFromBeacToRoom": (
        "{followVerb} {name} {fromLocPrep} the {loc} {toLocPrep} the {room}",
        "meet {name} at the {loc} and {followVerb} them {toLocPrep} the {room}",
        "{fromLocPrep} the {loc}, {followVerb} {name} all the way {toLocPrep} the {room}",
    ),
    "guideNameFromBeacToBeac": (
        "{guideVerb} {name} {fromLocPrep} the {loc} {toLocPrep} the {loc_room}",
        "meet {name} at the {loc}, then {guideVerb} them {toLocPrep} the {loc_room}",
        "{fromLocPrep} the {loc}, {guideVerb} {name} all the way {toLocPrep} the {loc_room}",
    ),
    "guidePrsFromBeacToBeac": (
        "{guideVerb} the {gestPers_posePers} {fromLocPrep} the {loc} {toLocPrep} the {loc_room}",
        "find the {gestPers_posePers} at the {loc} and {guideVerb} them {toLocPrep} the {loc_room}",
        "{fromLocPrep} the {loc}, {guideVerb} the {gestPers_posePers} {toLocPrep} the {loc_room}",
    ),
    "guideClothPrsFromBeacToBeac": (
        "{guideVerb} the person wearing {art} {colorClothe} {fromLocPrep} the {loc} {toLocPrep} the {loc_room}",
        "find the person in {art} {colorClothe} at the {loc} and {guideVerb} them {toLocPrep} the {loc_room}",
        "{fromLocPrep} the {loc}, {guideVerb} whoever is wearing {art} {colorClothe} {toLocPrep} the {loc_room}",
    ),
    "bringMeObjFromPlcmt": (
        "{bringVerb} me {art} {obj} {fromLocPrep} the {plcmtLoc}",
        "{takeVerb} {art} {obj} {fromLocPrep} the {plcmtLoc} and bring it to me",
        "{fromLocPrep} the {plcmtLoc}, fetch {art} {obj} for me",
    ),
    "tellCatPropOnPlcmt": (
        "{tellVerb} me what is the {objComp} {singCat} {onLocPrep} the {plcmtLoc}",
        "identify the {objComp} {singCat} {onLocPrep} the {plcmtLoc} and report it",
        "{onLocPrep} the {plcmtLoc}, find the {objComp} {singCat} and tell me",
    ),
    "greetClothDscInRm": (
        "{greetVerb} the person wearing {art} {colorClothe} {inLocPrep} the {room} and {FOLLOWUP:foundPers}",
        "find the person in {art} {colorClothe} {inLocPrep} the {room}, {greetVerb} them, and {FOLLOWUP:foundPers}",
        "{inLocPrep} the {room}, {greetVerb} whoever is wearing {art} {colorClothe}, then {FOLLOWUP:foundPers}",
    ),
    "greetNameInRm": (
        "{greetVerb} {name} {inLocPrep} the {room} and {FOLLOWUP:foundPers}",
        "find {name} {inLocPrep} the {room}, {greetVerb} them, and {FOLLOWUP:foundPers}",
        "{inLocPrep} the {room}, {greetVerb} {name}, then {FOLLOWUP:foundPers}",
    ),
    "meetNameAtLocThenFindInRm": (
        "{meetVerb} {name} {atLocPrep} the {loc} then {findVerb} them {inLocPrep} the {room}",
        "first {meetVerb} {name} {atLocPrep} the {loc}, then search the {room} for them",
        "go to the {loc} to {meetVerb} {name}; afterwards {findVerb} them {inLocPrep} the {room}",
    ),
    "countClothPrsInRoom": (
        "{countVerb} people {inLocPrep} the {room} are wearing {colorClothes}",
        "count the people wearing {colorClothes} {inLocPrep} the {room}",
        "{inLocPrep} the {room}, determine how many people have {colorClothes}",
    ),
    "tellPrsInfoAtLocToPrsAtLoc": (
        "{tellVerb} the {persInfo} of the person {atLocPrep} the {loc} to the person {atLocPrep} the {loc2}",
        "learn the {persInfo} of the person at the {loc}, then report it to the person at the {loc2}",
        "ask the person at the {loc} for their {persInfo} and tell it to the person at the {loc2}",
    ),
    "followPrsAtLoc": (
        "{followVerb} the {gestPers_posePers} {inRoom_atLoc}",
        "find the {gestPers_posePers} {inRoom_atLoc} and {followVerb} them",
        "go to the {gestPers_posePers} {inRoom_atLoc}, then {followVerb} them",
    ),
    "simpleGoToLoc": (
        "{goVerb} {toLocPrep} the {loc_room}",
        "make your way {toLocPrep} the {loc_room}",
        "head over {toLocPrep} the {loc_room}",
    ),
    "takeObjInRoom": (
        "{goVerb} {toLocPrep} the {loc_room} and {takeVerb} {art} {obj}",
        "{inLocPrep} the {loc_room}, {findVerb} {art} {obj} and {takeVerb} it",
        "head to the {loc_room}, then {takeVerb} {art} {obj}",
    ),
    "answerQuestionOfPersInRoom": (
        "{answerVerb} the question {ofPrsPrep} the {gestPers} {inLocPrep} the {room}",
        "find the {gestPers} {inLocPrep} the {room} and {answerVerb} their question",
        "{inLocPrep} the {room}, approach the {gestPers} and {answerVerb} the question",
    ),
    "bringObjFromTo": (
        "{bringVerb} {art} {obj} {fromLocPrep} the {loc} {toLocPrep} the {loc2}",
        "{takeVerb} {art} {obj} {fromLocPrep} the {loc} and place it at the {loc2}",
        "{fromLocPrep} the {loc}, fetch {art} {obj} and take it {toLocPrep} the {loc2}",
    ),
    # Nuevas coberturas semánticas. Estas familias producen firmas que no
    # existían como comandos completos en el dataset anterior.
    "findNameInRoom": (
        "{findVerb} {name} {inLocPrep} the {room}",
        "{goVerb} {toLocPrep} the {room} then {findVerb} {name}",
        "search the {room} for {name}",
    ),
    "findObjectInRoomSimple": (
        "{findVerb} {art} {obj_singCat} {inLocPrep} the {room}",
        "{goVerb} {toLocPrep} the {room} then {findVerb} {art} {obj_singCat}",
        "search the {room} for {art} {obj_singCat}",
    ),
    "greetNameInRoomSimple": (
        "{greetVerb} {name} {inLocPrep} the {room}",
        "find {name} {inLocPrep} the {room} and {greetVerb} them",
        "{goVerb} {toLocPrep} the {room}, find {name}, and {greetVerb} them",
    ),
}

# Compatibilidad con consumidores antiguos que esperan una sola plantilla.
TEMPLATES = {family: variants[0] for family, variants in TEMPLATE_VARIANTS.items()}


def semantic_surface_fields(template):
    """Extrae solo slots de contenido; ignora elecciones léxicas superficiales."""
    fields = set(re.findall(r"\{([^{}]+)\}", template))
    return frozenset(
        field
        for field in fields
        if field not in {"art", "connector"}
        and not field.endswith("Verb")
        and not field.endswith("Prep")
    )


def validate_template_variants(template_variants=TEMPLATE_VARIANTS):
    """Reporta si una paráfrasis altera los slots semánticos de su familia.

    Se ignoran verbos, preposiciones y artículos porque pertenecen a la
    superficie; nombres, objetos, ubicaciones y FOLLOWUP sí deben coincidir.
    """
    issues = []
    for family, variants in template_variants.items():
        if not 3 <= len(variants) <= 5:
            issues.append(f"{family}: expected 3-5 surface templates")
            continue
        expected = semantic_surface_fields(variants[0])
        for index, variant in enumerate(variants, start=1):
            actual = semantic_surface_fields(variant)
            if actual != expected:
                issues.append(
                    f"{family}:v{index}: semantic fields {sorted(actual)} "
                    f"!= {sorted(expected)}"
                )
    return issues

# Los follow-ups son subórdenes insertadas recursivamente. Su contexto conserva
# ``current_person``/``current_obj`` para que it/them apunten a la misma entidad.
FOLLOWUP_TEMPLATES = {
    "findObj": "{findVerb} {art} {obj_singCat} and {FOLLOWUP:foundObj}",
    "findPrs": "{findVerb} the {gestPers_posePers} and {FOLLOWUP:foundPers}",
    "meetName": "{meetVerb} {name} and {FOLLOWUP:foundPers}",
    "placeObjOnPlcmt": "{placeVerb} it {onLocPrep} the {plcmtLoc2}",
    "putObjInTrash": "throw it in the trash",
    "deliverObjToMe": "{deliverVerb} it to me",
    "deliverObjToPrsInRoom": "{deliverVerb} it {deliverPrep} the {gestPers_posePers} {inLocPrep} the {room}",
    "deliverObjToNameAtBeac": "{deliverVerb} it {deliverPrep} {name} {inLocPrep} the {room}",
    "talkInfo": "{talkVerb} {talk}",
    "followPrs": "{followVerb} them",
    "followPrsToRoom": "{followVerb} them {toLocPrep} the {loc2_room2}",
    "guidePrsToBeacon": "{guideVerb} them {toLocPrep} the {loc2_room2}",
    "takeObj": "{takeVerb} it and {FOLLOWUP:hasObj}",
}

FOLLOWUP_PEOPLE = {
    "atLoc": ["findPrs", "meetName"],
    "foundPers": ["talkInfo", "followPrs", "followPrsToRoom", "guidePrsToBeacon"],
}

FOLLOWUP_OBJECTS = {
    "atLoc": ["findObj"],
    "foundObj": ["takeObj"],
    "hasObj": ["putObjInTrash", "placeObjOnPlcmt", "deliverObjToMe", "deliverObjToPrsInRoom", "deliverObjToNameAtBeac"],
}

PERSON_CMD_LIST = [
    ("goToLoc", 8),
    ("findPrsInRoom", 4),
    ("meetPrsAtBeac", 4),
    ("countPrsInRoom", 1),
    ("tellPrsInfoInLoc", 1),
    ("talkInfoToGestPrsInRoom", 6),
    ("followNameFromBeacToRoom", 1),
    ("guideNameFromBeacToBeac", 1),
    ("guidePrsFromBeacToBeac", 1),
    ("guideClothPrsFromBeacToBeac", 1),
    ("greetClothDscInRm", 1),
    ("greetNameInRm", 4),
    ("meetNameAtLocThenFindInRm", 1),
    ("countClothPrsInRoom", 1),
    ("tellPrsInfoAtLocToPrsAtLoc", 1),
    ("followPrsAtLoc", 1),
    ("simpleGoToLoc", 2),
    ("answerQuestionOfPersInRoom", 1),
    ("findNameInRoom", 2),
    ("greetNameInRoomSimple", 2),
]

OBJECT_CMD_LIST = [
    ("goToLoc", 4),
    ("takeObjFromPlcmt", 2),
    ("findObjInRoom", 2),
    ("countObjOnPlcmt", 1),
    ("tellObjPropOnPlcmt", 1),
    ("bringMeObjFromPlcmt", 1),
    ("tellCatPropOnPlcmt", 1),
    ("bringObjFromTo",2),
    # Esta familia manipula un objeto; mantenerla fuera de PERSON_CMD_LIST
    # permite que PERSON_RATIO represente correctamente ambas categorías.
    ("takeObjInRoom", 2),
    ("findObjectInRoomSimple", 2),
]

# Slots que deben contener entidades diferentes para que la instrucción no
# produzca navegación o búsquedas redundantes. Los slots pueden pertenecer a
# catálogos distintos (por ejemplo loc y room), por eso se comparan por texto.
DISTINCT_SLOT_GROUPS = {
    "followNameFromBeacToRoom": (("loc", "room"),),
    "guideNameFromBeacToBeac": (("loc", "loc_room"),),
    "guidePrsFromBeacToBeac": (("loc", "loc_room"),),
    "guideClothPrsFromBeacToBeac": (("loc", "loc_room"),),
    "meetNameAtLocThenFindInRm": (("loc", "room"),),
    "tellPrsInfoAtLocToPrsAtLoc": (("loc", "loc2"),),
    "bringObjFromTo": (("loc", "loc2"),),
}

VERB_DICT = {
    "takeVerb": ["take", "get", "grasp", "fetch"],
    "placeVerb": ["put", "place"],
    "deliverVerb": ["bring", "give", "deliver"],
    "bringVerb": ["bring", "give"],
    "goVerb": ["go", "navigate"],
    "findVerb": ["find", "locate", "look for"],
    "talkVerb": ["tell", "say"],
    "answerVerb": ["answer"],
    "meetVerb": ["meet"],
    "tellVerb": ["tell"],
    "greetVerb": ["greet", "salute", "say hello to", "introduce yourself to"],
    "rememberVerb": ["meet", "contact", "get to know", "get acquainted with"],
    "countVerb": ["tell me how many"],
    "describeVerb": ["tell me how", "describe"],
    "offerVerb": ["offer"],
    "followVerb": ["follow"],
    "guideVerb": ["guide", "escort", "take", "lead"],
    "accompanyVerb": ["accompany"],
}

PREP_DICT = {
    "deliverPrep": ["to"],
    "placePrep": ["on"],
    "inLocPrep": ["in"],
    "fromLocPrep": ["from"],
    "toLocPrep": ["to"],
    "atLocPrep": ["at"],
    "talkPrep": ["to"],
    "locPrep": ["in", "at"],
    "onLocPrep": ["on"],
    "arePrep": ["are"],
    "ofPrsPrep": ["of"],
}

CONNECTOR_LIST = ["and"]

GESTURE_PERSON_LIST = [
    "waving person",
    "person raising their left arm",
    "person raising their right arm",
    "person pointing to the left",
    "person pointing to the right",
]

POSE_PERSON_LIST = ["sitting person", "standing person", "lying person"]

GESTURE_PERSON_PLURAL_LIST = [
    "waving persons",
    "persons raising their left arm",
    "persons raising their right arm",
    "persons pointing to the left",
    "persons pointing to the right",
]

POSE_PERSON_PLURAL_LIST = ["sitting persons", "standing persons", "lying persons"]

PERSON_INFO_LIST = ["name", "pose", "gesture"]

OBJECT_COMP_LIST = ["biggest", "largest", "smallest", "heaviest", "lightest", "thinnest"]

TALK_LIST = [
    "something about yourself",
    "the time",
    "what day is today",
    "what day is tomorrow",
    "your teams name",
    "your teams country",
    "your teams affiliation",
    "the day of the week",
    "the day of the month",
]

COLOR_LIST = ["blue", "yellow", "black", "white", "red", "orange", "gray"]
CLOTHE_LIST = ["t shirt", "shirt", "blouse", "sweater", "coat", "jacket"]
CLOTHES_LIST = ["t shirts", "shirts", "blouses", "sweaters", "coats", "jackets"]

COLOR_CLOTHE_LIST = [f"{a} {b}" for a, b in itertools.product(COLOR_LIST, CLOTHE_LIST)]
COLOR_CLOTHES_LIST = [f"{a} {b}" for a, b in itertools.product(COLOR_LIST, CLOTHES_LIST)]
