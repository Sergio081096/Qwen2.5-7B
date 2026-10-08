"""Renderizado de plantillas con contexto compartido y follow-ups recursivos.

Los métodos ``*_enum`` eligen valores deterministas para inspección. Los demás
muestrean valores aleatorios para el dataset. Ambos escriben los valores en un
diccionario ``context``; ``command_goals.py`` lee después ese mismo diccionario.
"""

import random
import re
import warnings

class CommandUtilsMixin:
    """Utilidades de superficie; no debe decidir la semántica de los goals."""
    def _debug_print(self, *args, **kwargs):
        if self.debug:
            print("[DEBUG]", *args, **kwargs)

    def _get_followup_options(self, key, cmd_category):
        """Restringe follow-ups a la categoría para evitar acciones incompatibles."""
        if cmd_category == "people":
            return self.followup_people.get(key, [])
        elif cmd_category == "objects":
            return self.followup_objects.get(key, [])
        else:
            return self.followup_people.get(key, []) + self.followup_objects.get(key, [])

    def _insert_placeholder_enum(self, ph, context):
        """Resuelve un placeholder de forma determinista para enumeración."""
        ph_clean = ph.replace("{", "").replace("}", "")
        ph_raw = ph_clean
        if ph_clean in context:
            return context[ph_clean]

        # En enumeración, loc_room representa el mismo slot semántico pero
        # puede tomar valores de ambos catálogos. Elegir un valor diferente al
        # origen permite enumerar familias de transporte con restricciones.
        if ph_clean == "loc_room":
            candidates = [*self.knowledge.locations, *self.knowledge.rooms]
            value = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.casefold()
                    != str(context.get("loc", "")).casefold()
                ),
                candidates[0] if candidates else "kitchen",
            )
            context[ph_raw] = value
            return value

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
            if ph_clean not in context:
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
        text = self._resolve_duplicates_enum(text, ctx)
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
        match = re.search(r"\{FOLLOWUP:(\w+)\}", template)
        if not match:
            yield self._fill_enum_placeholders(template, context)
            return

        key = match.group(1)
        options = self._get_followup_options(key, cmd_category)
        if not options:
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
            for fu_text, fu_ctx in self._resolve_followups_enum(fu_template, cmd_category, sub_ctx):
                new_template = template[:match.start()] + fu_text + template[match.end():]
                merged_ctx = context.copy()
                merged_ctx.update(fu_ctx)
                yield from self._resolve_followups_enum(new_template, cmd_category, merged_ctx)

    def _enumerate_followup_resolutions(self, template, cmd_category, context):
        match = re.search(r"\{FOLLOWUP:(\w+)\}", template)
        if not match:
            text, ctx = self._fill_enum_placeholders(template, context)
            yield text, ctx
            return

        key = match.group(1)
        options = self._get_followup_options(key, cmd_category)
        if not options:
            new_template = template[:match.start()] + template[match.end():]
            yield from self._enumerate_followup_resolutions(new_template, cmd_category, context)
            return

        for cmd in options:
            sub_ctx = {}
            if "current_obj" in context:
                sub_ctx["current_obj"] = context["current_obj"]
            if "current_person" in context:
                sub_ctx["current_person"] = context["current_person"]

            fu_template = self.followup_templates[cmd]
            for fu_text, fu_ctx in self._enumerate_followup_resolutions(fu_template, cmd_category, sub_ctx):
                new_template = template[:match.start()] + fu_text + template[match.end():]
                merged_ctx = context.copy()
                merged_ctx.update(fu_ctx)
                merged_ctx[f"followup_{key}"] = {"key": cmd, "context": fu_ctx}
                yield from self._enumerate_followup_resolutions(new_template, cmd_category, merged_ctx)

    def _resolve_followups_with_context(self, template, cmd_category, context, base_cmd_key=None):
        """Expande marcadores FOLLOWUP y conserva su subcontexto semántico.

        Cada follow-up recibe un subcontexto propio para evitar colisiones de
        slots como ``room`` y ``room2``. La referencia se guarda bajo
        ``followup_<key>`` para reconstruir la misma cadena en los goals.
        """
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
        """Sustituye placeholders y registra cada valor elegido en ``context``."""
        self._debug_print("insert_all_placeholders_with_context on:", string[:80])
        for ph in re.findall(r"(\{\w+\})", string):
            value = self._insert_placeholder_with_context(ph, context)
            self._debug_print(f"  {ph} -> {value}")
            string = string.replace(ph, value)
        return string

    def _insert_placeholder_with_context(self, ph, context):
        ph_clean = ph.replace("{", "").replace("}", "")
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
            if ph_clean not in context:
                context[ph_clean] = value
            if "_" in ph_raw:
                context[ph_raw] = value
        return value

    def _fix_articles(self, text):
        matches = re.findall(r"\{art\}\s*([A-Za-z])", text)
        if matches:
            return text.replace("{art}", "an" if matches[0].lower() in "aeiou" else "a")
        return text

    def _resolve_duplicates(self, text, context=None):
        """Resuelve slots diferidos ``*2`` evitando repetir entidades del texto."""
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

    def _propagate_context_references(self, context):
        """Propaga la entidad actual a follow-ups que usan pronombres como it/them."""
        for key, value in context.items():
            if key.startswith("followup_") and isinstance(value, dict) and "context" in value:
                sub_ctx = value["context"]
                if "current_person" in context and "current_person" not in sub_ctx:
                    sub_ctx["current_person"] = context["current_person"]
                if "current_obj" in context and "current_obj" not in sub_ctx:
                    sub_ctx["current_obj"] = context["current_obj"]
                self._propagate_context_references(sub_ctx)
