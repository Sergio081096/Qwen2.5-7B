"""Conversión del contexto renderizado al contrato canónico de goals.

Este módulo no genera lenguaje natural. Cada método corresponde a una familia
de ``TEMPLATE_VARIANTS`` y debe usar únicamente valores del contexto recibido.
Así se pueden agregar paráfrasis sin duplicar ni alterar la semántica.

Regla central: ``find`` y ``count`` siempre declaran ``kind=person|object``.
"""

import warnings


class CommandGoalsMixin:
    """Implementa una función semántica por familia y por follow-up."""

    def _singular_person_desc(self, desc):
        if not desc:
            return desc
        return desc.replace("persons", "person")

    def _singular_clothing_desc(self, desc):
        if not desc:
            return desc
        for plural, singular in zip(self.clothes_list, self.clothe_list):
            if desc.endswith(plural):
                return desc[: -len(plural)] + singular
        return desc

    def _generate_goals(self, command_key, context):
        """Despacha una familia al generador registrado en CommandGenerator."""
        if command_key in self.goal_generators:
            self._debug_print(f"Generating goals for {command_key} with context: {context}")
            return self.goal_generators[command_key](context)
        else:
            self._debug_print(f"No goal generator for {command_key}")
            warnings.warn(f"No goal generator for {command_key}")
            return []

    # ========== Generadores de metas para cada plantilla ==========
    def _goals_goToLoc(self, ctx):
        loc = ctx.get("loc_room", ctx.get("loc", ctx.get("room")))
        goals = [f"go({loc})"]
        if "followup_atLoc" in ctx:
            fu = ctx["followup_atLoc"]
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_takeObjFromPlcmt(self, ctx):
        obj = ctx.get("current_obj", "object")
        loc = ctx.get("plcmtLoc")
        goals = [f"go({loc})", f"find({obj}, kind=object)", f"take({obj})"]
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
            person = f"person, kind=person, gesture='{gesture}'"
            goals = [f"go({room})", f"find({person})"]
        elif "posePers" in ctx:
            pose = ctx["posePers"]
            person = f"person, kind=person, pose='{pose}'"
            goals = [f"go({room})", f"find({person})"]
        else:
            person = "person"
            goals = [f"go({room})", f"find(person, kind=person)"]
        ctx["current_person"] = person
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            fu["context"]["current_person"] = person
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_findObjInRoom(self, ctx):
        obj_cat = ctx.get("obj_singCat")
        room = ctx.get("room")
        goals = [f"go({room})", f"find({obj_cat}, kind=object)"]
        ctx["current_obj"] = obj_cat
        if "followup_foundObj" in ctx:
            fu = ctx["followup_foundObj"]
            fu["context"]["current_obj"] = obj_cat
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_meetPrsAtBeac(self, ctx):
        name = ctx.get("name")
        room = ctx.get("room")
        goals = [f"go({room})", f"find({name}, kind=person)"]
        ctx["current_person"] = name
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            fu["context"]["current_person"] = name
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_countObjOnPlcmt(self, ctx):
        cat_plural = ctx.get("plurCat")
        loc = ctx.get("plcmtLoc")
        return [f"go({loc})", f"count({cat_plural}, kind=object)"]

    def _goals_countPrsInRoom(self, ctx):
        desc_plural = ctx.get("gestPersPlur", ctx.get("posePersPlur"))
        room = ctx.get("room")
        if "gestPersPlur" in ctx:
            gesture = self._singular_person_desc(ctx["gestPersPlur"])
            return [f"go({room})", f"count(person, kind=person, gesture='{gesture}')"]
        else:
            pose = self._singular_person_desc(ctx["posePersPlur"])
            return [f"go({room})", f"count(person, kind=person, pose='{pose}')"]

    def _goals_tellPrsInfoInLoc(self, ctx):
        info = ctx.get("persInfo")
        if "inRoom_prep" in ctx:
            loc = ctx["inRoom_room"]
        else:
            loc = ctx.get("atLoc_loc")
        # save() obtiene el dato real; después se regresa con el operador para
        # reportarlo. tell() por sí solo no captura nombre, pose ni gesto.
        return [
            f"go({loc})",
            "find(person, kind=person)",
            f"save({info})",
            "go(instruction_point)",
            f"tell({info})",
        ]

    def _goals_tellObjPropOnPlcmt(self, ctx):
        prop = ctx.get("objComp")
        loc = ctx.get("plcmtLoc")
        return [
            f"go({loc})",
            f"find(object, kind=object, property={prop})",
            f"tell(object,property={prop})",
        ]

    def _goals_talkInfoToGestPrsInRoom(self, ctx):
        info = ctx.get("talk")
        gesture = ctx.get("gestPers")
        room = ctx.get("room")
        return [
            f"go({room})",
            f"find(person, kind=person, gesture='{gesture}')",
            f"talk('{info}')",
        ]

    def _goals_followNameFromBeacToRoom(self, ctx):
        name = ctx.get("name")
        loc_from = ctx.get("loc")
        room_to = ctx.get("room")
        return [f"go({loc_from})", f"find({name}, kind=person)", f"follow({name}, to={room_to})"]

    def _goals_guideNameFromBeacToBeac(self, ctx):
        name = ctx.get("name")
        loc_from = ctx.get("loc")
        loc_to = ctx.get("loc_room")
        return [f"go({loc_from})", f"find({name}, kind=person)", f"guide({name}, to={loc_to})"]

    def _goals_guidePrsFromBeacToBeac(self, ctx):
        person_desc = ctx.get("gestPers", ctx.get("posePers"))
        loc_from = ctx.get("loc")
        loc_to = ctx.get("loc_room")
        if "gestPers" in ctx:
            gesture = ctx["gestPers"]
            return [
                f"go({loc_from})",
                f"find(person, kind=person, gesture='{gesture}')",
                f"guide(person, to={loc_to})",
            ]
        else:
            pose = ctx["posePers"]
            return [
                f"go({loc_from})",
                f"find(person, kind=person, pose='{pose}')",
                f"guide(person, to={loc_to})",
            ]

    def _goals_guideClothPrsFromBeacToBeac(self, ctx):
        cloth = ctx.get("colorClothe")
        loc_from = ctx.get("loc")
        loc_to = ctx.get("loc_room")
        return [
            f"go({loc_from})",
            f"find(person, kind=person, wearing='{cloth}')",
            f"guide(person, to={loc_to})",
        ]

    def _goals_bringMeObjFromPlcmt(self, ctx):
        obj = ctx.get("obj")
        loc = ctx.get("plcmtLoc")
        return [
            f"go({loc})",
            f"find({obj}, kind=object)",
            f"take({obj})",
            f"deliver({obj}, to=me)",
        ]

    def _goals_tellCatPropOnPlcmt(self, ctx):
        prop = ctx.get("objComp")
        cat = ctx.get("singCat")
        loc = ctx.get("plcmtLoc")
        return [
            f"go({loc})",
            f"find({cat}, kind=object, property={prop})",
            f"tell({cat},property={prop})",
        ]

    def _goals_greetClothDscInRm(self, ctx):
        cloth = ctx.get("colorClothe")
        room = ctx.get("room")
        goals = [f"go({room})", f"find(person, kind=person, wearing='{cloth}')", f"greet(person)"]
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_greetNameInRm(self, ctx):
        name = ctx.get("name")
        room = ctx.get("room")
        goals = [f"go({room})", f"find({name}, kind=person)", f"greet({name})"]
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_meetNameAtLocThenFindInRm(self, ctx):
        name = ctx.get("name")
        loc = ctx.get("loc")
        room = ctx.get("room")
        return [
            f"go({loc})",
            f"find({name}, kind=person)",
            f"go({room})",
            f"find({name}, kind=person)",
        ]

    def _goals_countClothPrsInRoom(self, ctx):
        clothes = self._singular_clothing_desc(ctx.get("colorClothes"))
        room = ctx.get("room")
        return [f"go({room})", f"count(person, kind=person, wearing='{clothes}')"]

    def _goals_tellPrsInfoAtLocToPrsAtLoc(self, ctx):
        info = ctx.get("persInfo")
        loc1 = ctx.get("loc")
        loc2 = ctx.get("loc2")
        return [
            f"go({loc1})",
            "find(person, kind=person)",
            f"save({info})",
            f"go({loc2})",
            "find(person, kind=person)",
            f"tell({info})",
        ]

    def _goals_followPrsAtLoc(self, ctx):
        if "inRoom_room" in ctx:
            loc = ctx["inRoom_room"]
        else:
            loc = ctx.get("atLoc_loc")
        if "gestPers" in ctx:
            gesture = ctx["gestPers"]
            return [
                f"go({loc})",
                f"find(person, kind=person, gesture='{gesture}')",
                "follow(person)",
            ]
        else:
            pose = ctx["posePers"]
            return [f"go({loc})", f"find(person, kind=person, pose='{pose}')", f"follow(person)"]

    def _goals_simpleGoToLoc(self, ctx):
        loc = ctx.get("loc_room")
        return [f"go({loc})"]

    def _goals_bringObjFromTo(self, ctx):
        obj = ctx.get("obj")
        loc_from = ctx.get("loc")
        loc_to = ctx.get("loc2")
        # El destino es una ubicación general, no necesariamente una superficie.
        # Por eso se usa at= y no on= de forma indiscriminada.
        return [
            f"go({loc_from})",
            f"find({obj}, kind=object)",
            f"take({obj})",
            f"place({obj}, at={loc_to})",
        ]

    def _goals_answerQuestionOfPersInRoom(self, ctx):
        gesture = ctx["gestPers"]
        room = ctx.get("room")
        # Asumimos que la pregunta ya está en el contexto
        return [
            f"go({room})",
            f"find(person, kind=person, gesture='{gesture}')",
            "answer_question()",
        ]

    def _goals_takeObjInRoom(self, ctx):
        loc = ctx.get("loc_room")
        obj = ctx.get("obj")
        return [f"go({loc})", f"find({obj}, kind=object)", f"take({obj})"]

    def _goals_findNameInRoom(self, ctx):
        """Búsqueda simple de una persona conocida: firma go -> find."""
        room = ctx.get("room")
        name = ctx.get("name")
        return [f"go({room})", f"find({name}, kind=person)"]

    def _goals_findObjectInRoomSimple(self, ctx):
        """Búsqueda simple de un objeto/categoría: firma go -> find."""
        room = ctx.get("room")
        obj = ctx.get("obj_singCat")
        return [f"go({room})", f"find({obj}, kind=object)"]

    def _goals_greetNameInRoomSimple(self, ctx):
        """Composición corta sin follow-up implícito: go -> find -> greet."""
        room = ctx.get("room")
        name = ctx.get("name")
        return [
            f"go({room})",
            f"find({name}, kind=person)",
            f"greet({name})",
        ]

    # ========== Follow‑ups ==========
    def _goals_findObj(self, ctx):
        obj_cat = ctx.get("obj_singCat")
        goals = [f"find({obj_cat}, kind=object)"]
        ctx["current_obj"] = obj_cat
        if "followup_foundObj" in ctx:
            fu = ctx["followup_foundObj"]
            fu["context"]["current_obj"] = obj_cat
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_findPrs(self, ctx):
        if "gestPers" in ctx:
            gesture = ctx["gestPers"]
            person = f"person, kind=person, gesture='{gesture}'"
        else:
            pose = ctx["posePers"]
            person = f"person, kind=person, pose='{pose}'"
        goals = [f"find({person})"]
        ctx["current_person"] = person
        if "followup_foundPers" in ctx:
            fu = ctx["followup_foundPers"]
            fu["context"]["current_person"] = person
            goals.extend(self._generate_goals(fu["key"], fu["context"]))
        return goals

    def _goals_meetName(self, ctx):
        name = ctx.get("name")
        goals = [f"find({name}, kind=person)"]
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
        room = ctx.get("room")
        if "gestPers" in ctx:
            gesture = ctx["gestPers"]
            person = f"person, kind=person, gesture='{gesture}'"
            return [f"go({room})", f"find({person})", f"deliver({obj}, person)"]
        else:
            pose = ctx["posePers"]
            person = f"person, kind=person, pose='{pose}'"
            return [f"go({room})", f"find({person})", f"deliver({obj}, person)"]

    def _goals_deliverObjToNameAtBeac(self, ctx):
        obj = ctx.get("current_obj", "it")
        name = ctx.get("name")
        room = ctx.get("room")
        return [f"go({room})", f"find({name}, kind=person)", f"deliver({obj}, {name})"]

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
