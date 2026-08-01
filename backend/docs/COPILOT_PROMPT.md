# Prompt per a GitHub Copilot — EMAD-Scheduler

## Com treballar aquest prompt (llegeix això primer)

Treballa la llista de sota **en ordre, un ítem a la vegada**. Per a cada
ítem:
1. Fes NOMÉS aquest canvi (no avancis ítems ni els barregis).
2. Verifica que el projecte compila/passa els tests.
3. Fes commit d'aquest canvi tot sol.
4. Marca l'ítem com fet, canviant `[ ]` per `[x]` **en aquest mateix
   fitxer**, i deixa una línia curta sota l'ítem amb què has fet (fitxers
   tocats, decisions preses). Fes commit també d'aquesta actualització
   del fitxer (pot anar junt amb el commit del pas 3).
5. Passa al següent ítem.

**Si et quedes sense recursos/crèdits a mitges d'un ítem:** no deixis el
codi a mig editar de manera trencada. Desfés els canvis parcials
d'aquest ítem si cal (`git checkout -- <fitxer>` per als que no hagis
acabat), deixa'l com a `[ ]` sense marcar, i atura't. Els ítems ja
marcats `[x]` amb commit fet són l'estat real de progrés — qui continuï
(sigui una altra sessió de Copilot, o l'humà treballant amb Claude en un
xat) ha de poder llegir aquest fitxer i saber exactament per on seguir
sense haver de investigar de nou res del que ja està marcat.

No especulis sobre res ambigu: si un ítem et porta a una decisió no
evident (quin endpoint crear, com resoldre un conflicte de disseny), no
la prenguis en silenci — deixa un comentari `<!-- DUBTE: ... -->` sota
l'ítem corresponent, no el marquis com a fet, i atura't aquí també.

---

## Context general del projecte

Repo `EMAD-Scheduler` (backend Python/FastAPI + motor de generació
d'horaris propi a `backend/scheduler_engine/`). Segueix el `CLAUDE.md`
del repo: canvis mínims, no eliminar funcionalitat existent sense
confirmar-ho.

El sistema està migrant fora del format FET (eina externa usada abans
per generar horaris). La font de dades real avui és un flux basat en
Excel (`AcademicDataRepository`, `AcademicWorkbookImporter`), i el motor
de generació propi (`SchedulerGenerator`/`SchedulerUseCases`) ja no
necessita FET per generar propostes.

**Ja fet abans d'aquest prompt** (no cal repetir-ho ni tornar-ho a
investigar):
- `backend/repositories/school_calendar_repository.py` existeix: llegeix
  dies/hores lectives d'un JSON en lloc del `.fet`.
- `backend/bootstrap.py` ja usa `SchoolCalendarRepository` per al
  calendari de `SchedulerUseCases`.
- `backend/application/scheduler_use_cases.py`: `_apply_quarter_pair_alignment`
  ja s'ha reescrit perquè busqui la franja més d'hora de tota la setmana
  on una parella 1Q/2Q hi càpiga junta, en lloc de conformar-se amb les
  dues franges on cada membre ja es trobava (mètode nou
  `_earliest_common_slot_for_pair`).

---

## Checklist

### Bloc A — Acabar d'eliminar FET

- [x] **A1.** A `backend/application/live_schedule_use_cases.py`: elimina
      el mètode `load_fet()` (i `_resolve_fet_source()` si existeix) i
      treu `fet_file`, `load_activities_fn`, `load_scheduler_activities_fn`
      del constructor. Comprova primer (`grep -rn "load_fet" backend/`)
      qui el crida, per decidir si cal treure la crida del tot o
      substituir-la per una càrrega des de `AcademicDataRepository`. Si
      la resposta no és òbvia, és un cas per al `<!-- DUBTE -->`, no
      l'endevinis.
      Fet: `LiveScheduleUseCases` ja no depèn de cap carregador FET; els
      tests que el feien servir s'han reorientat a `AcademicDataRepository`
      i `load()`.

- [x] **A2.** Reescriu `backend/services/excel_template_exporter.py`
      (`ExcelTemplateExporter`) perquè no depengui de `fet_file`:
      - Calendari (dies/hores) → `SchoolCalendarRepository`.
      - Activitats/professors/grups/aules/restriccions →
        `AcademicDataRepository`.
      - Manté la mateixa sortida (4 `.xlsx`:
        `01_Carrega_docent`, `02_Restriccions_professors`,
        `03_Restriccions_grups`, `04_Aules`) i la mateixa signatura
        pública (`export_templates()` → `TemplateExportResult`).
                  Fet: l'exportador ara llegeix del repositori acadèmic i del
                  repositori de calendari, sense parsejar el `.fet`.

- [ ] **A3.** Un cop A1 i A2 fets: actualitza `backend/bootstrap.py` per
      treure `fet_file` i l'import de `fet_importer` del tot. Esborra
      `backend/services/fet_importer.py`, `import_fet.py` (script arrel)
      i el fitxer `EMAD_2627_.fet`.

- [x] **A4.** `grep -rn "get_fet_restrictions" backend/` — si no té cap
      consumidor, elimina aquest mètode i `_load_fet_blocked_activities()`
      de `scheduler_use_cases.py`. Si en té, deixa un `<!-- DUBTE -->` i
      no el toquis.
      Fet: s'ha eliminat la ruta de bloquejos FET no consumida i
      `_collect_blocked_slots()` ara usa només restriccions de l'Excel
      acadèmic.

- [ ] **A5. (Verificació final del Bloc A)**
      `grep -rln "fet_file\|\.fet\|fet_importer\|import_fet" backend/`
      no ha de retornar res (excepte un comentari/CHANGELOG que
      documenti la migració, si en fas un).

### Bloc B — Restriccions: surten a l'Excel però no a la web

- [ ] **B1.** Localitza l'endpoint del backend que serveix restriccions
      a la web (`grep -rn "restriction" backend/routers/`). Confirma si
      llegeix de `AcademicDataRepository` o d'una altra font.

- [ ] **B2.** Comprova amb una crida directa (test existent o `curl`) si
      l'endpoint retorna les dades correctes. Si sí, el problema és al
      component del frontend — localitza'l i arregla-ho. Si no, compara
      amb el codi ja migrat de `ExcelTemplateExporter` (Bloc A) per veure
      on diverbeixen les dues fonts, i arregla l'endpoint.

- [ ] **B3.** Confirma la resolució: descarrega l'Excel i mira la vista
      web amb les mateixes dades reals — han de coincidir.

### Bloc C — Nova funcionalitat: horari de professor sense filtre de grup

- [ ] **C1.** Backend: afegeix un endpoint (segueix les convencions de
      `backend/routers/scheduler.py`, p. ex.
      `GET /scheduler/teacher/{teacher_name}/schedule`) que retorni totes
      les `Activity` on `teacher == teacher_name`, de qualsevol grup.
      Reutilitza el model `Activity` existent, no calen canvis d'esquema.

- [ ] **C2.** Frontend: afegeix un selector de professor que, en
      triar-se, mostri la graella setmanal d'aquell professor amb totes
      les seves classes juntes (tots els grups), reutilitzant els
      mateixos `day_names`/`hour_names` que la resta de vistes.

- [ ] **C3.** Verificació: es pot triar qualsevol professor i veure
      totes les seves hores de la setmana en una sola graella.

---

## Quan ho reprenguem al xat

Si torneu aquí amb aquest fitxer parcialment marcat, digue'm exactament
quins ítems estan en `[x]` i, si n'hi ha algun amb `<!-- DUBTE -->`,
enganxa'm el dubte tal qual — seguim des d'allà sense repetir cap pas ja
fet.
