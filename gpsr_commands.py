"""Orquestador que mantiene alineados texto, contexto y goals GPSR.

``CommandUtilsMixin`` se ocupa de renderizar la superficie y
``CommandGoalsMixin`` transforma el contexto resultante en semántica. La clase
de este archivo es el punto de unión: selecciona familia/variante, reintenta
combinaciones redundantes y valida el plan antes de devolver una muestra.
"""

import random
import warnings

from goal_schema import validate_goals

from command_constants import (
    CLOTHE_LIST,
    CLOTHES_LIST,
    COLOR_CLOTHE_LIST,
    COLOR_CLOTHES_LIST,
    COLOR_LIST,
    CONNECTOR_LIST,
    DISTINCT_SLOT_GROUPS,
    FOLLOWUP_OBJECTS,
    FOLLOWUP_PEOPLE,
    FOLLOWUP_TEMPLATES,
    GESTURE_PERSON_LIST,
    GESTURE_PERSON_PLURAL_LIST,
    OBJECT_CMD_LIST,
    OBJECT_COMP_LIST,
    PERSON_CMD_LIST,
    PERSON_INFO_LIST,
    POSE_PERSON_LIST,
    POSE_PERSON_PLURAL_LIST,
    PREP_DICT,
    TALK_LIST,
    TEMPLATES,
    TEMPLATE_VARIANTS,
    VERB_DICT,
    validate_template_variants,
)
from command_goals import CommandGoalsMixin
from command_utils import CommandUtilsMixin


class CommandGenerator(CommandUtilsMixin, CommandGoalsMixin):
    """Genera pares supervisados ``input``/``goals`` desde catálogos cerrados."""

    def __init__(self, knowledge, debug=False):
        self.knowledge = knowledge
        self.debug = debug

        template_issues = validate_template_variants()
        if template_issues:
            raise ValueError("Invalid surface template catalog: " + "; ".join(template_issues))

        # Se copian los contenedores para que una prueba pueda personalizar una
        # instancia sin modificar los catálogos globales del siguiente test.
        self.templates = TEMPLATES.copy()
        self.template_variants = {
            family: tuple(variants) for family, variants in TEMPLATE_VARIANTS.items()
        }
        self.distinct_slot_groups = DISTINCT_SLOT_GROUPS.copy()
        self.followup_templates = FOLLOWUP_TEMPLATES.copy()
        self.followup_people = FOLLOWUP_PEOPLE.copy()
        self.followup_objects = FOLLOWUP_OBJECTS.copy()
        self.person_cmd_list = PERSON_CMD_LIST.copy()
        self.object_cmd_list = OBJECT_CMD_LIST.copy()
        self.verb_dict = VERB_DICT.copy()
        self.prep_dict = PREP_DICT.copy()
        self.connector_list = CONNECTOR_LIST.copy()
        self.gesture_person_list = GESTURE_PERSON_LIST.copy()
        self.pose_person_list = POSE_PERSON_LIST.copy()
        self.gesture_person_plural_list = GESTURE_PERSON_PLURAL_LIST.copy()
        self.pose_person_plural_list = POSE_PERSON_PLURAL_LIST.copy()
        self.person_info_list = PERSON_INFO_LIST.copy()
        self.object_comp_list = OBJECT_COMP_LIST.copy()
        self.talk_list = TALK_LIST.copy()
        self.color_list = COLOR_LIST.copy()
        self.clothe_list = CLOTHE_LIST.copy()
        self.clothes_list = CLOTHES_LIST.copy()
        self.color_clothe_list = COLOR_CLOTHE_LIST.copy()
        self.color_clothes_list = COLOR_CLOTHES_LIST.copy()

        # Registro explícito familia -> función semántica. Añadir una familia a
        # TEMPLATE_VARIANTS sin registrarla aquí debe considerarse incompleto.
        self.goal_generators = {
            "goToLoc": self._goals_goToLoc,
            "takeObjFromPlcmt": self._goals_takeObjFromPlcmt,
            "findPrsInRoom": self._goals_findPrsInRoom,
            "findObjInRoom": self._goals_findObjInRoom,
            "meetPrsAtBeac": self._goals_meetPrsAtBeac,
            "countObjOnPlcmt": self._goals_countObjOnPlcmt,
            "countPrsInRoom": self._goals_countPrsInRoom,
            "tellPrsInfoInLoc": self._goals_tellPrsInfoInLoc,
            "tellObjPropOnPlcmt": self._goals_tellObjPropOnPlcmt,
            "talkInfoToGestPrsInRoom": self._goals_talkInfoToGestPrsInRoom,
            "followNameFromBeacToRoom": self._goals_followNameFromBeacToRoom,
            "guideNameFromBeacToBeac": self._goals_guideNameFromBeacToBeac,
            "guidePrsFromBeacToBeac": self._goals_guidePrsFromBeacToBeac,
            "guideClothPrsFromBeacToBeac": self._goals_guideClothPrsFromBeacToBeac,
            "bringMeObjFromPlcmt": self._goals_bringMeObjFromPlcmt,
            "tellCatPropOnPlcmt": self._goals_tellCatPropOnPlcmt,
            "greetClothDscInRm": self._goals_greetClothDscInRm,
            "greetNameInRm": self._goals_greetNameInRm,
            "meetNameAtLocThenFindInRm": self._goals_meetNameAtLocThenFindInRm,
            "countClothPrsInRoom": self._goals_countClothPrsInRoom,
            "tellPrsInfoAtLocToPrsAtLoc": self._goals_tellPrsInfoAtLocToPrsAtLoc,
            "followPrsAtLoc": self._goals_followPrsAtLoc,
            # Los follow-ups usan el mismo registro porque también producen
            # goals y pueden encadenar otro follow-up.
            "findObj": self._goals_findObj,
            "findPrs": self._goals_findPrs,
            "meetName": self._goals_meetName,
            "placeObjOnPlcmt": self._goals_placeObjOnPlcmt,
            "putObjInTrash": self._goals_putObjInTrash,
            "deliverObjToMe": self._goals_deliverObjToMe,
            "deliverObjToPrsInRoom": self._goals_deliverObjToPrsInRoom,
            "deliverObjToNameAtBeac": self._goals_deliverObjToNameAtBeac,
            "talkInfo": self._goals_talkInfo,
            "followPrs": self._goals_followPrs,
            "followPrsToRoom": self._goals_followPrsToRoom,
            "guidePrsToBeacon": self._goals_guidePrsToBeacon,
            "takeObj": self._goals_takeObj,

            "simpleGoToLoc": self._goals_simpleGoToLoc,
            "bringObjFromTo": self._goals_bringObjFromTo,
            "answerQuestionOfPersInRoom": self._goals_answerQuestionOfPersInRoom,
            "takeObjInRoom": self._goals_takeObjInRoom,
            "findNameInRoom": self._goals_findNameInRoom,
            "findObjectInRoomSimple": self._goals_findObjectInRoomSimple,
            "greetNameInRoomSimple": self._goals_greetNameInRoomSimple,
        }

    def enumerate_command_variants(
        self, command_key, cmd_category="", include_invalid_combinations=False
    ):
        """Renderiza una muestra determinista por superficie y ruta de follow-up.

        Se usa para descubrir firmas y depurar el catálogo. No intenta enumerar
        el producto cartesiano completo de nombres, objetos y ubicaciones.
        """
        results = []
        for surface_index, template in enumerate(
            self.template_variants[command_key], start=1
        ):
            for text, ctx in self._enumerate_followup_resolutions(
                template, cmd_category, {}
            ):
                if not self._context_satisfies_constraints(command_key, ctx):
                    continue
                self._propagate_context_references(ctx)
                goals = self._generate_goals(command_key, ctx)
                if validate_goals(goals) and not include_invalid_combinations:
                    continue
                results.append(
                    {
                        "input": text,
                        "goals": goals,
                        "surface_template_id": f"{command_key}:v{surface_index}",
                    }
                )
                self._debug_print(f"Variant: {text[:60]}... goals: {goals}")
        return results

    def _context_satisfies_constraints(self, command_key, context):
        """Comprueba origen/destino sobre slots, no sobre palabras renderizadas."""
        for slot_group in self.distinct_slot_groups.get(command_key, ()):
            values = [
                str(context[slot]).strip().casefold()
                for slot in slot_group
                if context.get(slot) is not None
            ]
            if len(values) == len(slot_group) and len(set(values)) != len(values):
                return False
        return True

    def generate_command_start(self, cmd_category="", return_goals=True):
        """Genera una muestra aleatoria válida de la categoría solicitada.

        ``cmd_category`` puede ser ``people``, ``objects`` o vacío. La categoría
        limita familias y follow-ups; ``kind`` todavía queda explícito en goals.
        """
        # 1) Seleccionar una familia respetando los pesos declarados. El
        # balanceador de generate_dataset.py puede forzar esta selección.
        cmd_list = (
            self.person_cmd_list if cmd_category == "people"
            else self.object_cmd_list if cmd_category == "objects"
            else (self.person_cmd_list if random.random() > 0.5 else self.object_cmd_list)
        )
        command_key = self._weighted_choice(cmd_list)
        if command_key not in self.templates:
            print(f"ERROR: Command '{command_key}' not found in templates!")
            # Opcional: muestra las claves disponibles
            print("Available templates:", list(self.templates.keys()))
            warnings.warn("Command not covered: " + command_key)
            return {"input": "WARNING", "goals": []} if return_goals else "WARNING"

        self._debug_print(f"Command selected: {command_key}")
        # 2) Renderizar de nuevo cuando una combinación viola una restricción como
        # origen == destino. No se reescribe el texto después de generarlo: la
        # superficie y los valores semánticos continúan compartiendo el contexto.
        for _ in range(50):
            surface_index = random.randrange(len(self.template_variants[command_key]))
            template = self.template_variants[command_key][surface_index]
            # El mismo contexto recibe los valores usados en la frase y luego
            # alimenta command_goals.py. Esa identidad evita labels desalineados.
            context = {}
            text = self._resolve_followups_with_context(
                template, cmd_category, context, command_key
            )
            self._debug_print("After _resolve_followups, context:", context)
            text = self.insert_all_placeholders_with_context(text, context)
            self._debug_print("After insert_all, context:", context)
            text = self._resolve_duplicates(text, context)
            text = self._fix_articles(text)
            if not self._context_satisfies_constraints(command_key, context):
                continue
            self._propagate_context_references(context)
            goals = self._generate_goals(command_key, context)
            # La validación final también detecta redundancias introducidas en
            # follow-ups anidados que no son visibles en el contexto principal.
            if validate_goals(goals):
                continue
            break
        else:
            warnings.warn(f"Could not satisfy semantic constraints for {command_key}")
            return {"input": "WARNING", "goals": []} if return_goals else "WARNING"

        if return_goals:
            self._debug_print("Generated goals:", goals)
            return {
                "input": text,
                "goals": goals,
                "surface_template_id": f"{command_key}:v{surface_index + 1}",
            }
        else:
            return text
