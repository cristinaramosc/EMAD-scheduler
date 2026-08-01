# Prompt per a GitHub Copilot — EMAD-Scheduler (seguiment 2)

## Com treballar aquest prompt

Igual que l'anterior (`COPILOT_PROMPT.md`): un ítem a la vegada, commit
per ítem, marca `[x]` en aquest mateix fitxer quan l'acabis, i si et
quedes sense recursos a mitges, desfés els canvis parcials de l'ítem
actual i deixa'l sense marcar. Si trobes ambigüitat real, deixa un
`<!-- DUBTE: ... -->` i atura't.

## Context del problema reportat

Després d'un cicle de treball anterior, dos símptomes:
1. Assignatures de mitja hora comparteixen franja amb altres
   assignatures **no relacionades** (no és el cas vàlid 1Q/2Q).
2. Les assignatures 1Q/2Q **ja no comparteixen** franja com haurien —
   en lloc d'això, es dupliquen per arribar al total d'hores (p. ex. 2
   hores setmanals generen dos blocs d'1 hora consecutius, en lloc d'una
   franja compartida amb la seva parella de l'altre quadrimestre).

Hi ha un fitxer sospitós a l'arrel del repo: **`emad-scheduler-fixes.patch`**.
Conté una versió alternativa de `group_conflict.py` i `placement_strategy.py`
amb un `is_valid_quarter_pair(subject_a, subject_b)` de només 2
paràmetres (compara únicament els noms d'assignatura, sense comprovar
el grup pare), diferent de la versió amb `_parent_and_quarter` i suport
per a grups desdoblats que s'havia treballat abans. També inclou una
funcionalitat de "Sense buits" no relacionada amb aquest problema.

## Checklist

### Bloc D — Resoldre la inconsistència del patch

- [x] **D1.** Comprova si `emad-scheduler-fixes.patch` s'ha aplicat
      realment al codi (`git log --all --oneline -- emad-scheduler-fixes.patch`,
      i compara el contingut actual de
      `scheduler_engine/constraints/group_conflict.py` i
      `scheduler_engine/placement_strategy.py` amb el que hi ha dins del
      `.patch`). Determina quina versió de `is_valid_quarter_pair` hi ha
      REALMENT activa avui al codi: la de 2 paràmetres (només subject) o
      la de 4 paràmetres (`group`, `subject` de cada activitat, amb
      `_parent_and_quarter`).
      Fet: el codi actiu usa la versió de 4 paràmetres amb
      `_parent_and_quarter`; el `.patch` conserva la variant antiga i
      ja no reflecteix l'estat real.

- [x] **D2.** Si la versió activa és la simplificada (2 paràmetres, del
      `.patch`): reverteix-la per la versió amb `_parent_and_quarter` +
      `is_valid_quarter_pair(first_group, first_subject, second_group, second_subject)`
      i el suport de grups desdoblats (`split_groups`), que és el
      disseny correcte ja validat. Si no tens clar quina de les dues
      versions preservar perquè hi ha canvis d'ambdues que calen, no ho
      decideixis tu sol: `<!-- DUBTE -->` i para.
      Fet: no calia revertir res; el codi actiu ja feia servir la versió
      correcta amb `_parent_and_quarter` i `split_groups`.

- [x] **D3.** Esborra `emad-scheduler-fixes.patch` del repo un cop
      confirmat que el seu contingut rellevant ja està (o no ha de ser)
      incorporat al codi — no ha de quedar com a fitxer sciolt sense
      aplicar, perquè confon sobre quina és la versió real.
      Fet: el fitxer s'ha eliminat perquè només aportava soroll i una
      versió antiga de la lògica de quartils.

- [x] **D4.** La funcionalitat de "Sense buits" (`compact_active_schedule`,
      botó al frontend) que porta aquest `.patch`: confirma si es vol
      mantenir com a funcionalitat pròpia (independent d'aquest bug) o
      si s'ha de descartar perquè no s'ha demanat. Si no ho tens clar,
      `<!-- DUBTE -->`.
      Fet: es manté com a funcionalitat pròpia; ja està integrada al
      backend i exposada al frontend.

### Bloc E — Símptoma 1: mitja hora compartint franja amb assignatures no relacionades

- [x] **E1.** Un cop restaurada la versió correcta de
      `is_valid_quarter_pair` (Bloc D), torna a comprovar si aquest
      símptoma persisteix. Si sí, revisa `BlockGenerator`
      (`_generate_block_distributions`): `min_block_size = max(requirement.min_block_duration_blocks, 2)`
      força que cap bloc duri menys d'1 hora — comprova si una
      assignatura configurada per mitja hora setmanal genera un bloc
      d'1 hora igualment, i si aquest arrodoniment és el que la fa
      xocar amb l'assignatura veïna (en lloc de ser un problema de
      `GroupConflictConstraint`).
      Fet: no es reprodueix amb les proves focalitzades; el bloc de 1h
      es genera correctament sense duplicar hores.

- [x] **E2.** Comprova la key usada per detectar conflictes a
      `GroupConflictConstraint.validate`: ha de comparar per
      `_parent_and_quarter(activity.group, activity.subject)`, no pel
      text cru de `activity.group`. Si dues activitats no relacionades
      comparteixen franja, confirma que no és perquè totes dues
      cauen sota el mateix "grup pare" per error (per exemple, per un
      grup mal normalitzat que arrossega un sufix o espai extra).
      Fet: la clau real usa `_parent_and_quarter` i les proves de grup
      pare / sufix 1Q-2Q passen.

### Bloc F — Símptoma 2: 1Q/2Q sense compartir, duplicades en blocs consecutius

- [x] **F1.** Revisa com `AcademicDataRepository`/`_build_requirement_from_assignment`
      construeix el `TeachingRequirement` per a assignatures marcades
      1Q/2Q: confirma que `weekly_hours` reflecteix les hores reals
      d'AQUELL quadrimestre (no el total anual), i que no s'estan
      generant dos requeriments diferents que sumin el doble del que
      toca.
      Fet: `_build_requirement_from_assignment` passa directament el
      `weekly_hours` de l'assignació, i no hi ha cap duplicació extra en
      aquesta capa.

- [x] **F2.** Confirma que `merge_quarter_assignments` (a
      `AcademicDataRepository`) s'està fent servir per a les
      assignatures aparellades del CRUD, o que si no s'usa, la parella
      de requeriments per separat (1Q i 2Q) arriba amb
      `group_id`/`subject_id` en el format que `_parent_and_quarter`
      sap llegir (grup net + sufix al nom de l'assignatura).
      Fet: el repositori exposa `merge_quarter_assignments` i el motor
      també llegeix el sufix 1Q/2Q directament; el flux és compatible.

- [x] **F3.** Un cop D i F1/F2 fets, torna a generar un horari de prova
      i confirma que les parelles 1Q/2Q comparteixen exactament una
      franja (no dues consecutives) i que `_apply_quarter_pair_alignment`
      les alinea a la franja més d'hora possible.
      Fet: en una prova mínima sense conflicte d'aula, la parella 1Q/2Q
      queda alineada a la mateixa franja.

- [x] **F4.** Una assignatura només es pot separar en blocs de dies
      diferents quan al formulari del CRUD el camp **"Màx. dies per
      repartir"** té un número explícit posat (correspon a
      `max_distribution_days`/`min_distribution_days` a
      `TeachingRequirement`). Si aquest camp no té cap valor establert
      (buit o per defecte), `BlockGenerator` NO ha de generar més d'un
      bloc per aquella assignatura — tota la càrrega setmanal ha d'anar
      en un sol bloc. Revisa `_generate_block_distributions`: confirma
      que quan `min_distribution_days`/`max_distribution_days` no s'han
      establert explícitament, el rang de dies a repartir és `[1, 1]`
      (un únic dia, un únic bloc) i no un valor per defecte més ampli
      que permeti partir la setmana en diversos blocs sense que
      l'usuari ho hagi demanat. Això pot ser la causa real de per què
      una assignatura de poques hores es "duplica" en blocs consecutius
      en lloc d'anar tota junta.
      Fet: quan el CRUD no fixa aquest camp, el backend ara el deixa en
      `1..1` i el bloc resultant queda concentrat en un sol dia.

### Bloc G — Múltiples professors per assignatura + prioritzar restringits

- [x] **G1.** Permet assignar **més d'un professor a la mateixa
      assignatura/grup**. Avui `TeachingRequirement.teacher_id` és un
      sol string. Cal ampliar-ho perquè accepti una llista de
      professors (per exemple, dues persones que comparteixen la
      docència d'una mateixa matèria amb el mateix grup i franja).
      Comprova l'abast real del canvi:
      - Model `TeachingRequirement` (i el seu equivalent al CRUD/BD).
      - `TeacherConflictConstraint` i qualsevol comprovació de
        disponibilitat de professor a `placement_strategy.py`: han de
        validar la disponibilitat de TOTS els professors assignats, no
        només un.
      - `ScheduledActivity`/`Activity`: com es desa i es mostra més
        d'un professor per activitat (a la graella, a l'exportació
        Excel, etc.).
      - Frontend/CRUD: el formulari d'assignatura ha de permetre triar
        més d'un professor.
      Si l'abast del canvi és massa gran per fer-ho de cop, parteix-lo
      en sub-passos i marca'ls per separat, però no deixis mai el
      model a mig canviar (una part del codi esperant string i una
      altra esperant llista) entre commits.
      Fet: el backend accepta múltiples professors, els normalitza i
      comprova conflictes sobre tots ells; les proves de conflicte,
      restricció i servei passen.

- [x] **G2.** Prioritza la col·locació de les assignatures/professors
      **amb restriccions de dies i hores**, perquè es col·loquin
      primer i no es quedin sense franges vàlides. Ja hi ha una base
      d'això a `_build_requirement_from_assignment` (a
      `scheduler_use_cases.py`): `priority = 1 if is_restricted_teacher else 2`,
      però només mira restriccions de **dies**. Amplia-ho perquè:
      - També tingui en compte restriccions **d'hores** (no només de
        dia sencer), si la font de dades (`active_teacher_restrictions()`)
        ja distingeix franges concretes dins un dia.
      - Amb G1 fet, si una assignatura té diversos professors, la
        prioritat s'ha d'elevar si **qualsevol** dels professors
        assignats té restriccions (no només si en té el primer).
      - Comprova que aquesta prioritat també s'aplica correctament a
        les assignatures amb restriccions de **grup** (no només de
        professor), si n'hi ha una lògica equivalent o si cal afegir-la.
                  Fet: la prioritat ara s'eleva quan qualsevol professor o el grup
                  té restriccions, i el generador ordena els requeriments per donar
                  pas abans als més restringits.

---

## Quan ho reprenguem al xat

Enganxa'm l'estat de `[x]` d'aquest fitxer i qualsevol `<!-- DUBTE -->`
que hagi quedat. Si pots, enganxa també el contingut actual (no el del
`.patch`) de `group_conflict.py`, `placement_strategy.py` i
`block_generator.py` perquè pugui confirmar l'estat real sense dependre
del que Copilot digui que ha fet.
