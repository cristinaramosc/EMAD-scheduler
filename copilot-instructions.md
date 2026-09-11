# Context per a GitHub Copilot — EMAD-Scheduler

## Què és el projecte
Aplicació de planificació d'horaris per a un centre de formació (EMAD), amb
backend Python/FastAPI i frontend React/Vite, amb un motor de programació
d'horaris basat en restriccions. Repositori:
`github.com/cristinaramosc/EMAD-scheduler`, branca de treball
`fix/quarter-alignment-academic-data`.

## Estructura clau
- `backend/application/scheduler_use_cases.py` — orquestració principal:
  construcció de requeriments a partir de les dades acadèmiques, compactació
  d'horaris (`_compact_activities`), alineació de parelles 1Q/2Q, acceptació
  i moviment d'activitats dins una proposta.
- `backend/scheduler_engine/` — motor de generació i col·locació
  (`generator.py`, `placement_strategy.py`, `quarter_utils.py` amb
  `group_names()`/`normalize_group_name()` per a grups combinats com
  `"GI, GP"`).
- `backend/repositories/academic_data_repository.py` — emmagatzematge en
  memòria (professors, grups, assignatures, aules, restriccions,
  assignacions docents). **Important: tot és en memòria, no persisteix a
  disc; es perd en cada reinici del backend (inclòs l'auto-reload de
  `uvicorn --reload`).**
- `backend/services/schedule_exporter.py` / `schedule_pdf_exporter.py` —
  exportació a Excel/PDF.
- `frontend/src/App.jsx` — tot el frontend viu en aquest únic fitxer gran
  (calendari, filtres, restriccions, xat assistent, etc.).
- `backend/tests/test_todays_features_regression.py` — fitxer de tests de
  regressió on s'hi van afegint tests puntuals per a cada fix/feature nova.

## Convencions i preferències de la Cristina (segueix-les sempre)
- Corregeix només el que està malament, sense tocar lògica o noms no
  relacionats.
- Canvis mínims i quirúrgics, verificats abans de donar-los per bons.
- Abans de donar per acabat un canvi al backend: `cd backend && python3 -m
  pytest -q`. La suite normal ha de donar **185 passats** i sempre els
  mateixos 5 que ja fallaven abans (no relacionats, no els toquis):
  `test_move_activity.py::test_invalid_move_is_rejected_and_schedule_remains_consistent`,
  `test_scheduler_api.py::test_scheduler_generation_endpoint_uses_fet_bootstrap_when_request_is_empty`,
  `test_scheduler_api.py::test_incomplete_fet_proposal_cannot_be_accepted`,
  `test_scheduler_generator_interfaces.py::test_scheduler_generator_uses_the_strategy`,
  `test_working_timetable_persistence.py::test_pending_proposal_is_restored_after_dependency_reset`.
  El que importa és que la llista de failed no creixi ni canviï.
- Si el canvi afecta el frontend: `cd frontend && npm run build` ha de
  passar sense errors.
- Quan es corregeix un bug real, afegeix un test de regressió petit a
  `backend/tests/test_todays_features_regression.py` seguint l'estil dels
  tests que ja hi ha (normalment usant
  `SchedulerUseCases.__new__(SchedulerUseCases)` per construir una
  instància mínima sense passar per tot el `__init__`).
- Un patró de bug recurrent en aquest projecte: qualsevol lloc que compari
  el camp `group` per igualtat exacta de text (`activity.group ==
  "GI"`) trenca amb grups combinats com `"GI, GP"`. Sempre cal fer servir
  `group_names(group)` (de `scheduler_engine/quarter_utils.py`, que
  normalitza amb `casefold`) i unir/comparar conjunts, mai comparació
  directa de text. Si compares contra claus guardades amb el text
  original (no normalitzat), cal normalitzar-les totes dues bandes abans
  de comparar.
- `backend/data/school_calendar.json` defineix `day_names`/`hour_names`
  (l'horari del centre, actualment de 8:00 a 21:30). No hardcodejar hores
  al codi.

## Bugs coneguts, ja detectats però encara sense corregir (context, no cal tocar-los sense que t'ho demani)
1. Reimportar el mateix full Excel d'assignacions genera IDs nous cada
   vegada en lloc d'actualitzar les files existents
   (`_apply_teaching_assignments_dataset` guarda per `canonical_id` nou en
   lloc de per la clau calculada), i marca com a eliminades totes les
   assignacions anteriors encara que la fila segueixi present a
   l'importació nova.
2. Dues files amb el mateix professor+assignatura+grup exactes col·lideixen
   silenciosament (només sobreviu l'última).
3. `generator.py::_build_blocks_from_requirements` descarta un requeriment
   amb un `continue` silenciós quan no troba cap distribució vàlida de
   blocs — sense generar cap incidència.
4. El camp que es llegeix per al "màxim de dies" d'una assignatura
   (`assignment.get("max_days")`) no coincideix amb el nom real del camp a
   les dades (`max_session_days`), així que aquest límit mai s'aplica
   correctament.
5. Un avís de "no s'ha pogut col·locar" d'una activitat que en una altra
   ordenació provada pel generador ha fallat pot filtrar-se a la llista
   `warnings` d'una proposta diferent on aquella mateixa activitat sí que
   s'ha col·locat bé (sospita: `generator.py::generate()` acumula
   `placement_warnings` de totes les ordenacions provades en una única
   llista global en lloc de mantenir-les separades per proposta).

## Pendents actius (backlog)
- **Pendent C** (disseny, no bug): els horaris dels grups s'haurien de
  compactar al màxim (sense forats) sense forçar-los a començar sempre a
  les 8:00.
- **Nova petició sense dissenyar**: un "màxim de dies setmanals per
  professor", anàleg al `max_days` que ja existeix per a grups
  (`GroupRestrictionDTO`), però aplicat a `TeacherRestrictionDTO` (cal
  revisar com `active_teacher_restrictions()` s'usa a
  `scheduler_use_cases.py` per replicar el mateix patró que `max_days` als
  grups).

## Com treballa normalment
Fes canvis mínims i localitzats, verifica sempre amb els tests abans de
donar-los per fets, i explica en poques línies què has canviat i per què
(sense reescriure fitxers sencers si només cal tocar unes línies).
