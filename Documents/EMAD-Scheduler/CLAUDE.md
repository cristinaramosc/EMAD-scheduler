# CLAUDE.md

# EMAD-Scheduler

Aquest projecte és un editor visual d'horaris per a centres educatius.

L'objectiu NO és únicament generar horaris.

L'objectiu és oferir la millor experiència possible per crear, editar i optimitzar horaris de forma visual.

El calendari és el centre de tota l'aplicació.

---

# Filosofia

L'usuari no ha de pensar en restriccions.

L'usuari ha de poder treballar de forma natural:

- arrossegar activitats
- bloquejar activitats
- editar hores
- canviar professors
- compactar horaris

El backend és qui decideix si un moviment és possible.

Si no és possible, el sistema ha d'explicar exactament el perquè.

Mai mostrar errors genèrics.

---

# Arquitectura

Frontend

React

↓

API

FastAPI

↓

Application Layer

↓

Scheduler Engine

↓

Placement Strategy

El frontend només representa dades.

Tota la intel·ligència ha d'estar al backend.

---

# Regles de desenvolupament

## Sempre

Fer els canvis mínims possibles.

Mantenir compatibilitat amb el codi existent.

Afegir tests quan es modifiqui el comportament del scheduler.

Explicar quins fitxers s'han modificat.

Descriure breument el motiu del canvi.

---

## No fer mai

No refactoritzar fitxers sencers.

No canviar noms de classes sense necessitat.

No moure fitxers.

No canviar imports absoluts o relatius si no és imprescindible.

No modificar el frontend quan la tasca sigui exclusivament del backend.

No modificar el backend quan la tasca sigui exclusivament del frontend.

No eliminar funcionalitats existents.

---

# Qualitat del codi

Abans de donar una tasca per acabada:

Python

Executar sempre:

python3 -m py_compile <fitxer>

si s'ha modificat un fitxer Python.

React

Comprovar que no hi ha errors de compilació.

---

# Principis del Scheduler

Quan una activitat no es pot col·locar:

NO retornar:

"No s'ha pogut col·locar."

Cal retornar totes les causes.

Exemple:

- professor no disponible
- aula ocupada
- grup supera hores consecutives
- restricció de compactació
- incompatibilitat amb una altra activitat

Si existeixen diverses causes, retornar-les totes.

---

# Drag & Drop

El drag & drop és una funcionalitat principal.

Quan un usuari deixa una activitat damunt d'una altra:

1. intentar el moviment

2. si cal, provar un swap

3. si cal, provar una reorganització local

4. només si tot falla, explicar el motiu

Mai rebutjar el moviment sense intentar alternatives.

---

# Frontend

El calendari és l'element principal.

La resta de la interfície només dona suport al calendari.

Prioritats:

1. calendari

2. incidències

3. activitats sense planificar

4. estadístiques

Evitar finestres emergents.

Preferir panells laterals.

---

# Incidències

Cada incidència ha de contenir:

- activitat

- gravetat

- causes

- possibles solucions (quan existeixin)

Mai mostrar només el títol.

---

# Objectiu final

L'usuari ha de sentir que està editant un calendari intel·ligent.

No un formulari.

Cada funcionalitat nova ha de seguir aquesta filosofia.

---

# Quan implementis una tasca

1. Analitza el codi existent.

2. Fes el canvi mínim.

3. Mantén compatibilitat.

4. Afegeix tests si és possible.

5. Indica:

- fitxers modificats

- resum dels canvis

- possibles riscos

No facis refactors que no s'hagin demanat explícitament.