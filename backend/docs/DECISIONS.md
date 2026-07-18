# Decisions del projecte

## 2026-07-04

Decisió:

L'horari principal és el del grup.

Motiu:

És la vista més utilitzada a l'EMAD.

Conseqüència:

Les vistes de professor i aula es generen a partir dels horaris dels grups.

## 2026-07-04 (compat shim)

Decisió temporal:

Per compatibilitat amb imports existents s'ha afegit un shim `scheduler_engine/__init__.py`
que redirigeix les importacions cap a `backend.scheduler_engine`.

Raó:

La base de codi original utilitza imports amb el prefix `scheduler_engine.*` a
varis llocs i tests. Evitar una refactorització d'imports massiva facilita fer
canvis incrementals sense trencar regressions durant el desenvolupament del
nou domini de `TeachingRequirement`.

Acció futura:

Eliminar aquest shim i unificar l'espai de noms movent `scheduler_engine` al
nível superior o actualitzant els imports a `backend.scheduler_engine`.
Aquesta refactorització s'ha de planificar i executar amb tests i commits petits.

## 2026-07-05 (platform data split)

Decisió:

Separar l'arquitectura d'integració entre dades de configuració permanent del centre i dades d'any acadèmic.

Motiu:

El producte evoluciona d'un generador d'horaris a una plataforma permanent de gestió. Els imports futurs no han de carregar directament un `Schedule`, sinó datasets normalitzats que després l'aplicació decidirà com persistir o convertir.

Conseqüència:

Els contractes d'import/export passen a tenir una frontera comuna basada en datasets i mapping, mantenint compatibilitat temporal amb l'export/import de `Schedule` existent.

Acció futura:

Implementar importadors concrets (Excel workload, FET bootstrap, CSV, Google Sheets) sobre aquesta frontera comuna i definir després la persistència separada per `School` i `AcademicYear`.