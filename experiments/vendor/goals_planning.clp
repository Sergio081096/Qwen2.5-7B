;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;; GPSR directo desde goals de Qwen
;;
;; Entrada esperada:
;;   (gpsr-goal (step 1) (name go) (target "kitchen") ...)
;;
;; Este archivo mantiene el mismo contrato de salida que gpsr_planning.clp:
;;   plan-note   -> ==Justina GPSR_START/DONE==
;;   ros-message -> Paso N: Justina <accion> <parametros>
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

(deffunction known-person-name (?target)
  (return (or
    (eq ?target "Angel")
    (eq ?target "angel")
    (eq ?target "Charlie")
    (eq ?target "charlie")
    (eq ?target "James")
    (eq ?target "james")
    (eq ?target "John")
    (eq ?target "john")
    (eq ?target "Michael")
    (eq ?target "michael")
    (eq ?target "David")
    (eq ?target "david")
    (eq ?target "Robert")
    (eq ?target "robert")
    (eq ?target "William")
    (eq ?target "william")
    (eq ?target "Daniel")
    (eq ?target "daniel")
    (eq ?target "Matthew")
    (eq ?target "matthew")
    (eq ?target "Morgan")
    (eq ?target "morgan")
    (eq ?target "Sarah")
    (eq ?target "sarah")
    (eq ?target "Emily")
    (eq ?target "emily")
    (eq ?target "Anna")
    (eq ?target "anna")
    (eq ?target "Laura")
    (eq ?target "laura")
    (eq ?target "Simone")
    (eq ?target "simone")
    (eq ?target "Sophia")
    (eq ?target "sophia"))))

(deffunction generic-person-target (?target)
  (return (or
    (eq ?target "")
    (eq ?target "person")
    (eq ?target "user")
    (eq ?target "me")
    (eq ?target "anybody"))))

(deffunction named-person-target (?target)
  (return (not (generic-person-target ?target))))

(deffunction named-person-goal (?target ?kind)
  (return (and
    (named-person-target ?target)
    (or (eq ?kind person) (known-person-name ?target)))))

(deftemplate start
  (slot name))

(deftemplate plan-note
  (slot robot (default Justina))
  (slot state))

(deftemplate gpsr-goal
  (slot step (type INTEGER))
  (slot name)
  (slot target (default ""))
  (slot kind (default unknown))
  (slot destination (default ""))
  (slot relation (default ""))
  (slot value (default ""))
  (slot qualifier (default "")))

(deftemplate current-state
  (slot location (default "unknown"))
  (slot holding (default "nothing")))

(deftemplate manipulation-unavailable
  (slot target))

; ==============================================================
; CONFIGURACION RAPIDA
; Cambia solo esta variable al inicio del archivo:
;   TRUE  -> genera flujo real de manipulacion: take/place/drop/give
;   FALSE -> modo seguro: dice que por el momento no puede tomar objetos
; ==============================================================
(defglobal ?*MANIPULATION_ENABLED* = TRUE)

(deftemplate manipulation-mode
  (slot enabled))

(deftemplate action-step
  (slot step (type INTEGER))
  (slot action)
  (slot arg (default "")))

(deftemplate say-counter
  (slot value (type INTEGER)))

(deftemplate act-counter
  (slot value (type INTEGER)))

(deftemplate person-counter
  (slot value (type INTEGER)))

(deftemplate guest-counter
  (slot value (type INTEGER)))

(deftemplate customer-counter
  (slot value (type INTEGER)))

(deftemplate ros-message
  (slot step (type INTEGER))
  (slot robot (default Justina))
  (slot action)
  (multislot params))

(deftemplate saved-info
  (slot value))

(deftemplate visual-analysis
  (slot target)
  (slot qualifier)
  (slot query)
  (slot answer))

(deftemplate visual-person-found
  (slot target)
  (slot source))

(deftemplate last-person-context
  (slot target)
  (slot source)
  (slot guest-index (default ""))
  (slot customer-index (default "")))

(deftemplate focus-active)

(deftemplate final-steps-added)

(deftemplate planning-ready)

(deffunction clear-manipulation-mode ()
  (bind ?facts (find-all-facts ((?mm manipulation-mode)) TRUE))
  (while (> (length$ ?facts) 0) do
    (retract (nth$ 1 ?facts))
    (bind ?facts (find-all-facts ((?mm manipulation-mode)) TRUE))))

(deffunction set-manipulation-enabled (?enabled)
  (clear-manipulation-mode)
  (if (or (eq ?enabled TRUE) (eq ?enabled true) (eq ?enabled yes) (eq ?enabled enabled) (eq ?enabled on)) then
    (assert (manipulation-mode (enabled TRUE)))
    else
    (assert (manipulation-mode (enabled FALSE)))))

(deffunction manipulation-enabled ()
  (bind ?facts (find-all-facts ((?mm manipulation-mode)) (eq ?mm:enabled TRUE)))
  (return (> (length$ ?facts) 0)))

(deffunction empty-value (?value)
  (return (or (eq ?value "") (eq ?value "unknown"))))

(deffunction object-id (?name)
  (return (str-cat ?name "_1")))

(deffunction person-id (?desc)
  (return (str-cat ?desc "_1")))

(deffunction next-person-id (?desc)
  (bind ?facts (find-all-facts ((?pc person-counter)) TRUE))
  (bind ?counter (nth$ 1 ?facts))
  (bind ?index (fact-slot-value ?counter value))
  (retract ?counter)
  (assert (person-counter (value (+ ?index 1))))
  (return (str-cat ?desc "_" ?index)))

(deffunction next-guest-source ()
  (bind ?facts (find-all-facts ((?gc guest-counter)) TRUE))
  (bind ?counter (nth$ 1 ?facts))
  (bind ?index (fact-slot-value ?counter value))
  (retract ?counter)
  (assert (guest-counter (value (+ ?index 1))))
  (return (str-cat "guest_" ?index)))

(deffunction next-customer-source ()
  (bind ?facts (find-all-facts ((?cc customer-counter)) TRUE))
  (bind ?counter (nth$ 1 ?facts))
  (bind ?index (fact-slot-value ?counter value))
  (retract ?counter)
  (assert (customer-counter (value (+ ?index 1))))
  (return (str-cat "customer_" ?index)))

(deffunction source-index (?source ?prefix)
  (if (eq (str-index ?prefix ?source) 1) then
    (return (sub-string (+ (str-length ?prefix) 1) (str-length ?source) ?source)))
  (return ""))

(deffunction anonymous-person-arg (?source)
  (return (str-cat "anybody_" ?source)))

(deffunction clear-last-person-context ()
  (bind ?facts (find-all-facts ((?lp last-person-context)) TRUE))
  (while (> (length$ ?facts) 0) do
    (retract (nth$ 1 ?facts))
    (bind ?facts (find-all-facts ((?lp last-person-context)) TRUE))))

(deffunction clear-focus-active ()
  (bind ?facts (find-all-facts ((?fa focus-active)) TRUE))
  (while (> (length$ ?facts) 0) do
    (retract (nth$ 1 ?facts))
    (bind ?facts (find-all-facts ((?fa focus-active)) TRUE))))

(deffunction focus-is-active ()
  (bind ?facts (find-all-facts ((?fa focus-active)) TRUE))
  (return (> (length$ ?facts) 0)))

(deffunction remember-last-person (?target ?source ?guest-index ?customer-index)
  (clear-last-person-context)
  (assert (last-person-context
    (target ?target)
    (source ?source)
    (guest-index ?guest-index)
    (customer-index ?customer-index))))

(deffunction customer-source (?source)
  (return (eq (str-index "customer_" ?source) 1)))

(deffunction next-goal-name (?step)
  (bind ?facts (find-all-facts ((?g gpsr-goal)) (> ?g:step ?step)))
  (bind ?best-step 999999)
  (bind ?best-name "")
  (while (> (length$ ?facts) 0) do
    (bind ?fact (nth$ 1 ?facts))
    (bind ?candidate-step (fact-slot-value ?fact step))
    (if (< ?candidate-step ?best-step) then
      (bind ?best-step ?candidate-step)
      (bind ?best-name (fact-slot-value ?fact name)))
    (bind ?facts (rest$ ?facts)))
  (return ?best-name))

(deffunction next-goal-is-talk (?step)
  (bind ?name (next-goal-name ?step))
  (return (or (eq ?name tell) (eq ?name talk))))

(deffunction describe-target (?target ?qualifier)
  (if (neq ?qualifier "") then
    (return (str-cat ?target "_" ?qualifier)))
  (return ?target))

; Normaliza texto libre de Qwen a los destinos que FindSpace/Drop entienden:
; table, container_down/top, shelf(_N) o floor. Si no reconoce la superficie,
; mantiene table como soporte por defecto despues de navegar al lugar pedido.
(deffunction contains-text (?value ?needle)
  (return (neq (str-index ?needle ?value) FALSE)))


; Inferencia contextual: si otro goal del mismo plan usa el mismo target en una
; accion que semanticamente requiere persona, find(X) debe tratar X como persona
; aunque goals_to_clips lo haya marcado como kind unknown.
(deffunction recipient-mentions-target (?value ?target)
  (if (or (empty-value ?value) (empty-value ?target)) then
    (return FALSE))
  (return (or
    (eq ?value ?target)
    (contains-text ?value (str-cat "to=" ?target))
    (contains-text ?value (str-cat "to:" ?target))
    (contains-text ?value (str-cat "to_" ?target))
    (contains-text ?value (str-cat "to " ?target))
    (contains-text ?value (str-cat "person=" ?target))
    (contains-text ?value (str-cat "person:" ?target))
    (contains-text ?value (str-cat "person_" ?target)))))

(deffunction target-is-person-by-plan-context (?target)
  (if (empty-value ?target) then
    (return FALSE))

  ; Acciones donde el target principal es una persona.
  (bind ?direct-context
    (find-all-facts ((?cg gpsr-goal))
      (and
        (eq ?cg:target ?target)
        (or
          (eq ?cg:name guide)
          (eq ?cg:name follow)
          (eq ?cg:name greet)
          (eq ?cg:name meet)
          (eq ?cg:name introduce)))))
  (if (> (length$ ?direct-context) 0) then
    (return TRUE))

  ; Acciones tipo talk/tell/ask solo cuentan como persona si el target aparece
  ; como destinatario, no como informacion a decir. Ejemplos: to=Robin,
  ; destination Robin, value Robin.
  (bind ?recipient-context
    (find-all-facts ((?cg gpsr-goal))
      (and
        (or
          (eq ?cg:name talk)
          (eq ?cg:name tell)
          (eq ?cg:name ask)
          (eq ?cg:name answer))
        (or
          (eq ?cg:destination ?target)
          (eq ?cg:value ?target)
          (recipient-mentions-target ?cg:qualifier ?target)))))
  (return (> (length$ ?recipient-context) 0)))

(deffunction support-name (?value)
  (return (or
    (contains-text ?value "floor")
    (contains-text ?value "suelo")
    (contains-text ?value "table")
    (contains-text ?value "mesa")
    (contains-text ?value "shelf")
    (contains-text ?value "rack")
    (contains-text ?value "cabinet")
    (contains-text ?value "bookcase")
    (contains-text ?value "estante")
    (contains-text ?value "repisa")
    (contains-text ?value "container")
    (contains-text ?value "trash")
    (contains-text ?value "bin")
    (contains-text ?value "box")
    (contains-text ?value "bote")
    (contains-text ?value "basura")
    (contains-text ?value "caja"))))

; Estos nombres son superficies genericas, no puntos de navegacion.
; Ejemplo: table/shelf/rack se usan para FindSpace en el lugar actual.
; En cambio destinos nombrados como storage_rack, dining_table o kitchen_table
; si deben generar go_to antes de buscar espacio y soltar.
(deffunction support-only-destination (?destination)
  (return (or
    (empty-value ?destination)
    (eq ?destination "floor")
    (eq ?destination "suelo")
    (eq ?destination "table")
    (eq ?destination "mesa")
    (eq ?destination "shelf")
    (eq ?destination "shelf_1")
    (eq ?destination "shelf_2")
    (eq ?destination "shelf_3")
    (eq ?destination "rack")
    (eq ?destination "cabinet")
    (eq ?destination "bookcase")
    (eq ?destination "estante")
    (eq ?destination "repisa")
    (eq ?destination "container")
    (eq ?destination "container_down")
    (eq ?destination "container_top")
    (eq ?destination "trash")
    (eq ?destination "bin")
    (eq ?destination "box")
    (eq ?destination "bote")
    (eq ?destination "basura")
    (eq ?destination "caja"))))

(deffunction placement-needs-navigation (?loc ?dest)
  (return (and
    (not (empty-value ?dest))
    (neq ?loc ?dest)
    (not (support-only-destination ?dest)))))

(deffunction table-support (?value)
  (return (or
    (contains-text ?value "table")
    (contains-text ?value "mesa"))))

(deffunction drop-surface (?destination)
  (if (or (contains-text ?destination "floor") (contains-text ?destination "suelo")) then
    (return "floor"))
  (if (contains-text ?destination "shelf_3") then
    (return "shelf_3"))
  (if (contains-text ?destination "shelf_2") then
    (return "shelf_2"))
  (if (contains-text ?destination "shelf_1") then
    (return "shelf_1"))
  (if (or (contains-text ?destination "shelf")
          (contains-text ?destination "rack")
          (contains-text ?destination "cabinet")
          (contains-text ?destination "bookcase")
          (contains-text ?destination "estante")
          (contains-text ?destination "repisa")) then
    (return "shelf"))
  (if (or (contains-text ?destination "container_top")
          (contains-text ?destination "container_high")
          (contains-text ?destination "container_table")
          (contains-text ?destination "encima")
          (contains-text ?destination "sobre_mesa")) then
    (return "container_top"))
  (if (or (contains-text ?destination "container")
          (contains-text ?destination "trash")
          (contains-text ?destination "bin")
          (contains-text ?destination "box")
          (contains-text ?destination "bote")
          (contains-text ?destination "basura")
          (contains-text ?destination "caja")) then
    (return "container_down"))
  (return "table"))

(deffunction destination-phrase (?relation ?destination)
  (if (eq ?destination "") then
    (return ""))
  (if (or (eq ?relation "at") (eq ?relation "in") (eq ?relation "on") (eq ?relation "to")) then
    (return (str-cat " " ?relation " " ?destination)))
  (if (or (contains-text ?destination "container")
          (contains-text ?destination "trash")
          (contains-text ?destination "bin")) then
    (return (str-cat " in " ?destination)))
  (return (str-cat " on " ?destination)))

(deffunction qualifier-value (?qualifier ?prefix ?start-index)
  (if (eq (str-index ?prefix ?qualifier) 1) then
    (return (sub-string ?start-index (str-length ?qualifier) ?qualifier)))
  (return ""))

(deffunction spoken-target (?target ?qualifier)
  (bind ?property (qualifier-value ?qualifier "property:" 10))
  (if (neq ?property "") then
    (return (str-cat "the " ?property " " ?target)))
  (return (describe-target ?target ?qualifier)))

(deffunction normalize-person-attribute (?value)
  (bind ?out "")
  (bind ?i 1)
  (while (<= ?i (str-length ?value)) do
    (bind ?ch (sub-string ?i ?i ?value))
    (if (or (eq ?ch " ") (eq ?ch "-")) then
      (bind ?out (str-cat ?out "_"))
      else
      (if (neq ?ch "'") then
        (bind ?out (str-cat ?out ?ch))))
    (bind ?i (+ ?i 1)))
  (return ?out))

(deffunction normalize-gesture-attribute (?value)
  (bind ?out (normalize-person-attribute ?value))
  (if (contains-text ?out "pointing") then
    (if (contains-text ?out "right") then
      (return "pointing_right"))
    (if (contains-text ?out "left") then
      (return "pointing_left"))
    (return "pointing"))
  (if (or (contains-text ?out "waving") (contains-text ?out "wave")) then
    (return "waving"))
  (if (or (contains-text ?out "raising") (contains-text ?out "raise")) then
    (if (contains-text ?out "right") then
      (return "raising_right"))
    (if (contains-text ?out "left") then
      (return "raising_left"))
    (return "raising"))
  (bind ?suffix "_person")
  (bind ?len (str-length ?out))
  (bind ?slen (str-length ?suffix))
  (if (and (>= ?len ?slen)
           (eq (sub-string (+ (- ?len ?slen) 1) ?len ?out) ?suffix)) then
    (return (sub-string 1 (- ?len ?slen) ?out)))
  (return ?out))

(deffunction describe-person-target (?target ?qualifier)
  (bind ?gesture (qualifier-value ?qualifier "gesture:" 9))
  (if (neq ?gesture "") then
    (return (str-cat ?target " " ?gesture)))
  (return (describe-target ?target ?qualifier)))

; Traduce conteos a AnalyzeObjects para los comandos esperados:
; count(person), count(category). No se generan filtros por color de objetos.
(deffunction count-query (?target ?qualifier ?kind)
  (if (eq ?kind person) then
    (return "count_person"))
  (if (neq ?target "") then
    (return (str-cat "count_" ?target)))
  (return "count_objects"))

; La tool actual de AnalyzeObjects solo tiene extremos por tamaño:
; big/small. Para comandos sin medicion real de peso/grosor usamos proxy visual.
(deffunction size-filter (?qualifier)
  (bind ?property (qualifier-value ?qualifier "property:" 10))
  (if (or (contains-text ?qualifier "biggest")
          (contains-text ?qualifier "largest")
          (contains-text ?property "biggest")
          (contains-text ?property "largest")
          (contains-text ?property "heaviest")) then
    (return "big"))
  (if (or (contains-text ?qualifier "smallest")
          (contains-text ?property "smallest")
          (contains-text ?property "lightest")
          (contains-text ?property "thinnest")) then
    (return "small"))
  (return ""))

(deffunction analyze-object-query (?target ?qualifier ?relation ?value)
  (bind ?filter (size-filter ?qualifier))
  (if (eq ?filter "big") then
    (return (str-cat "biggest_" ?target)))
  (if (eq ?filter "small") then
    (return (str-cat "smallest_" ?target)))
  (return ""))

(deffunction analyze-answer-key (?qualifier)
  (bind ?property (qualifier-value ?qualifier "property:" 10))
  (if (or (contains-text ?qualifier "biggest")
          (contains-text ?property "biggest")
          (contains-text ?property "largest")) then
    (return "biggest_category"))
  (if (contains-text ?property "heaviest") then
    (return "heaviest_category"))
  (if (or (contains-text ?qualifier "smallest")
          (contains-text ?property "smallest")) then
    (return "smallest_category"))
  (if (contains-text ?property "lightest") then
    (return "lightest_category"))
  (if (contains-text ?property "thinnest") then
    (return "thinnest_category"))
  (return ""))

(deffunction talk-answer-key (?info)
  (if (or (eq ?info "about_yourself")
          (eq ?info "current_time")
          (eq ?info "day_today")
          (eq ?info "day_tomorrow")
          (eq ?info "team_name")
          (eq ?info "team_country")
          (eq ?info "team_affiliation")
          (eq ?info "day_of_week")
          (eq ?info "day_of_month")) then
    (return ?info))
  (if (and (contains-text ?info "team") (contains-text ?info "name")) then
    (return "team_name"))
  (if (and (contains-text ?info "team") (contains-text ?info "country")) then
    (return "team_country"))
  (if (and (contains-text ?info "team") (contains-text ?info "affiliation")) then
    (return "team_affiliation"))
  (if (contains-text ?info "yourself") then
    (return "about_yourself"))
  (if (contains-text ?info "time") then
    (return "current_time"))
  (if (contains-text ?info "gesture") then
    (return "gesture_category"))
  (if (and (contains-text ?info "day") (contains-text ?info "tomorrow")) then
    (return "day_tomorrow"))
  (if (and (contains-text ?info "day") (contains-text ?info "today")) then
    (return "day_today"))
  (if (and (contains-text ?info "day") (contains-text ?info "week")) then
    (return "day_of_week"))
  (if (and (contains-text ?info "day") (contains-text ?info "month")) then
    (return "day_of_month"))
  (return ""))

; Texto de pre-plan para respuestas conocidas de talk/tell.
; Evita decir siempre "I will answer the question" cuando ya sabemos
; exactamente que respuesta se va a decir, por ejemplo team_affiliation.
(deffunction talk-intro-text (?answer)
  (if (eq ?answer "team_affiliation") then
    (return "I will announce my teams affiliation"))
  (if (eq ?answer "team_name") then
    (return "I will announce my team name"))
  (if (eq ?answer "team_country") then
    (return "I will announce my team country"))
  (if (eq ?answer "current_time") then
    (return "I will say the current time"))
  (if (eq ?answer "day_today") then
    (return "I will say todays date"))
  (if (eq ?answer "day_tomorrow") then
    (return "I will say tomorrows date"))
  (if (eq ?answer "day_of_week") then
    (return "I will say the day of the week"))
  (if (eq ?answer "day_of_month") then
    (return "I will say the day of the month"))
  (if (eq ?answer "about_yourself") then
    (return "I will introduce myself"))
  (if (eq ?answer "gesture_category") then
    (return "I will tell the gesture"))
  (return "I will answer the question"))

; Respuestas finales que normalmente se dicen mirando a la persona/operador.
; Despues de decirlas se libera el foco para no dejar el robot enganchado.
(deffunction answer-releases-focus (?answer)
  (return (or
    (eq ?answer "about_yourself")
    (eq ?answer "current_time")
    (eq ?answer "day_today")
    (eq ?answer "day_tomorrow")
    (eq ?answer "team_name")
    (eq ?answer "team_country")
    (eq ?answer "team_affiliation")
    (eq ?answer "day_of_week")
    (eq ?answer "day_of_month")
    (eq ?answer "gesture_category")
    (eq ?answer "biggest_category")
    (eq ?answer "heaviest_category")
    (eq ?answer "smallest_category")
    (eq ?answer "lightest_category")
    (eq ?answer "thinnest_category")
    (eq ?answer "count_category")
    (eq ?answer "answer_question")
    (eq ?answer "saved_name")
    (eq ?answer "greet"))))

; Textos separados para guide:
; - append-say describe lo que hara el robot en el pre-plan.
; - guide-start-text se dice a la persona antes de empezar a navegar.
; - guide-finished-text se dice solamente despues de llegar al destino.
(deffunction guide-intro-text (?person ?dest)
  (if (empty-value ?dest) then
    (if (empty-value ?person) then
      (return "I will guide the person")
      else
      (return (str-cat "I will guide " ?person)))
    else
    (if (empty-value ?person) then
      (return (str-cat "I will guide the person to " ?dest))
      else
      (return (str-cat "I will guide " ?person " to " ?dest)))))

(deffunction guide-start-text (?dest)
  (if (empty-value ?dest) then
    (return "Please follow me")
    else
    (return (str-cat "Please follow me to " ?dest))))

(deffunction guide-finished-text (?person ?dest)
  (if (empty-value ?dest) then
    (if (empty-value ?person) then
      (return "I have completed the guide")
      else
      (return (str-cat "I have guided " ?person)))
    else
    (if (empty-value ?person) then
      (return (str-cat "I have guided the person to " ?dest))
      else
      (return (str-cat "I have guided " ?person " to " ?dest)))))

; AnalyzePerson no cuenta personas; localiza personas por atributos visuales.
; wearing:red_shirt -> color_red_shirt, gesture:waving -> gesture_waving.
(deffunction analyze-person-query (?qualifier)
  (bind ?gesture (qualifier-value ?qualifier "gesture:" 9))
  (if (neq ?gesture "") then
    (return (str-cat "gesture_" (normalize-gesture-attribute ?gesture))))
  (bind ?wearing (qualifier-value ?qualifier "wearing:" 9))
  (if (eq ?wearing "") then
    (bind ?wearing (qualifier-value ?qualifier "wearing=" 9)))
  (if (neq ?wearing "") then
    (return (str-cat "color_" (normalize-person-attribute ?wearing))))
  (bind ?pose (qualifier-value ?qualifier "pose:" 6))
  (if (neq ?pose "") then
    (return (str-cat "gesture_" (normalize-gesture-attribute ?pose))))
  (return ""))

; FindPose guarda la navegacion como customer_N. Por eso el indice debe ir
; al final del argumento: waving_1 -> customer_1, gesture_2 -> customer_2.
(deffunction find-pose-query (?qualifier ?customer-index)
  (bind ?gesture (qualifier-value ?qualifier "gesture:" 9))
  (if (neq ?gesture "") then
    (return (str-cat (normalize-gesture-attribute ?gesture) "_" ?customer-index)))
  (bind ?wearing (qualifier-value ?qualifier "wearing:" 9))
  (if (eq ?wearing "") then
    (bind ?wearing (qualifier-value ?qualifier "wearing=" 9)))
  (if (neq ?wearing "") then
    (return (str-cat "color_" (normalize-person-attribute ?wearing) "_" ?customer-index)))
  (bind ?pose (qualifier-value ?qualifier "pose:" 6))
  (if (neq ?pose "") then
    (return (str-cat (normalize-gesture-attribute ?pose) "_" ?customer-index)))
  (return ""))

(deffunction append-action (?action ?arg)
  (bind ?facts (find-all-facts ((?ac act-counter)) TRUE))
  (bind ?counter (nth$ 1 ?facts))
  (bind ?step (fact-slot-value ?counter value))
  (retract ?counter)
  (assert (act-counter (value (+ ?step 1))))
  (if (eq ?action focus) then
    (if (eq ?arg "enable") then
      (clear-focus-active)
      (assert (focus-active))
      else
      (if (eq ?arg "disable") then
        (clear-focus-active))))
  (assert (action-step (step ?step) (action ?action) (arg ?arg))))

(deffunction append-focused-say (?answer)
  (bind ?needs-focus (answer-releases-focus ?answer))

  ; Si la frase necesita foco y aun no esta activo, lo activa.
  ; Si ya venia activo desde una regla anterior, evita repetir focus enable.
  (if (and ?needs-focus (not (focus-is-active))) then
    (append-action focus "enable"))

  (append-action say ?answer)

  ; Despues de una respuesta final, libera el foco.
  (if ?needs-focus then
    (append-action focus "disable")))

; Drop consume object_id para seleccionar mano y el ultimo safe_drop_1 guardado
; por FindSpace. Floor es la excepcion: no necesita FindSpace.
(deffunction append-drop-sequence (?obj ?destination)
  (bind ?surface (drop-surface ?destination))
  (if (eq ?surface "floor") then
    (append-action drop "floor")
    else
    (append-action find_space ?surface)
    (append-action drop (object-id ?obj))))

(deffunction append-say (?text)
  (bind ?facts (find-all-facts ((?sc say-counter)) TRUE))
  (bind ?counter (nth$ 1 ?facts))
  (bind ?step (fact-slot-value ?counter value))
  (retract ?counter)
  (assert (say-counter (value (+ ?step 1))))
  (assert (action-step (step ?step) (action say) (arg ?text))))

(defrule goals-initialize
  (declare (salience 500))
  ?s <- (start (name action-planning))
  (not (plan-note (state GPSR_START)))
  (not (plan-note (state GPSR_DONE)))
  =>
  (retract ?s)
  (assert (say-counter (value 1)))
  (assert (act-counter (value 1001)))
  (assert (person-counter (value 1)))
  (assert (guest-counter (value 1)))
  (assert (customer-counter (value 1)))
  ; Si nadie configuro el modo antes de planear, usar la variable global de arriba.
  ; Para cambiar el default, edita: ?*MANIPULATION_ENABLED* = TRUE/FALSE
  ; Tambien se puede sobrescribir en runtime con: (set-manipulation-enabled TRUE/FALSE)
  (if (= (length$ (find-all-facts ((?mm manipulation-mode)) TRUE)) 0) then
    (assert (manipulation-mode (enabled ?*MANIPULATION_ENABLED*))))
  (assert (current-state (location "unknown") (holding "nothing")))
  (assert (planning-ready))
  (assert (plan-note (robot Justina) (state GPSR_START))))

(defrule process-go
  (declare (salience 200))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name go) (target ?dest))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc) (holding ?held))
  =>
  (retract ?g)
  (if (neq ?loc ?dest) then
    (append-say (str-cat "I will navigate to " ?dest))
    (append-action go_to ?dest)
    (append-action say (str-cat "I have arrived at " ?dest))
    (retract ?st)
    (assert (current-state (location ?dest) (holding ?held)))))

(defrule process-find-person
  (declare (salience 190))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name find) (target ?target) (kind person) (qualifier ?qualifier))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (bind ?desc (describe-person-target ?target ?qualifier))
  (append-say (str-cat "I will look for " ?desc))
  (if (neq (analyze-person-query ?qualifier) "") then
    (bind ?customer (next-customer-source))
    (bind ?customer_index (source-index ?customer "customer_"))
    (append-action find_pose (find-pose-query ?qualifier ?customer_index))
    (append-action approach ?customer)
    (assert (visual-person-found (target ?target) (source ?customer)))
    (remember-last-person ?target ?customer "" ?customer_index)
    else
    (append-action find_person "anybody")
    (assert (visual-person-found (target ?target) (source "guest_last")))
    (remember-last-person ?target "guest_last" "last" ""))
  (append-action focus "enable"))

(defrule process-find-named-person
  (declare (salience 195))
  (planning-ready)
  ?g <- (gpsr-goal
          (step ?step)
          (name find)
          (target ?target)
          (kind ?kind)
          (qualifier ?qualifier))
  (test (named-person-goal ?target ?kind))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (append-say (str-cat "I will look for " ?target))
  (append-action find_person "anybody")
  (assert (visual-person-found (target ?target) (source "guest_last")))
  (remember-last-person ?target "guest_last" "last" "")
  ; La arena no garantiza rostros conocidos: se captura la cara anonima y el
  ; runtime resuelve guest_name_last al guest_N real reportado por find_person.
  (append-action say "ask_name")
  (append-action listen "guest_name_last")
  (append-action focus "enable")
  (append-action say "acknowledge_name_last")
  (if (not (next-goal-is-talk ?step)) then
    (append-action focus "disable")))


(defrule process-find-known-named-person
  (declare (salience 197))
  (planning-ready)
  ?g <- (gpsr-goal
          (step ?step)
          (name find)
          (target ?target)
          (kind ?kind)
          (qualifier ?qualifier))
  (test (named-person-goal ?target ?kind))
  (visual-person-found (target ?target) (source ?source))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (append-say (str-cat "I will look for " ?target))
  ; Si ya se confirmo el nombre en este plan, se reutiliza el ultimo slot
  ; real guardado por FindPerson/Listen en vez de registrar otro anybody.
  (append-action find_person ?source)
  (remember-last-person ?target ?source "last" "")
  (append-action focus "enable")
  (append-action say "acknowledge_name_last")
  (append-action focus "disable"))


(defrule process-find-context-person
  (declare (salience 193))
  (planning-ready)
  ?g <- (gpsr-goal
          (step ?step)
          (name find)
          (target ?target&:(target-is-person-by-plan-context ?target))
          (kind ?kind&~person)
          (qualifier ?qualifier))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (bind ?desc (describe-person-target ?target ?qualifier))
  (append-say (str-cat "I will look for " ?desc))
  (if (neq (analyze-person-query ?qualifier) "") then
    (bind ?customer (next-customer-source))
    (bind ?customer_index (source-index ?customer "customer_"))
    (append-action find_pose (find-pose-query ?qualifier ?customer_index))
    (append-action approach ?customer)
    (assert (visual-person-found (target ?target) (source ?customer)))
    (remember-last-person ?target ?customer "" ?customer_index)
    else
    (append-action find_person "anybody")
    (assert (visual-person-found (target ?target) (source "guest_last")))
    (remember-last-person ?target "guest_last" "last" ""))
  (append-action focus "enable"))

(defrule process-find-object
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name find) (target ?target) (kind ?kind&~person) (qualifier ?qualifier))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  (current-state (location ?loc))
  =>
  (retract ?g)
  (bind ?desc (describe-target ?target ?qualifier))
  (bind ?spoken-desc (spoken-target ?target ?qualifier))
  (append-say (str-cat "I will search for " ?spoken-desc))
  (if (table-support ?loc) then
    (append-action align "table"))
  (bind ?analysis "")
  (bind ?answer "")
  (if (neq ?qualifier "") then
    (bind ?analysis (analyze-object-query ?target ?qualifier "" ""))
    (bind ?answer (analyze-answer-key ?qualifier))
    (if (neq ?analysis "") then
      (append-action analyze_objects ?analysis))
    (if (neq ?answer "") then
      (assert (visual-analysis (target ?target) (qualifier ?qualifier) (query ?analysis) (answer ?answer)))))
  (if (or (eq ?qualifier "") (eq ?analysis "") (eq (str-index "count_" ?analysis) 1)) then
    (append-action find_object (object-id ?target))))

(defrule process-take-enabled
  (declare (salience 181))
  (planning-ready)
  (test (manipulation-enabled))
  ?g <- (gpsr-goal (step ?step) (name take) (target ?obj))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc) (holding ?held))
  =>
  (retract ?g)
  (retract ?st)
  (append-say (str-cat "I will pick up " ?obj))
  ; Si el executor usa otro nombre para tomar objetos, cambia solo esta accion.
  (append-action take (object-id ?obj))
  (append-action say (str-cat "I have picked up " ?obj))
  (assert (current-state (location ?loc) (holding ?obj))))

(defrule process-take-disabled
  (declare (salience 180))
  (planning-ready)
  (test (not (manipulation-enabled)))
  ?g <- (gpsr-goal (step ?step) (name take) (target ?obj))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc) (holding ?held))
  =>
  (retract ?g)
  (retract ?st)
  (append-say (str-cat "I will pick up " ?obj ", but at this moment I cannot pick up objects"))
  ; Manipulation is temporarily disabled. Keep the plan executable by replacing
  ; the take action with speech instead of sending an unsupported arm command.
  (append-action say (str-cat "At this moment I cannot pick up " ?obj))
  (assert (manipulation-unavailable (target ?obj)))
  (assert (current-state (location ?loc) (holding "nothing"))))

(defrule process-place-drop-unavailable
  (declare (salience 196))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name ?name&place|drop) (target ?obj) (destination ?dest))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  (manipulation-unavailable (target ?obj))
  ?st <- (current-state (location ?loc) (holding ?held))
  =>
  (retract ?g)
  (retract ?st)
  (bind ?newloc ?loc)
  (if (placement-needs-navigation ?loc ?dest) then
    (append-say (str-cat "I will navigate to " ?dest))
    (append-action go_to ?dest)
    (bind ?newloc ?dest))
  (append-say (str-cat "I cannot " ?name " " ?obj " because I am not carrying it"))
  (append-action say (str-cat "At this moment I cannot " ?name " " ?obj " because I cannot pick up objects"))
  (assert (current-state (location ?newloc) (holding "nothing"))))

(defrule process-manipulation-dependent-unavailable
  (declare (salience 195))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name ?name&deliver|place|drop) (target ?obj))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  (manipulation-unavailable (target ?obj))
  ?st <- (current-state (location ?loc) (holding ?held))
  =>
  (retract ?g)
  (retract ?st)
  (append-say (str-cat "I cannot " ?name " " ?obj " because I am not carrying it"))
  (append-action say (str-cat "At this moment I cannot " ?name " " ?obj " because I cannot pick up objects"))
  (assert (current-state (location ?loc) (holding "nothing"))))

(defrule process-deliver-to-user
  (declare (salience 190))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name deliver) (target ?obj) (destination ?dest&"me"|"user"|""))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc) (holding ?held))
  =>
  (retract ?g)
  (retract ?st)
  (if (neq ?loc "instruction_point") then
    (append-say "I will return to the instruction point")
    (append-action go_to "instruction_point"))
  (append-say (str-cat "I will deliver " ?obj " to you"))
  (append-action approach "host_1")
  (append-action give (object-id ?obj))
  (append-action say (str-cat "I have delivered " ?obj))
  (assert (current-state (location "instruction_point") (holding "nothing"))))

(defrule process-deliver-to-person
  (declare (salience 185))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name deliver) (target ?obj) (destination ?dest&~"me"&~"user"&~""))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc))
  =>
  (retract ?g)
  (retract ?st)
  (append-say (str-cat "I will deliver " ?obj " to " ?dest))
  (bind ?known (find-all-facts ((?vp visual-person-found)) (eq ?vp:target ?dest)))
  (if (> (length$ ?known) 0) then
    (bind ?found (nth$ 1 ?known))
    (append-action approach (fact-slot-value ?found source))
    else
    (if (known-person-name ?dest) then
      (append-action find_person "anybody")
      (assert (visual-person-found (target ?dest) (source "guest_last")))
      (remember-last-person ?dest "guest_last" "last" "")
      (append-action say "ask_name")
      (append-action listen "guest_name_last")
      (append-action focus "enable")
      (append-action say "acknowledge_name_last")
      (append-action focus "disable")
      (append-action approach "guest_last")
      else
      (append-action find_person (person-id ?dest))
      (append-action approach (person-id ?dest))))
  (append-action give (object-id ?obj))
  (append-action say (str-cat "I have delivered " ?obj))
  (assert (current-state (location ?loc) (holding "nothing"))))

(defrule process-place-drop-not-carrying
  (declare (salience 181))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name ?name&place|drop) (target ?obj) (destination ?dest))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc) (holding ?held&:(neq ?held ?obj)))
  (not (manipulation-unavailable (target ?obj)))
  =>
  (retract ?g)
  (retract ?st)
  (append-say (str-cat "I cannot " ?name " " ?obj " because I am not carrying it"))
  (append-action say (str-cat "I cannot " ?name " " ?obj " because I am not carrying it"))
  (assert (current-state (location ?loc) (holding ?held))))

(defrule process-place
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name place) (target ?obj) (destination ?dest) (relation ?rel))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc) (holding ?obj))
  =>
  (retract ?g)
  (retract ?st)
  (if (placement-needs-navigation ?loc ?dest) then
    (append-say (str-cat "I will navigate to " ?dest))
    (append-action go_to ?dest))
  (append-say (str-cat "I will place " ?obj (destination-phrase ?rel ?dest)))
  (append-drop-sequence ?obj ?dest)
  (append-action say (str-cat "I have placed " ?obj))
  (assert (current-state (location ?dest) (holding "nothing"))))

(defrule process-drop
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name drop) (target ?obj) (destination ?dest) (relation ?rel))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc) (holding ?obj))
  =>
  (retract ?g)
  (retract ?st)
  (if (placement-needs-navigation ?loc ?dest) then
    (append-say (str-cat "I will navigate to " ?dest))
    (append-action go_to ?dest))
  (append-say (str-cat "I will drop " ?obj (destination-phrase ?rel ?dest)))
  (append-drop-sequence ?obj ?dest)
  (append-action say (str-cat "I have dropped " ?obj))
  (assert (current-state (location ?dest) (holding "nothing"))))

(defrule process-guide
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name guide) (target ?person) (destination ?dest))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (holding ?held))
  =>
  (retract ?g)
  (retract ?st)
  (append-say (guide-intro-text ?person ?dest))
  (append-action say (guide-start-text ?dest))
  (append-action go_to ?dest)
  (append-action say (guide-finished-text ?person ?dest))
  (append-action focus "disable")
  (assert (current-state (location ?dest) (holding ?held))))

(defrule process-follow
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name follow) (target ?person) (destination ?dest))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (if (neq ?dest "") then
    (append-say (str-cat "I will follow " ?person " to " ?dest))
    else
    (append-say (str-cat "I will follow " ?person)))
  (bind ?focus_needed TRUE)
  (bind ?known (find-all-facts ((?vp visual-person-found)) (eq ?vp:target ?person)))
  (if (> (length$ ?known) 0) then
    (bind ?found (nth$ 1 ?known))
    (bind ?source (fact-slot-value ?found source))
    (if (not (customer-source ?source)) then
      (append-action approach ?source)
      else
      (bind ?focus_needed FALSE))
    else
    (append-action find_person "anybody")
    (assert (visual-person-found (target ?person) (source "guest_last")))
    (remember-last-person ?person "guest_last" "last" "")
    (if (known-person-name ?person) then
      (append-action say "ask_name")
      (append-action listen "guest_name_last")
      (append-action focus "enable")
      (append-action say "acknowledge_name_last")
      (append-action focus "disable"))
    (append-action approach "guest_last"))
  (if ?focus_needed then
    (append-action focus "enable"))
  (if (neq ?dest "") then
    (append-action say (str-cat "I will follow " ?person " to " ?dest))
    (append-action say (str-cat "instruct_follow_to_" ?dest))
    else
    (append-action say "instruct_follow_only"))
  (append-action focus "disable"))

(defrule process-count
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name count) (target ?target) (qualifier ?qualifier) (kind ?kind))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  ?st <- (current-state (location ?loc) (holding ?held))
  =>
  (retract ?g)
  (retract ?st)
  (bind ?desc (describe-target ?target ?qualifier))
  (append-say (str-cat "I will count " ?desc))
  (append-action analyze_objects (count-query ?target ?qualifier ?kind))
  ; Count answers are normally requested by the operator at the entrance.
  ; Count where the objects are, return to the instruction point, then report.
  (if (neq ?loc "instruction_point") then
    (append-say "I will return to the instruction point to report the count")
    (append-action go_to "instruction_point"))
  (append-action focus "enable")
  (append-action say "count_category")
  (append-action focus "disable")
  (assert (current-state (location "instruction_point") (holding ?held))))

(defrule process-tell
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name tell|talk) (target ?info) (qualifier ?qualifier))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (bind ?talk_intro (talk-answer-key ?info))
  (bind ?answer (analyze-answer-key ?qualifier))
  (bind ?spoken-info (spoken-target ?info ?qualifier))
  (if (contains-text ?info "gesture") then
    (append-say "I will tell the gesture")
    else
    (if (neq ?talk_intro "") then
      (append-say (talk-intro-text ?talk_intro))
    else
      (if (neq ?answer "") then
        (append-say (str-cat "I will report " ?spoken-info))
        else
        (append-say (str-cat "I will tell " ?spoken-info)))))
  (if (neq ?answer "") then
    (bind ?known (find-all-facts ((?va visual-analysis))
      (and (eq ?va:target ?info) (eq ?va:qualifier ?qualifier))))
    (if (= (length$ ?known) 0) then
      (bind ?analysis (analyze-object-query ?info ?qualifier "" ""))
      (append-action analyze_objects ?analysis)
      (assert (visual-analysis (target ?info) (qualifier ?qualifier) (query ?analysis) (answer ?answer))))
	    (append-focused-say ?answer)
	    else
	    (if (eq ?info "name") then
	      (append-action say "saved_name")
	      else
	    (if (neq ?qualifier "") then
	      (append-action say ?qualifier)
	      else
	      (bind ?talk_answer (talk-answer-key ?info))
	      (if (neq ?talk_answer "") then
	        (append-focused-say ?talk_answer)
	        else
	        (append-action say ?info))))))

(defrule process-save
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name save) (target ?info))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (assert (saved-info (value ?info)))
  (if (contains-text ?info "gesture") then
    (append-say "I will save the gesture")
    else
    (append-say (str-cat "I will save " ?info)))
  (if (contains-text ?info "name") then
    (bind ?last (find-all-facts ((?lp last-person-context)) TRUE))
    (if (> (length$ ?last) 0) then
      (bind ?ctx (nth$ 1 ?last))
      (bind ?guest_index (fact-slot-value ?ctx guest-index))
      else
      (bind ?guest_index ""))
	    (if (eq ?guest_index "") then
	      (append-action find_person "anybody")
	      (assert (visual-person-found (target "person") (source "guest_last")))
	      (remember-last-person "person" "guest_last" "last" ""))
	    (append-action say "ask_name")
	    (append-action listen "guest_name_last")
	    (append-action focus "enable")
	    (append-action say "acknowledge_name_last")
	    (append-action focus "disable")
    else
    (if (or (contains-text ?info "gesture") (contains-text ?info "pose")) then
      (bind ?last (find-all-facts ((?lp last-person-context)) TRUE))
      (if (> (length$ ?last) 0) then
        (bind ?ctx (nth$ 1 ?last))
        (bind ?target (fact-slot-value ?ctx target))
        (bind ?customer_index (fact-slot-value ?ctx customer-index))
        else
        (bind ?target "person")
        (bind ?customer_index ""))
      (if (eq ?customer_index "") then
        (bind ?customer (next-customer-source))
        (bind ?customer_index (source-index ?customer "customer_"))
        else
        (bind ?customer (str-cat "customer_" ?customer_index)))
      (if (contains-text ?info "gesture") then
        (append-action say "I will observe the person's gesture")
        ; AnalyzePerson llena analytics.gesture para tell(gesture); FindPose
        ; conserva el customer_N que usa approach/follow.
        (append-action analyze_person "gesture_any")
        (append-action find_pose (str-cat "gesture_" ?customer_index))
        else
        (append-action say "I will observe the person's pose")
        (append-action find_pose (str-cat "pose_" ?customer_index)))
      (assert (visual-person-found (target ?target) (source ?customer)))
      (remember-last-person ?target ?customer "" ?customer_index)
      else
      (append-action say (str-cat "I will remember " ?info)))))

(defrule process-answer-question
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name answer_question))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (append-say "I will answer the question")
  (append-action listen "answer_question")
  (append-action say "answer_question")
  (append-action focus "disable"))

(defrule process-greet
  (declare (salience 180))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name greet) (target ?person))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (append-say (str-cat "I will greet " ?person))
    (bind ?known (find-all-facts ((?vp visual-person-found)) (eq ?vp:target ?person)))
  (if (> (length$ ?known) 0) then
    (bind ?found (nth$ 1 ?known))
    (append-action approach (fact-slot-value ?found source))
    else
    (append-action find_person "anybody")
    (assert (visual-person-found (target ?person) (source "guest_last")))
    (remember-last-person ?person "guest_last" "last" "")
    (if (known-person-name ?person) then
      (append-action say "ask_name")
      (append-action listen "guest_name_last")
      (append-action focus "enable")
      (append-action say "acknowledge_name_last")
      (append-action focus "disable"))
    (append-action approach "guest_last"))
  (append-action focus "enable")
  (append-action say "greet")
  (append-action focus "disable"))

(defrule process-unsupported-goal
  (declare (salience 10))
  (planning-ready)
  ?g <- (gpsr-goal (step ?step) (name ?name) (target ?target))
  (not (gpsr-goal (step ?prev&:(< ?prev ?step))))
  =>
  (retract ?g)
  (append-action say (str-cat "I do not know how to execute goal " ?name " " ?target)))

(defrule add-final-return
  (declare (salience 20))
  (planning-ready)
  (not (gpsr-goal))
  (not (final-steps-added))
  ?st <- (current-state (location ?loc) (holding ?held))
  =>
  (bind ?focus (find-all-facts ((?fa focus-active)) TRUE))
  (if (> (length$ ?focus) 0) then
    (append-action focus "disable"))
  (if (neq ?loc "instruction_point") then
    (append-action go_to "instruction_point"))
  (append-action say "task completed")
  (assert (final-steps-added)))

(defrule serialize-action-step
  (declare (salience 5))
  (planning-ready)
  ?as <- (action-step (step ?step) (action ?action) (arg ?arg))
  (not (gpsr-goal))
  (final-steps-added)
  =>
  (retract ?as)
  (assert (ros-message
    (step ?step)
    (robot Justina)
    (action ?action)
    (params ?arg))))

(defrule goals-finish
  (declare (salience 1))
  (planning-ready)
  (not (gpsr-goal))
  (not (action-step))
  (final-steps-added)
  (not (plan-note (state GPSR_DONE)))
  =>
  (assert (plan-note (robot Justina) (state GPSR_DONE))))
