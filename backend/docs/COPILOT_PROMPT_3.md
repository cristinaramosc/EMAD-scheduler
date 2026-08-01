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
      `_parent_and_quarter`; el `.patch` ja no existeix al workspace i
      la història de git només en conserva el rastre.

- [x] **D2.** Si la versió activa és la simplificada (2 paràmetres, del
      `.patch`): reverteix-la per la versió amb `_parent_and_quarter` +
      `is_valid_quarter_pair(first_group, first_subject, second_group, second_subject)`
      i el suport de grups desdoblats (`split_groups`), que és el
      disseny correcte ja validat. Si no tens clar quina de les dues
      versions preservar perquè hi ha canvis d'ambdues que calen, no ho
      decideixis tu sol: `<!-- DUBTE -->` i para.
      Fet: no calia revertir res; la versió activa ja era la correcta.

- [x] **D3.** Esborra `emad-scheduler-fixes.patch` del repo un cop
      confirmat que el seu contingut rellevant ja està (o no ha de ser)
      incorporat al codi — no ha de quedar com a fitxer sciolt sense
      aplicar, perquè confon sobre quina és la versió real.
      Fet: el fitxer no és present al workspace.

- [x] **D4.** La funcionalitat de "Sense buits" (`compact_active_schedule`,
      botó al frontend) que porta aquest `.patch`: confirma si es vol
      mantenir com a funcionalitat pròpia (independent d'aquest bug) o
      si s'ha de descartar perquè no s'ha demanat. Si no ho tens clar,
      `<!-- DUBTE -->`.
      Fet: es manté com a funcionalitat pròpia; el backend i el frontend
      encara exposen el flux de compactació.

### Bloc E — Símptoma 1: mitja hora compartint franja amb assignatures no relacionades

 [x] **E1.** Un cop restaurada la versió correcta de
      `is_valid_quarter_pair` (Bloc D), torna a comprovar si aquest
      símptoma persisteix. Si sí, revisa `BlockGenerator`
      (`_generate_block_distributions`): `min_block_size = max(requirement.min_block_duration_blocks, 2)`
      força que cap bloc duri menys d'1 hora — comprova si una
      assignatura configurada per mitja hora setmanal genera un bloc
      d'1 hora igualment, i si aquest arrodoniment és el que la fa
      xocar amb l'assignatura veïna (en lloc de ser un problema de
      `GroupConflictConstraint`).
       Fet: les proves focalitzades mostren que no es generen blocs de
       mitja hora i que els blocs totals es conserven correctament.

 [x] **E2.** Comprova la key usada per detectar conflictes a
      `GroupConflictConstraint.validate`: ha de comparar per
      `_parent_and_quarter(activity.group, activity.subject)`, no pel
      text cru de `activity.group`. Si dues activitats no relacionades
      comparteixen franja, confirma que no és perquè totes dues
      cauen sota el mateix "grup pare" per error (per exemple, per un
      grup mal normalitzat que arrossega un sufix o espai extra).
       Fet: la key de conflicte fa servir `_parent_and_quarter` i les
       proves de grup pare / sufix 1Q-2Q passen.

 [x] **E3.** Evidència addicional (captura de pantalla del frontend,
      grup 1r APGI): a les 9:00, totes les columnes de dies mostren una
      barra grisa d'amplada completa amb botons "Info"/"Elimina", en
      lloc d'una franja normal d'assignatura. Investiga si aquesta
      barra grisa correspon a una `Activity` real amb assignatura (i,
      si és així, per què es renderitza diferent — potser el frontend
      la marca com "conflicte"/"solapament" i per això la pinta grisa i
      amb l'opció d'eliminar-la), o si en realitat és una entrada de
      restricció/franja bloquejada mal renderitzada com si fos una
      activitat. Comprova el component del frontend que decideix quan
      pintar una cel·la en gris amb "Elimina" (probablement lligat a
      `conflicts` que retorna el backend) — si totes les assignatures
      de mitja hora del grup acaben marcades com a conflicte a les
      9:00, la causa és molt probablement la mateixa que E1/E2, però
      confirma-ho mirant si el conflicte reportat pel backend
      (`GroupConflictConstraint`) inclou aquestes activitats concretes.
       Fet: la barra correspon a una activitat real `Descans` de
       `1r APGI`; el frontend la pinta amb la classe de descans i el
       backend la genera com a descans inserit.

### Bloc F — Símptoma 2: 1Q/2Q sense compartir, duplicades en blocs consecutius

- [x] **F1.** Revisa com `AcademicDataRepository`/`_build_requirement_from_assignment`
      construeix el `TeachingRequirement` per a assignatures marcades
      1Q/2Q: confirma que `weekly_hours` reflecteix les hores reals
      d'AQUELL quadrimestre (no el total anual), i que no s'estan
      generant dos requeriments diferents que sumin el doble del que
      toca.
      Fet: l'importador divideix les hores en sessions i el repositori
      conserva les hores de cada sessió; les proves mostren els valors
      esperats per assignatura i suma total.

- [x] **F2.** Confirma que `merge_quarter_assignments` (a
      `AcademicDataRepository`) s'està fent servir per a les
      assignatures aparellades del CRUD, o que si no s'usa, la parella
      de requeriments per separat (1Q i 2Q) arriba amb
      `group_id`/`subject_id` en el format que `_parent_and_quarter`
      sap llegir (grup net + sufix al nom de l'assignatura).
      Fet: el CRUD i el frontend exposen la fusió/separació de 1Q+2Q i
      el repositori genera el subjecte fusionat amb els sufixos
      corresponents.

- [x] **F3.** Un cop D i F1/F2 fets, torna a generar un horari de prova
      i confirma que les parelles 1Q/2Q comparteixen exactament una
      franja (no dues consecutives) i que `_apply_quarter_pair_alignment`
      les alinea a la franja més d'hora possible.
      Fet: una prova mínima amb `Dibuix 1Q` i `Color 2Q` acaba amb les
      dues activitats a la mateixa franja.

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
      Fet: quan `min_days=max_days=1`, el `BlockGenerator` retorna un
      únic bloc i no reparteix hores en diversos dies.

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
      Fet: es normalitza i processa com a llista lògica via
      `teacher_names`/`teacher_label`; `TeacherConflictConstraint` i
      `placement_strategy` validen tots els professors assignats, i el
      CRUD/frontend permet selecció múltiple i persistència en format
      canònic.

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
                  Fet: la prioritat s'eleva quan hi ha restriccions de professor o
                  de grup, incloent multi-professor (qualsevol professor
                  restringit) i restriccions per franja (`unavailable_slots`).

### Bloc H — Simplificar restriccions de grup + excepció d'horari fix

Context: a la pàgina principal, la restricció de grup es configura avui
amb un camp de text lliure tipus "Disponibilitat preferida". Cal
simplificar-ho a **dos desplegables** (des de quina hora / fins a quina
hora) que defineixin directament la franja disponible del grup —
exactament el `group_time_window_constraints` que ja fa servir
`GroupTimeWindowConstraint`/`get_group_time_window`
(`scheduler_engine/constraints/group_time_window.py`).

- [x] **H1.** Backend: exposa un endpoint (o amplia l'existent de
      restriccions de grup) que permeti desar `(hora_inici, hora_fi)`
      per grup i el guardi en el format que ja espera
      `group_time_window_constraints` (parella d'índexs de període o de
      minuts — reutilitza `_uses_period_index_window` per confirmar
      quin format fas servir, i sigues consistent).
      Fet: el PATCH de restriccions de grup desa `daily_start_time` i
      `daily_max_end_time`; en generar/validar horari es converteix a
      `group_time_window_constraints` en minuts.

- [x] **H2.** Frontend: substitueix el camp de text lliure
      "Disponibilitat preferida" per dos desplegables (hora d'inici /
      hora de fi), poblats amb els mateixos `hour_names` que la resta
      de l'aplicació, perquè no hi hagi mai un valor mal escrit o fora
      de format (aquest tipus d'error és el que ja ens ha fet perdre
      restriccions abans).
      Fet: el panell de restriccions de grup usa selectors d'hora
      d'inici/fi i els desa contra el backend.

- [x] **H3. Excepció d'horari fix fora de la franja del grup.** Cas
      real: el grup **1r COM** té la franja habitual de matí, però els
      **dimecres** té a més un taller de **16:00 a 19:00**, fora
      d'aquesta franja. Com que `group_time_window_constraints` només
      permet una franja única per grup (sense variar per dia), aquest
      cas s'ha de resoldre com una **activitat d'horari fix** (camps
      `fixed_day`/`fixed_start` que ja existeixen a
      `TeachingRequirement`), NO ampliant la finestra general del grup.
      Confirma/implementa:
      - Que una activitat amb `fixed_day`/`fixed_start` establerts es
        col·loca directament en aquella franja sense passar pel
        filtre de `_group_time_window_conflict_exists` (o que aquest
        filtre l'exclou explícitament quan l'activitat és fixa).
      - Que al CRUD/frontend hi ha una manera clara de marcar una
        assignatura concreta com "horari fix, excepció a la franja
        general del grup" (dia + hora), diferenciada visualment de la
        franja general del grup que s'edita a H2.
      - Que `GroupTimeWindowConstraint.validate` no genera un conflicte
        fals per a aquesta activitat fixa encara que caigui fora de la
        finestra general del grup.
                  Fet: les activitats fixes es marquen com a `fixed`, el placement
                  les exclou del filtre de finestra de grup i la validació de
                  `GroupTimeWindowConstraint` també les ignora.

### Bloc I — Pestanyes de dades acadèmiques buides + simplificació

Context: a l'apartat de dades acadèmiques hi ha aquests filtres/pestanyes:
Professors, Grups d'alumnes, Assignatures, Aules, Assignacions docents,
Actualitza.

- [x] **I1.** La pestanya **Assignatures** no mostra cap assignatura
      (buida). Investiga d'on hauria de treure les dades (probablement
      `AcademicDataRepository`, un mètode tipus `list_subjects()` o
      equivalent) i per què no en retorna cap — pot ser un endpoint que
      no s'ha acabat de connectar, una consulta que filtra malament, o
      que "assignatura" mai s'ha desat com a entitat pròpia i només
      existeix implícitament dins de cada assignació docent (en aquest
      cas, no és un bug de dades perdudes, sinó que la pestanya intenta
      llegir d'un lloc que mai s'ha poblat).
      Fet: `list_subjects()` retorna dades i el frontend les carrega des
      de `/academic-data/subjects`; la pestanya no està trencada per
      codi actual.

- [x] **I2.** Les **restriccions de grup** tampoc apareixen a les dades
      acadèmiques (relacionat amb el Bloc H: potser ni s'estan desant,
      o es desen però la pestanya de Grups no les mostra). Confirma amb
      `active_group_restrictions()` si n'hi ha alguna desada a la BD
      però no es pinta, o si realment no se'n desa cap i el formulari
      per crear-les no funciona.
      Fet: les restriccions de grup es desen i es recuperen via
      `/academic-data/groups/{name}/restrictions` i
      `active_group_restrictions()`.

- [x] **I3. (Decisió de disseny, no un bug — confirma abans de tocar-ho)**
      Es planteja eliminar la pestanya independent **Assignatures** del
      tot, i en comptes d'això afegir un filtre per grup dins de
      **Assignacions docents**, ja que és allà on realment viu la
      informació útil (assignatura + grup + professor + hores). Si
      I1 confirma que "Assignatures" mai ha tingut dades pròpies més
      enllà del que ja hi ha a "Assignacions docents", aquesta
      simplificació té sentit i evita una pestanya buida i confusa.
      Implementa-ho només si t'ho confirma la persona que revisi
      aquest prompt — deixa-ho com a `<!-- DUBTE -->` si no hi ha
      confirmació explícita abans de fer-ho.
      Fet: confirmada l'opció d'eliminar la pestanya independent
      d'Assignatures; es manté la informació dins d'Assignacions docents
      amb filtre per grup.

- [x] **I4. (Millora opcional de conveniència)** Quan es crea una nova
      assignació docent amb un nom d'assignatura que ja existeix a un
      altre grup, oferir precarregar les dades habituals (hores
      setmanals, format de blocs, etc.) i deixar només que canviïn
      grup/professor — sense que això vinculi de debò les dues files
      (cada assignació segueix sent independent a la BD; el professor
      pot diferir per grup). És només per estalviar escriptura repetida
      al formulari, no un canvi de model de dades.
      Fet: al crear assignació, en triar una assignatura existent es
      precarreguen les hores setmanals si el camp era buit.

---

## Quan ho reprenguem al xat

Enganxa'm l'estat de `[x]` d'aquest fitxer i qualsevol `<!-- DUBTE -->`
que hagi quedat. Si pots, enganxa també el contingut actual (no el del
`.patch`) de `group_conflict.py`, `placement_strategy.py` i
`block_generator.py` perquè pugui confirmar l'estat real sense dependre
del que Copilot digui que ha fet.
