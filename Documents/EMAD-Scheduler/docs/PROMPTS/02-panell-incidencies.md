# Prompt 02 - Panell d'incidències

## Objectiu

Aquest document defineix el comportament del panell d'incidències de l'EMAD Scheduler.

El panell d'incidències és el principal sistema de comunicació entre el motor de planificació i l'usuari.

No és una simple llista d'errors.

Ha de permetre entendre ràpidament:

- què està passant
- on passa
- per què passa
- com es pot solucionar

---

# Filosofia

L'usuari no ha d'interpretar codis tècnics.

Mai no s'han de mostrar errors interns.

Per exemple:

Incorrecte

teacher_overlap

room_conflict

constraint_27

Correcte

El professor Jordi té dues classes simultànies.

L'aula Taller 2 està ocupada.

El grup 2n COM té dues activitats a la mateixa hora.

---

# Tipus d'incidències

Les incidències es classifiquen en quatre nivells.

## Error

Impedeix que l'horari sigui vàlid.

Exemples:

- professor duplicat
- grup duplicat
- aula duplicada
- activitat sense professor
- activitat sense aula obligatòria

Color:

vermell

Icona:

❌

---

## Conflicte

L'horari és possible però incompleix una restricció important.

Exemples:

- professor fora de preferència
- massa hores consecutives
- compactació deficient

Color:

taronja

Icona:

⚠️

---

## Avís

No és un problema real.

Només informa.

Exemples:

- professor amb una única hora un dia
- aula infrautilitzada
- assignatura molt fragmentada

Color:

groc

Icona:

ℹ️

---

## Suggeriment

És una proposta de millora.

No indica cap error.

Exemples:

Es podria compactar millor.

Es podria reduir un desplaçament.

Es podria aprofitar una aula lliure.

Color:

blau

Icona:

💡

---

# Ordre

Les incidències sempre apareixen ordenades per prioritat.

1 Errors

2 Conflictes

3 Avisos

4 Suggeriments

Mai barrejar-les.

---

# Agrupació

Les incidències es poden agrupar per:

Professor

Grup

Aula

Dia

Assignatura

Tipus

Cada grup es pot desplegar o plegar.

---

# Comptadors

A la part superior es mostren:

Errors

Conflictes

Avisos

Suggeriments

Els comptadors s'actualitzen automàticament després de qualsevol modificació.
---

# Sincronització amb el calendari

El panell d'incidències i el calendari sempre han d'estar sincronitzats.

No poden mostrar informació diferent.

Quan desapareix una incidència:

- desapareix del panell
- desapareix del calendari
- s'actualitzen els comptadors

Quan apareix una incidència nova:

- apareix immediatament al panell
- es ressalta al calendari
- s'actualitzen els comptadors

Mai cal recarregar la pàgina.

---

# Selecció

Quan l'usuari fa clic sobre una incidència:

- es selecciona automàticament l'activitat relacionada
- el calendari es desplaça fins a ella si és necessari
- el panell dret mostra tota la informació

L'usuari no ha de buscar manualment on és el problema.

---

# Ressalt visual

Quan una incidència està seleccionada:

- l'activitat es ressalta
- el professor implicat es pot ressaltar
- l'aula implicada es pot ressaltar
- el grup implicat es pot ressaltar

Només els elements afectats.

No s'ha de tenyir tot el calendari.

---

# Expansió

Cada incidència es pot desplegar.

Quan està plegada només mostra:

- tipus
- resum
- prioritat

Quan es desplega mostra:

- descripció completa
- activitats afectades
- professors afectats
- grups afectats
- aules afectades
- possibles solucions

---

# Navegació

Cada activitat relacionada és clicable.

L'usuari pot passar d'una incidència a una altra sense perdre el context.

---

# Actualització automàtica

Qualsevol acció ha de recalcular les incidències.

Per exemple:

- moure una activitat
- editar una activitat
- eliminar una activitat
- afegir una activitat
- bloquejar
- desbloquejar
- generar un nou horari

El panell sempre reflecteix l'estat actual.

---

# No mostrar duplicats

Una mateixa incidència no s'ha de mostrar dues vegades.

Per exemple:

Si dues activitats provoquen el mateix conflicte de professor:

Només hi ha una incidència.

Dins la incidència apareixen les dues activitats.

---

# Ordenació interna

Dins de cada categoria:

1. més activitats afectades

2. més impacte

3. ordre cronològic

Això ajuda a solucionar primer els problemes més importants.

---

# Filtrat

El panell permet filtrar:

- només errors

- només conflictes

- només avisos

- només suggeriments

També es pot combinar amb:

- professor

- grup

- aula

- dia

Els filtres són instantanis.

---

# Cerca

La cerca ha de funcionar sobre:

- professor

- grup

- assignatura

- aula

- text de la incidència

No cal prémer Enter.

---

# Incidències resoltes

Quan una incidència desapareix:

No cal mantenir-la visible.

Opcionalment es pot guardar a l'historial.

L'usuari sempre veu només els problemes actuals.

---

# Indicador global

Si no hi ha incidències:

Mostrar un missatge positiu.

Per exemple:

"Horari validat correctament."

o

"No s'han detectat conflictes."

No deixar el panell buit.

---

# Rendiment

El recalcul de les incidències no ha de bloquejar la interfície.

Quan sigui possible:

- reutilitzar validacions existents
- recalcular només les activitats afectades
- evitar validar tot l'horari després de petits canvis

---

# Relació amb l'assistent de resolució

El panell d'incidències no només informa.

També és el punt d'entrada de l'assistent intel·ligent.

Cada incidència pot tenir:

- una explicació
- una causa
- una o més possibles solucions

L'usuari decideix si les aplica.

Mai s'han d'executar canvis automàticament sense confirmació.

---

# Propostes de resolució

Quan sigui possible, el sistema ha de generar propostes.

Exemples:

Professor duplicat

→ moure una de les activitats.

Aula ocupada

→ buscar una aula equivalent.

Grup duplicat

→ proposar un altre horari.

Assignatura massa fragmentada

→ compactar les sessions.

Professor amb massa hores seguides

→ redistribuir les classes.

---

# Prioritat de les solucions

L'ordre recomanat és:

1. mantenir el professor

2. mantenir el grup

3. mantenir l'aula

4. mantenir el dia

5. modificar només l'hora

6. modificar el mínim nombre possible d'activitats

Mai proposar canvis massius si n'hi ha un de senzill.

---

# Qualitat de les propostes

Cada proposta ha d'indicar:

- quines activitats canvien
- per què canvien
- quins conflictes desapareixen
- quines restriccions es mantenen
- si apareix algun conflicte nou

No s'han d'ocultar els inconvenients.

---

# Acceptació

Quan l'usuari accepta una proposta:

- s'aplica al calendari
- es valida
- es recalculen les incidències
- es recalcula la puntuació
- s'actualitza el panell

Tot ha de quedar sincronitzat.

---

# Rebuig

Si l'usuari rebutja una proposta:

No passa res.

El sistema continua mostrant la incidència.

Es poden generar noves propostes.

---

# Explicacions

Cada incidència ha de poder respondre tres preguntes:

Què passa?

Per què passa?

Com es pot solucionar?

Si alguna d'aquestes preguntes no té resposta, la incidència està incompleta.

---

# Informació tècnica

Les dades tècniques només s'utilitzen internament.

No s'han de mostrar codis com:

teacher_overlap

room_conflict

constraint_id

score_delta

L'usuari només veu informació funcional.

---

# Estadístiques

El panell també pot mostrar:

- nombre total d'activitats

- activitats bloquejades

- activitats manuals

- activitats generades

- activitats pendents

- puntuació global

- evolució de la puntuació

Aquestes dades ajuden a entendre l'estat general de l'horari.

---

# Integració amb el motor

El panell no calcula incidències.

Les incidències sempre provenen del backend.

El frontend només:

- les representa
- les filtra
- les ordena
- les destaca visualment

La lògica de validació pertany exclusivament al motor de planificació.

---

# Principis de disseny

Una incidència ha de ser:

- fàcil de detectar
- fàcil d'entendre
- fàcil de localitzar
- fàcil de resoldre

L'usuari no ha de necessitar coneixements tècnics per interpretar-la.

---

# Objectiu final

El panell d'incidències ha de convertir els errors del motor de planificació en informació útil i accionable.

L'usuari ha de poder identificar els problemes més importants en pocs segons, entendre'n la causa i disposar de propostes clares per resoldre'ls.

Aquest document és la referència oficial per al desenvolupament del panell d'incidències de l'EMAD Scheduler.

Qualsevol modificació futura ha de respectar els criteris definits aquí.