# EMAD Scheduler

## Què és aquest projecte?

EMAD Scheduler és una plataforma per generar, editar i explicar horaris acadèmics complexos.

No és únicament un generador automàtic d'horaris.

L'objectiu és construir una eina que permeti combinar:

- generació automàtica
- edició manual
- validació immediata
- explicació intel·ligent dels conflictes
- assistència basada en IA

L'usuari manté sempre el control final sobre l'horari.

---

# Filosofia

El projecte es basa en cinc principis.

## 1. El motor no pren decisions per l'usuari

El sistema genera propostes.

Mai imposa una solució.

Sempre és l'usuari qui decideix.

---

## 2. Les restriccions són el centre del sistema

Tot gira al voltant de les restriccions.

Existeixen:

- restriccions fortes (mai es poden violar)
- restriccions toves (es poden relaxar si milloren la qualitat global)

---

## 3. Les propostes són temporals

Quan es genera un horari no es modifica immediatament l'horari actiu.

Primer es crea una Proposal.

Només quan l'usuari l'accepta passa a ser l'horari actiu.

---

## 4. L'horari actiu és editable

Una vegada acceptat un horari, l'usuari pot:

- moure activitats
- afegir activitats manuals
- eliminar activitats
- afegir descansos
- afegir hores de dinar

Cada modificació es valida abans de ser acceptada.

---

## 5. L'assistent explica, no decideix

La IA no substitueix el planificador.

La seva funció és:

- explicar conflictes
- suggerir alternatives
- justificar recomanacions
- ajudar a entendre les conseqüències de cada canvi

Mai modifica l'horari sense confirmació.

---

# Arquitectura general

El sistema està dividit en diversos blocs independents.

- Frontend React
- Backend FastAPI
- Application Layer
- Scheduler Engine
- Search Engine
- AI Assistant
- Persistence

Cada component té una responsabilitat única.

---

# Flux principal

El flux principal del projecte és:

Teaching Requirements

↓

Teaching Blocks

↓

Search Engine

↓

Schedule Proposal

↓

Acceptació de l'usuari

↓

Active Schedule

↓

Edició manual

↓

Persistència

---

# Estat actual

Actualment el projecte disposa de:

- generació de blocs
- sistema de propostes
- edició interactiva
- validació incremental
- activitats manuals
- descansos
- hores de dinar
- arquitectura preparada per IA
- documentació funcional

El SchedulerGenerator continua evolucionant per millorar la qualitat de les propostes.

---

# Objectiu final

L'objectiu d'EMAD Scheduler no és competir amb FET.

L'objectiu és construir una plataforma moderna de planificació acadèmica on la generació automàtica, l'edició manual i la intel·ligència artificial treballin conjuntament.

L'usuari continua prenent totes les decisions importants.

La plataforma simplement li proporciona les millors eines possibles per fer-ho.