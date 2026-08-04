import random
import re
import itertools
import warnings
from functools import cached_property

class CommandGenerator:
    def __init__(self, knowledge, debug=False):
        self.knowledge = knowledge
        self.debug = debug
        # -----------------------------
        #  COMMAND TEMPLATES
        # -----------------------------
        self.templates = {
            "goToLoc": "{goVerb} {toLocPrep} the {loc_room} then {FOLLOWUP:atLoc}",
            "takeObjFromPlcmt": "{takeVerb} {art} {obj_singCat} {fromLocPrep} the {plcmtLoc} and {FOLLOWUP:hasObj}",
            "findPrsInRoom": "{findVerb} a {gestPers_posePers} {inLocPrep} the {room} and {FOLLOWUP:foundPers}",
            "findObjInRoom": "{findVerb} {art} {obj_singCat} {inLocPrep} the {room} then {FOLLOWUP:foundObj}",
            "meetPrsAtBeac": "{meetVerb} {name} {inLocPrep} the {room} and {FOLLOWUP:foundPers}",
            "countObjOnPlcmt": "{countVerb} {plurCat} there are {onLocPrep} the {plcmtLoc}",
            "countPrsInRoom": "{countVerb} {gestPersPlur_posePersPlur} are {inLocPrep} the {room}",
            "tellPrsInfoInLoc": "{tellVerb} me the {persInfo} of the person {inRoom_atLoc}",
            "tellObjPropOnPlcmt": "{tellVerb} me what is the {objComp} object {onLocPrep} the {plcmtLoc}",
            "talkInfoToGestPrsInRoom": "{talkVerb} {talk} {talkPrep} the {gestPers} {inLocPrep} the {room}",
            "followNameFromBeacToRoom": "{followVerb} {name} {fromLocPrep} the {loc} {toLocPrep} the {room}",
            "guideNameFromBeacToBeac": "{guideVerb} {name} {fromLocPrep} the {loc} {toLocPrep} the {loc_room}",
            "guidePrsFromBeacToBeac": "{guideVerb} the {gestPers_posePers} {fromLocPrep} the {loc} {toLocPrep} the {loc_room}",
            "guideClothPrsFromBeacToBeac": "{guideVerb} the person wearing {art} {colorClothe} {fromLocPrep} the {loc} {toLocPrep} the {loc_room}",
            "bringMeObjFromPlcmt": "{bringVerb} me {art} {obj} {fromLocPrep} the {plcmtLoc}",
            "tellCatPropOnPlcmt": "{tellVerb} me what is the {objComp} {singCat} {onLocPrep} the {plcmtLoc}",
            "greetClothDscInRm": "{greetVerb} the person wearing {art} {colorClothe} {inLocPrep} the {room} and {FOLLOWUP:foundPers}",
            "greetNameInRm": "{greetVerb} {name} {inLocPrep} the {room} and {FOLLOWUP:foundPers}",
            "meetNameAtLocThenFindInRm": "{meetVerb} {name} {atLocPrep} the {loc} then {findVerb} them {inLocPrep} the {room}",
            "countClothPrsInRoom": "{countVerb} people {inLocPrep} the {room} are wearing {colorClothes}",
            "tellPrsInfoAtLocToPrsAtLoc": "{tellVerb} the {persInfo} of the person {atLocPrep} the {loc} to the person {atLocPrep} the {loc2}",
            "followPrsAtLoc": "{followVerb} the {gestPers_posePers} {inRoom_atLoc}",
        }

        # followup TEMPLATES
        self.followup_templates = {
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

        # ------------------
        # Possible Followups
        # ------------------
        self.followup_people = {
            "atLoc": ["findPrs", "meetName"],
            "foundPers": ["talkInfo", "followPrs", "followPrsToRoom", "guidePrsToBeacon"],
        }

        self.followup_objects = {
            "atLoc": ["findObj"],
            "foundObj": ["takeObj"],
            "hasObj": ["putObjInTrash","placeObjOnPlcmt", "deliverObjToMe", "deliverObjToPrsInRoom","deliverObjToNameAtBeac"], 
        }

        # -----------------------------
        # COMMAND GROUPS with weigths
        # -----------------------------
        self.person_cmd_list = [
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
        ]

        self.object_cmd_list = [
            ("goToLoc", 4),
            ("takeObjFromPlcmt", 2),
            ("findObjInRoom", 2),
            ("countObjOnPlcmt", 1),
            ("tellObjPropOnPlcmt", 1),
            ("bringMeObjFromPlcmt", 1),
            ("tellCatPropOnPlcmt", 1),
        ]

        # =====================================================================
        self.verb_dict = {
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

        self.prep_dict = {
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

        self.connector_list = ["and"]

        self.gesture_person_list = [
            "waving person",
            "person raising their left arm",
            "person raising their right arm",
            "person pointing to the left",
            "person pointing to the right",
        ]
        self.pose_person_list = ["sitting person", "standing person", "lying person"]

        self.gesture_person_plural_list = [
            "waving persons",
            "persons raising their left arm",
            "persons raising their right arm",
            "persons pointing to the left",
            "persons pointing to the right",
        ]
        self.pose_person_plural_list = ["sitting persons", "standing persons", "lying persons"]

        self.person_info_list = ["name", "pose", "gesture"]

        self.object_comp_list = [
            "biggest",
            "largest",
            "smallest",
            "heaviest",
            "lightest",
            "thinnest",
        ]

        self.talk_list = [
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

        self.color_list = ["blue", "yellow", "black", "white", "red", "orange", "gray"]
        self.clothe_list = ["t shirt", "shirt", "blouse", "sweater", "coat", "jacket"]
        self.clothes_list = ["t shirts", "shirts", "blouses", "sweaters", "coats", "jackets"]

        self.color_clothe_list = [f"{a} {b}" for a, b in itertools.product(self.color_list, self.clothe_list)]
        self.color_clothes_list = [f"{a} {b}" for a, b in itertools.product(self.color_list, self.clothes_list)]

        # ===== NUEVO: Diccionario de generadores de metas =====
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
            # Follow‑ups
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
        }

    def _debug_print(self, *args, **kwargs):
        if self.debug:
            print("[DEBUG]", *args, **kwargs)

    def _get_followup_options(self, key, cmd_category):
        if cmd_category == "people":
            return self.followup_people.get(key, [])
        elif cmd_category == "objects":
            return self.followup_objects.get(key, [])
        else:
            return self.followup_people.get(key, []) + self.followup_objects.get(key, [])

    def _insert_placeholder_enum(self, ph, context):
        ph_clean = ph.replace("{", "").replace("}", "")
        ph_raw = ph_clean
        if ph_clean in context:
            return context[ph_clean]

        if "_" in ph_clean:
            ph_clean = ph_clean.split("_")[0]

        value = None
        if ph_clean == "name":
            value = self.knowledge.names[0] if self.knowledge.names else "Alice"
            context["current_person"] = value
        elif ph_clean == "room":
            value = self.knowledge.rooms[0] if self.knowledge.rooms else "kitchen"
        elif ph_clean == "loc":
            value = self.knowledge.locations[0] if self.knowledge.locations else "door"
        elif ph_clean == "plcmtLoc":
            value = self.knowledge.placement_locations[0] if self.knowledge.placement_locations else "table"
        elif ph_clean == "obj":
            value = self.knowledge.objects[0] if self.knowledge.objects else "apple"
            context["current_obj"] = value
        elif ph_clean == "singCat":
            value = self.knowledge.object_categories_singular[0] if self.knowledge.object_categories_singular else "object"
            context["current_obj"] = value
        elif ph_clean == "plurCat":
            value = self.knowledge.object_categories_plural[0] if self.knowledge.object_categories_plural else "objects"
        elif ph_clean == "inRoom":
            prep = self.prep_dict["inLocPrep"][0]
            room = self.knowledge.rooms[0] if self.knowledge.rooms else "kitchen"
            context["inRoom_prep"] = prep
            context["inRoom_room"] = room
            value = f"{prep} the {room}"
        elif ph_clean == "atLoc":
            prep = self.prep_dict["atLocPrep"][0]
            loc = self.knowledge.locations[0] if self.knowledge.locations else "door"
            context["atLoc_prep"] = prep
            context["atLoc_loc"] = loc
            value = f"{prep} the {loc}"
        elif ph_clean == "gestPers":
            value = self.gesture_person_list[0]
            context["current_person"] = f"person, gesture='{value}'"
        elif ph_clean == "posePers":
            value = self.pose_person_list[0]
            context["current_person"] = f"person, pose='{value}'"
        elif ph_clean == "gestPersPlur":
            value = self.gesture_person_plural_list[0]
        elif ph_clean == "posePersPlur":
            value = self.pose_person_plural_list[0]
        elif ph_clean == "persInfo":
            value = self.person_info_list[0]
        elif ph_clean == "objComp":
            value = self.object_comp_list[0]
        elif ph_clean == "talk":
            value = self.talk_list[0]
        elif ph_clean == "colorClothe":
            value = self.color_clothe_list[0]
        elif ph_clean == "colorClothes":
            value = self.color_clothes_list[0]
        elif ph_clean in self.verb_dict:
            value = self.verb_dict[ph_clean][0]
        elif ph_clean in self.prep_dict:
            value = self.prep_dict[ph_clean][0]
        elif ph_clean in ["plcmtLoc2", "room2", "loc2"]:
            value = "{" + ph_clean + "}"
        elif ph_clean == "art":
            value = "{art}"
        else:
            warnings.warn("Placeholder not covered (enum): " + ph_clean)
            value = "UNKNOWN"

        if ph_clean != "art" and "{" not in value:
            context[ph_clean] = value
            if "_" in ph_raw:
                context[ph_raw] = value
        return value

    def _fill_enum_placeholders(self, template, context):
        ctx = context.copy()
        text = template
        for ph in re.findall(r"(\{\w+\})", text):
            value = self._insert_placeholder_enum(ph, ctx)
            text = text.replace(ph, value, 1)
        text = self._resolve_duplicates_enum(text, ctx)  # ahora ctx se llena con loc2, etc.
        text = self._fix_articles(text)
        return text, ctx

    def _resolve_duplicates_enum(self, text, context=None):
        if context is None:
            context = {}
        if "{loc2}" in text:
            alt = next((x for x in self.knowledge.locations if x not in text), self.knowledge.locations[0])
            text = text.replace("{loc2}", alt)
            context["loc2"] = alt
        if "{room2}" in text:
            alt = next((x for x in self.knowledge.rooms if x not in text), self.knowledge.rooms[0])
            text = text.replace("{room2}", alt)
            context["room2"] = alt
        if "{plcmtLoc2}" in text:
            alt = next((x for x in self.knowledge.placement_locations if x not in text), self.knowledge.placement_locations[0])
            text = text.replace("{plcmtLoc2}", alt)
            context["plcmtLoc2"] = alt
        return text

    def _resolve_followups_enum(self, template, cmd_category, context):
        """
        Genera todos los (texto, contexto) posibles al recorrer los FOLLOWUPs.
        """
        match = re.search(r"\{FOLLOWUP:(\w+)\}", template)
        if not match:
            yield self._fill_enum_placeholders(template, context)
            return

        key = match.group(1)
        options = self._get_followup_options(key, cmd_category)
        if not options:
            # eliminar el placeholder y continuar
            new_template = template[:match.start()] + template[match.end():]
            yield from self._resolve_followups_enum(new_template, cmd_category, context)
            return

        for cmd in options:
            sub_ctx = {}
            if "current_obj" in context:
                sub_ctx["current_obj"] = context["current_obj"]
            if "current_person" in context:
                sub_ctx["current_person"] = context["current_person"]

            fu_template = self.followup_templates[cmd]
            # Recursivamente obtener todas las expansiones del follow-up
            for fu_text, fu_ctx in self._resolve_followups_enum(fu_template, cmd_category, sub_ctx):
                # Reemplazar la primera ocurrencia del placeholder
                new_template = template[:match.start()] + fu_text + template[match.end():]
                # Combinar contextos: el del follow-up puede tener más detalles
                merged_ctx = context.copy()
                merged_ctx.update(fu_ctx)
                # Seguimos resolviendo otros FOLLOWUPs que pudieran quedar
                yield from self._resolve_followups_enum(new_template, cmd_category, merged_ctx)

    def _enumerate_followup_resolutions(self, template, cmd_category, context):
        """Generator that yields (text, context) for all possible follow-up choices."""
        match = re.search(r"\{FOLLOWUP:(\w+)\}", template)
        if not match:
            # No more FOLLOWUPs -> resolve remaining placeholders deterministically
            text, ctx = self._fill_enum_placeholders(template, context)
            yield text, ctx
            return

        key = match.group(1)
        options = self._get_followup_options(key, cmd_category)
        if not options:
            # No options available: remove the placeholder and continue
            new_template = template[:match.start()] + template[match.end():]
            yield from self._enumerate_followup_resolutions(new_template, cmd_category, context)
            return

        for cmd in options:
            sub_ctx = {}
            # Inherit current object/person references
            if "current_obj" in context:
                sub_ctx["current_obj"] = context["current_obj"]
            if "current_person" in context:
                sub_ctx["current_person"] = context["current_person"]

            fu_template = self.followup_templates[cmd]
            # Recursively expand the follow-up template
            for fu_text, fu_ctx in self._enumerate_followup_resolutions(fu_template, cmd_category, sub_ctx):
                # Replace the matched placeholder with the expanded follow-up text
                new_template = template[:match.start()] + fu_text + template[match.end():]
                # Merge the follow-up's context into the main one
                merged_ctx = context.copy()
                merged_ctx.update(fu_ctx)
                # Store the follow-up information exactly as the random version does
                merged_ctx[f"followup_{key}"] = {"key": cmd, "context": fu_ctx}
                # Continue resolving any remaining FOLLOWUPs in the rest of the template
                yield from self._enumerate_followup_resolutions(new_template, cmd_category, merged_ctx)

    def enumerate_command_variants(self, command_key, cmd_category=""):
        """Devuelve una lista de dicts con todas las combinaciones posibles."""
        template = self.templates[command_key]
        results = []
        for text, ctx in self._enumerate_followup_resolutions(template, cmd_category, {}):
            self._propagate_context_references(ctx)
            goals = self._generate_goals(command_key, ctx)
            results.append({"input": text, "goals": goals})
            self._debug_print(f"Variant: {text[:60]}... goals: {goals}")
        return results

    # ============================================================
    # GENERACIÓN PRINCIPAL (ahora con metas)
    # ============================================================
    def generate_command_start(self, cmd_category="", return_goals=True):
        cmd_list = (
            self.person_cmd_list if cmd_category == "people"
            else self.object_cmd_list if cmd_category == "objects"
            else (self.person_cmd_list if random.random() > 0.5 else self.object_cmd_list)
        )
        command_key = self._weighted_choice(cmd_list)
        if command_key not in self.templates:
            warnings.warn("Command not covered: " + command_key)
            return {"input": "WARNING", "goals": []} if return_goals else "WARNING"

        self._debug_print(f"Command selected: {command_key}")
        template = self.templates[command_key]
        context = {}
        text = self._resolve_followups_with_context(template, cmd_category, context, command_key)
        self._debug_print("After _resolve_followups, context:", context)
        text = self.insert_all_placeholders_with_context(text, context)
        self._debug_print("After insert_all, context:", context)
        text = self._resolve_duplicates(text, context)
        text = self._fix_articles(text)

        self._propagate_context_references(context)

        if return_goals:
            goals = self._generate_goals(command_key, context)
            self._debug_print("Generated goals:", goals)
            return {"input": text, "goals": goals}
        else:
            return text

    def _resolve_followups_with_context(self, template, cmd_category, context, base_cmd_key=None):
        matches = re.findall(r"\{FOLLOWUP:(\w+)\}", template)
        for key in matches:
            cmd = self._sample_followup(key, cmd_category)
            self._debug_print(f"FOLLOWUP {key} -> {cmd}")
            sub_context = {}
            if "current_obj" in context:
                sub_context["current_obj"] = context["current_obj"]
            if "current_person" in context:
                sub_context["current_person"] = context["current_person"]

            expanded = self._generate_followup_with_context(cmd, cmd_category, sub_context)
            self._debug_print(f"Followup '{cmd}' expanded to: {expanded}")
            self._debug_print(f"Subcontext after expansion: {sub_context}")
            context[f"followup_{key}"] = {"key": cmd, "context": sub_context}
            template = template.replace(f"{{FOLLOWUP:{key}}}", expanded)
        return template

    def _generate_followup_with_context(self, command, cmd_category, sub_context):
        if command not in self.followup_templates:
            warnings.warn("followup_templates not covered: " + command)
            return "WARNING"
        template = self.followup_templates[command]
        template = self._resolve_followups_with_context(template, cmd_category, sub_context, command)
        template = self.insert_all_placeholders_with_context(template, sub_context)
        template = self._resolve_duplicates(template, sub_context)
        return template

    def insert_all_placeholders_with_context(self, string, context):
        # Opcional: puedes activar un debug muy detallado aquí
        self._debug_print("insert_all_placeholders_with_context on:", string[:80])
        for ph in re.findall(r"(\{\w+\})", string):
            value = self._insert_placeholder_with_context(ph, context)
            self._debug_print(f"  {ph} -> {value}")
            string = string.replace(ph, value)
        return string

    def _insert_placeholder_with_context(self, ph, context):
        ph_clean = ph.replace("{", "").replace("}", "")
        # Si ya fue resuelto, devolvemos el valor almacenado
        ph_raw = ph_clean
        if ph_clean in context:
            return context[ph_clean]

        if "_" in ph_clean:
            ph_clean = random.choice(ph_clean.split("_"))

        value = None

        if ph_clean == "name":
            value = random.choice(self.knowledge.names)
            context["current_person"] = value
        elif ph_clean == "room":
            value = random.choice(self.knowledge.rooms)
        elif ph_clean == "loc":
            value = random.choice(self.knowledge.locations)
        elif ph_clean == "plcmtLoc":
            value = random.choice(self.knowledge.placement_locations)
        elif ph_clean == "obj":
            value = random.choice(self.knowledge.objects)
            context["current_obj"] = value
        elif ph_clean == "singCat":
            value = random.choice(self.knowledge.object_categories_singular)
            context["current_obj"] = value
        elif ph_clean == "plurCat":
            value = random.choice(self.knowledge.object_categories_plural)
        elif ph_clean == "inRoom":
            prep = random.choice(self.prep_dict["inLocPrep"])
            room = random.choice(self.knowledge.rooms)
            context["inRoom_prep"] = prep
            context["inRoom_room"] = room
            value = f"{prep} the {room}"
        elif ph_clean == "atLoc":
            prep = random.choice(self.prep_dict["atLocPrep"])
            loc = random.choice(self.knowledge.locations)
            context["atLoc_prep"] = prep
            context["atLoc_loc"] = loc
            value = f"{prep} the {loc}"
        elif ph_clean == "gestPers":
            value = random.choice(self.gesture_person_list)
            context["current_person"] = f"person, gesture='{value}'"
        elif ph_clean == "posePers":
            value = random.choice(self.pose_person_list)
            context["current_person"] = f"person, pose='{value}'"
        elif ph_clean == "gestPersPlur":
            value = random.choice(self.gesture_person_plural_list)
        elif ph_clean == "posePersPlur":
            value = random.choice(self.pose_person_plural_list)
        elif ph_clean == "persInfo":
            value = random.choice(self.person_info_list)
        elif ph_clean == "objComp":
            value = random.choice(self.object_comp_list)
        elif ph_clean == "talk":
            value = random.choice(self.talk_list)
        elif ph_clean == "colorClothe":
            value = random.choice(self.color_clothe_list)
        elif ph_clean == "colorClothes":
            value = random.choice(self.color_clothes_list)
        elif ph_clean == "connector":
            value = random.choice(self.connector_list)
        elif ph_clean in self.verb_dict:
            value = random.choice(self.verb_dict[ph_clean])
        elif ph_clean in self.prep_dict:
            value = random.choice(self.prep_dict[ph_clean])
        elif ph_clean in ["plcmtLoc2", "room2", "loc2"]:
            value = "{" + ph_clean + "}"
        elif ph_clean == "art":
            value = "{art}"
        else:
            warnings.warn("Placeholder not covered: " + ph_clean)
            value = "WARNING"

        if ph_clean != "art" and "{" not in value:
            context[ph_clean] = value
            if "_" in ph_raw:
                context[ph_raw] = value
        return value

    def _generate_goals(self, command_key, context):
        """Invoca el generador de metas correspondiente."""
        if command_key in self.goal_generators:
            self._debug_print(f"Generating goals for {command_key} with context: {context}")
            return self.goal_generators[command_key](context)
        else:
            self._debug_print(f"No goal generator for {command_key}")
            warnings.warn(f"No goal generator for {command_key}")
            return []

    # ============================================================
    # GENERADORES DE METAS PARA CADA PLANTILLA
    # ============================================================
    def _goals_goToLoc(self, ctx):
        loc = ctx.get("loc", ctx.get("room"))
        goals = [f"go({loc})"]
        # Añadir metas del follow‑up "atLoc" si existe
        if "followup_atLoc" in ctx:
            fu = ctx["followup_atLoc"]
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_takeObjFromPlcmt(self, ctx):
        obj = ctx.get("current_obj", "object")
        loc = ctx.get("plcmtLoc")
        goals = [f"go({loc})",f"find({obj})",f"take({obj})"]
        if "followup_hasObj" in ctx:
            fu = ctx["followup_hasObj"]
            fu["context"]["current_obj"] = obj
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_findPrsInRoom(self, ctx):
        person_desc = ctx.get("gestPers", ctx.get("posePers"))
        room = ctx.get("room")
        if "gestPers" in ctx:
            gesture = ctx["gestPers"]
            person = f"person, gesture='{gesture}'"
            goals = [f"go({room})",f"find({person})"]
        elif "posePers" in ctx:
            pose = ctx["posePers"]
            person = f"person, gesture='{pose}'"
            goals = [f"go({room})",f"find({person})"]
        else:
            person = "person"
            goals = [f"go({room})",f"find(person)"]
        ctx["current_person"] = person
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            fu["context"]["current_person"] = person
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_findObjInRoom(self, ctx):
        obj_cat = ctx.get("obj_singCat")
        room = ctx.get("room")
        goals = [f"go({room})",f"find({obj_cat})"]
        ctx["current_obj"] = obj_cat
        if "followup_foundObj" in ctx:
            fu = ctx["followup_foundObj"]
            fu["context"]["current_obj"] = obj_cat
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_meetPrsAtBeac(self, ctx):
        name = ctx.get("name")
        room = ctx.get("room")
        goals = [f"go({room})",f"find({name})"]
        ctx["current_person"] = name
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            fu["context"]["current_person"] = name
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_countObjOnPlcmt(self, ctx):
        cat_plural = ctx.get("plurCat")
        loc = ctx.get("plcmtLoc")
        return [f"go({loc})",f"count({cat_plural})"]

    def _goals_countPrsInRoom(self, ctx):
        desc_plural = ctx.get("gestPersPlur", ctx.get("posePersPlur"))
        room = ctx.get("room")
        if "gestPersPlur" in ctx:
            gesture = ctx["gestPersPlur"]
            return [f"go({room})",f"count(person, gesture='{gesture}')"]
        else:
            pose = ctx["posePersPlur"]
            return [f"go({room})",f"count(person, pose='{pose}')"]

    def _goals_tellPrsInfoInLoc(self, ctx):
        info = ctx.get("persInfo")
        if "inRoom_prep" in ctx:
            loc = ctx["inRoom_room"]
        else:
            loc = ctx.get("atLoc_loc")
        return [f"go({loc})",f"find(person)",f"tell({info})"]

    def _goals_tellObjPropOnPlcmt(self, ctx):
        prop = ctx.get("objComp")
        loc = ctx.get("plcmtLoc")
        return [f"go({loc})",f"find(object,property={prop})",f"tell(object,property={prop})"]

    def _goals_talkInfoToGestPrsInRoom(self, ctx):
        info = ctx.get("talk")
        gesture = ctx.get("gestPers")
        room = ctx.get("room")
        return [f"go({room})",f"find(person, gesture='{gesture}')",f"talk('{info}')"]

    def _goals_followNameFromBeacToRoom(self, ctx):
        name = ctx.get("name")
        loc_from = ctx.get("loc")
        room_to = ctx.get("room")
        return [f"go({loc_from})",f"find({name})",f"follow({name}, to={room_to})"]

    def _goals_guideNameFromBeacToBeac(self, ctx):
        name = ctx.get("name")
        loc_from = ctx.get("loc")
        loc_to = ctx.get("loc_room")
        return [f"go({loc_from})",f"find({name})",f"guide({name}, to={loc_to})"]

    def _goals_guidePrsFromBeacToBeac(self, ctx):
        person_desc = ctx.get("gestPers", ctx.get("posePers"))
        loc_from = ctx.get("loc")
        loc_to = ctx.get("loc_room")
        if "gestPers" in ctx:
            gesture = ctx["gestPers"]
            return [f"go({loc_from})",f"find(person, gesture='{gesture}')",f"guide(person, to={loc_to})"]
        else:
            pose = ctx["posePers"]
            return [f"go({loc_from})",f"find(person, gesture='{pose}')",f"guide(person, to={loc_to})"]

    def _goals_guideClothPrsFromBeacToBeac(self, ctx):
        cloth = ctx.get("colorClothe")
        loc_from = ctx.get("loc")
        loc_to = ctx.get("loc_room")
        return [f"go({loc_from})",f"find(person, wearing='{cloth}')",f"guide(person, to={loc_to})"]

    def _goals_bringMeObjFromPlcmt(self, ctx):
        obj = ctx.get("obj")
        loc = ctx.get("plcmtLoc")
        return [f"go({loc})",f"find({obj})",f"take({obj})",f"drop({obj}, to=me)"]

    def _goals_tellCatPropOnPlcmt(self, ctx):
        prop = ctx.get("objComp")
        cat = ctx.get("singCat")
        loc = ctx.get("plcmtLoc")
        return [f"go({loc})",f"find({cat},property={prop})",f"tell({cat},property={prop})"]

    def _goals_greetClothDscInRm(self, ctx):
        cloth = ctx.get("colorClothe")
        room = ctx.get("room")
        goals = [f"go({room})",f"find(person, wearing='{cloth}')",f"greet(person)"]
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_greetNameInRm(self, ctx):
        name = ctx.get("name")
        room = ctx.get("room")
        goals = [f"go({room})",f"find({name})",f"greet({name})"]
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_meetNameAtLocThenFindInRm(self, ctx):
        name = ctx.get("name")
        loc = ctx.get("loc")
        room = ctx.get("room")
        return [f"go({loc})",f"find({name})",f"go({room})",f"find({name})"]

    def _goals_countClothPrsInRoom(self, ctx):
        clothes = ctx.get("colorClothes")
        room = ctx.get("room")
        return [f"go({room})",f"count(person, wearing='{clothes}')"]

    def _goals_tellPrsInfoAtLocToPrsAtLoc(self, ctx):
        info = ctx.get("persInfo")
        loc1 = ctx.get("loc")
        loc2 = ctx.get("loc2")
        return [f"go({loc1})",f"find(person)","save(name)",f"go({loc2})","find(person)",f"tell({info})"]

    def _goals_followPrsAtLoc(self, ctx):
        person_desc = ctx.get("gestPers", ctx.get("posePers"))
        if "inRoom_room" in ctx:
            loc = ctx["inRoom_room"]
        else:
            loc = ctx.get("atLoc_loc")
        if "gestPers" in ctx:            
            gesture = ctx["gestPers"]
            return [f"go({loc})",f"find(person, gesture='{gesture}')",f"follow(person)"]
        else:
            pose = ctx["posePers"]
            return [f"go({loc})",f"find(person, gesture='{pose}')",f"follow(person)"]

    # Follow‑ups
    def _goals_findObj(self, ctx):
        obj_cat = ctx.get("obj_singCat")
        goals = [f"find({obj_cat})"]
        ctx["current_obj"] = obj_cat
        if "followup_foundObj" in ctx:
            fu = ctx["followup_foundObj"]
            fu["context"]["current_obj"] = obj_cat
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_findPrs(self, ctx):
        # person_desc = ctx.get("gestPers", ctx.get("posePers"))
        if "gestPers" in ctx:
            gesture = ctx["gestPers"]
            person = f"person, gesture='{gesture}'"
        else:
            pose = ctx["posePers"]
            person = f"person, pose='{pose}'"
        goals = [f"find({person})"]
        ctx["current_person"] = person
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            fu["context"]["current_person"] = person
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_meetName(self, ctx):
        name = ctx.get("name")
        goals = [f"find({name})"]
        ctx["current_person"] = name
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            fu["context"]["current_person"] = name
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_placeObjOnPlcmt(self, ctx):
        obj = ctx.get("current_obj", "it")
        loc = ctx.get("plcmtLoc2")
        return [f"place({obj}, on={loc})"]

    def _goals_putObjInTrash(self, ctx):
        obj = ctx.get("current_obj", "it")
        return [f"drop({obj}, in=trash)"]

    def _goals_deliverObjToMe(self, ctx):
        obj = ctx.get("current_obj", "it")
        return [f"deliver({obj}, to=me)"]

    def _goals_deliverObjToPrsInRoom(self, ctx):
        obj = ctx.get("current_obj", "it")
        person = ctx.get("current_person", "person")
        room = ctx.get("room")
        if "gestPers" in ctx:
            gesture = ctx["gestPers"]
            person = f"person, gesture='{gesture}'"
            return [f"go({room})",f"find({person})",f"deliver({obj}, person)"]
        else:
            pose = ctx["posePers"]
            person = f"person, pose='{pose}'"
            return [f"go({room})",f"find({person})",f"deliver({obj}, person)"]

    def _goals_deliverObjToNameAtBeac(self, ctx):
        obj = ctx.get("current_obj", "it")
        name = ctx.get("name")
        room = ctx.get("room")
        return [f"go({room})",f"find({name})",f"deliver({obj}, {name})"]

    def _goals_talkInfo(self, ctx):
        info = ctx.get("talk")
        return [f"talk('{info}')"]

    def _goals_followPrs(self, ctx):
        person = ctx.get("current_person", "person")
        if "person" in person:
            person = "person"
        return [f"follow({person})"]

    def _goals_followPrsToRoom(self, ctx):
        person = ctx.get("current_person", "person")
        loc_to = ctx.get("loc2", ctx.get("room2"))
        if "person" in person:
            person = "person"
        return [f"follow({person}, to={loc_to})"]

    def _goals_guidePrsToBeacon(self, ctx):
        loc_to = ctx.get("loc2", ctx.get("room2"))
        person = ctx.get("current_person", "person")
        if "person" in person:
            person = "person"
        return [f"guide({person}, to={loc_to})"]

    def _goals_takeObj(self, ctx):
        obj = ctx.get("current_obj", "it")
        goals = [f"take({obj})"]
        if "followup_hasObj" in ctx:
            fu = ctx["followup_hasObj"]
            fu["context"]["current_obj"] = obj
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _propagate_context_references(self, context):
        """Recursively copy current_person/obj from parent contexts into nested follow-up contexts."""
        for key, value in context.items():
            if key.startswith("followup_") and isinstance(value, dict) and "context" in value:
                sub_ctx = value["context"]
                if "current_person" in context and "current_person" not in sub_ctx:
                    sub_ctx["current_person"] = context["current_person"]
                if "current_obj" in context and "current_obj" not in sub_ctx:
                    sub_ctx["current_obj"] = context["current_obj"]
                # Recurse into the sub-context in case there are deeper follow-ups
                self._propagate_context_references(sub_ctx)

    def _sample_followup(self, key, cmd_category):
        if cmd_category == "people":
            pool = self.followup_people.get(key, [])
        elif cmd_category == "objects":
            pool = self.followup_objects.get(key, [])
        else:
            pool = self.followup_people.get(key, []) + self.followup_objects.get(key, [])
        if not pool:
            warnings.warn(f"No followups mapped: '{key}' in {cmd_category}")
        return random.choice(pool) if pool else ""

    def _fix_articles(self, text):
        matches = re.findall(r"\{art\}\s*([A-Za-z])", text)
        if matches:
            return text.replace("{art}", "an" if matches[0].lower() in "aeiou" else "a")
        return text

    def _resolve_duplicates(self, text, context=None):
        if context is None:
            context = {}
        if "{loc2}" in text:
            alt = random.choice([x for x in self.knowledge.locations if x not in text])
            text = text.replace("{loc2}", alt)
            context["loc2"] = alt
        if "{room2}" in text:
            alt = random.choice([x for x in self.knowledge.rooms if x not in text])
            text = text.replace("{room2}", alt)
            context["room2"] = alt
        if "{plcmtLoc2}" in text:
            alt = random.choice([x for x in self.knowledge.placement_locations if x not in text])
            text = text.replace("{plcmtLoc2}", alt)
            context["plcmtLoc2"] = alt
        return text

    def _weighted_choice(self, weighted_list):
        items, weights = zip(*weighted_list)
        return random.choices(items, weights=weights, k=1)[0]