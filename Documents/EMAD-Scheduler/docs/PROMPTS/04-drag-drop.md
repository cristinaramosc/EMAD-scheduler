# Prompt 04 - Drag & Drop

## Objectiu

Aquest document defineix el funcionament complet del sistema de moviment d'activitats dins de l'EMAD Scheduler.

Qualsevol implementació (React, Vue, Flutter o una altra tecnologia) ha de respectar aquest comportament.

El drag & drop és una de les funcionalitats principals de l'aplicació.

L'usuari ha de poder reorganitzar l'horari de forma intuïtiva mantenint totes les restriccions acadèmiques.

---

# Principis generals

L'usuari ha de sentir que mou una targeta sobre un calendari.

No ha de percebre que està modificant una base de dades.

El moviment ha de ser immediat.

La validació ha de ser automàtica.

La resposta visual ha de ser instantània.

---

# Activitats

Cada activitat és una unitat indivisible.

Conté com a mínim:

- identificador

- assignatura

- professor

- grup

- aula

- dia

- hora

- durada

- estat de bloqueig

---

# Inici del moviment

Quan l'usuari prem sobre una activitat:

la targeta entra en mode moviment.

El sistema recorda:

- dia original

- hora original

- aula original

- professor

- identificador

Aquesta informació servirà per restaurar l'activitat si el moviment no és vàlid.

---

# Durant el moviment

L'activitat segueix el cursor.

No desapareix.

No es duplica.

No es crea una còpia permanent.

Només existeix una representació temporal.

---

# Posició temporal

Mentre el cursor es mou:

el sistema calcula contínuament:

nou dia

nova hora

possible aula

franges afectades

Aquest càlcul és temporal.

No modifica l'horari real.

---

# Validació en temps real

Durant el moviment es comproven:

ocupació del professor

ocupació del grup

ocupació de l'aula

activitats bloquejades

durada

límits horaris

restriccions fortes

No es modifiquen dades persistents.

---

# Restriccions toves

També es calculen:

compactació

preferències

hores mortes

fragmentació

equilibri

Aquestes restriccions només generen avisos.

Mai impedeixen deixar anar una activitat.

---

# Resposta visual

Zona vàlida

contorn verd

Zona amb advertiments

contorn taronja

Zona invàlida

contorn vermell

L'usuari ha d'entendre immediatament si el moviment és possible.

---

# Cap canvi permanent

Fins que l'usuari deixa anar el ratolí:

No s'ha de modificar:

l'estat

la base de dades

el backend

la puntuació

les incidències

Tot és provisional.
---

# Final del moviment

Quan l'usuari deixa anar una activitat:

el frontend envia una única petició al backend.

El backend és l'únic responsable de decidir si el moviment és acceptable.

El frontend mai no decideix si un moviment és vàlid.

---

# Validació

El backend reconstrueix un horari temporal.

Mai modifica directament l'horari actiu.

Primer calcula els conflictes existents.

A continuació aplica temporalment el moviment.

Després calcula els conflictes del nou horari.

Finalment compara els dos conjunts.

Només interessen els conflictes nous.

Els conflictes que ja existien abans del moviment no impedeixen el canvi.

Aquest mecanisme permet millorar progressivament un horari encara que inicialment contingui incidències.

---

# Conflictes nous

Només es consideren errors:

els conflictes que apareixen com a conseqüència del moviment.

Per exemple:

Si ja existia un conflicte d'aula abans del moviment:

el moviment no s'ha de rebutjar per aquest motiu.

Només s'ha de rebutjar si crea un conflicte addicional.

---

# Acceptació

Quan el moviment és vàlid:

el backend actualitza l'horari.

desa l'estat.

recalcula les incidències.

actualitza la puntuació.

retorna el nou estat complet.

---

# Rebuig

Quan el moviment no és vàlid:

el backend no modifica l'horari.

retorna la llista de conflictes nous.

el frontend retorna automàticament la targeta a la posició original.

L'usuari no ha de corregir manualment el moviment.

---

# Persistència

Quan un moviment és acceptat:

s'ha de desar immediatament.

No s'ha d'esperar que l'usuari premi "Guardar".

L'horari actiu sempre reflecteix l'última acció acceptada.

---

# Sincronització

Després d'un moviment correcte s'han d'actualitzar:

el calendari

les incidències

la puntuació

les estadístiques

el panell dret

l'historial

Tots els elements han de mostrar la mateixa informació.

---

# Desfer

Cada moviment acceptat crea una nova entrada a l'historial.

L'usuari pot desfer qualsevol moviment.

En desfer:

es restaura exactament l'estat anterior.

No es recalcula un horari diferent.

Es recupera el mateix estat que existia abans del moviment.

---

# Refer

Després d'un Desfer:

l'usuari pot executar Refer.

Es recupera exactament el moviment que s'havia desfet.

---

# Historial

Cada moviment registra:

identificador de l'activitat

dia anterior

hora anterior

dia nou

hora nova

usuari

data

hora

Aquesta informació permet auditar qualsevol canvi.

---

# Bloquejos

Les activitats bloquejades no es poden moure.

Quan l'usuari intenta arrossegar-les:

el moviment no comença.

Es mostra un missatge discret indicant que l'activitat està bloquejada.

No s'ha de permetre iniciar un moviment que inevitablement fracassarà.

---

# Objectiu

El moviment d'activitats ha de ser segur.

Mai no ha de deixar l'horari en un estat inconsistent.

Cada acció ha de produir un resultat completament coherent.

---

# Blocs de diverses hores

Una activitat pot ocupar diverses franges consecutives.

Exemples:

Durada 2

09:00 - 11:00

Durada 3

15:00 - 18:00

Quan es mou una activitat:

es mou sempre el bloc complet.

Mai una part.

---

# Validació de blocs

Totes les franges ocupades pel bloc han de ser vàlides.

No n'hi ha prou amb validar la primera.

Exemple:

09:00 lliure

10:00 ocupada

El moviment és invàlid.

---

# Activitats manuals

Les activitats creades manualment es comporten igual que qualsevol altra activitat.

Es poden:

moure

editar

bloquejar

eliminar

Només canvia el seu origen.

---

# Descansos

Els descansos són activitats especials.

Per defecte:

es poden moure.

No obstant això:

només poden situar-se dins la finestra de descans configurada.

Exemple:

09:30

10:00

10:30

11:00

11:30

12:00

Fora d'aquesta finestra:

el moviment és invàlid.

---

# Dinars

Les hores de dinar també són activitats especials.

Només poden situar-se entre:

12:00

i

16:00

A més:

han de tenir una durada d'una hora.

---

# Activitats bloquejades

Quan una activitat està bloquejada:

no es pot:

moure

compactar

reubicar

generar automàticament

Només l'usuari la pot desbloquejar.

---

# Intercanvis

En el futur es podran intercanviar dues activitats.

Quan això s'implementi:

s'hauran de validar simultàniament els dos moviments.

No s'han de validar de forma independent.

---

# Aula ocupada

Quan el destí està ocupat:

no s'ha de sobreescriure automàticament.

L'usuari ha de rebre una explicació.

En futures versions:

es podran proposar intercanvis.

---

# Professor ocupat

Si el professor ja té classe:

el moviment és invàlid.

No s'ha d'intentar moure automàticament l'altra activitat.

Aquest tipus de decisions corresponen a l'assistent de resolució.

---

# Grup ocupat

Mateix comportament.

No es fan modificacions automàtiques.

Només es detecta el conflicte.

---

# Restriccions toves

Les restriccions toves mai bloquegen el moviment.

Només provoquen:

avisos

reducció de puntuació

propostes de millora

L'usuari continua tenint l'última decisió.

---

# Activitats pendents

Les activitats encara no planificades també poden arrossegar-se.

Quan es deixen sobre el calendari:

passen a formar part de l'horari actiu.

Es validen igual que qualsevol altra activitat.

---

# Cancel·lació

Si l'usuari prem ESC durant el moviment:

es cancel·la immediatament.

No es fa cap petició al backend.

Tot torna a l'estat anterior.

---

# Sortida del calendari

Si l'usuari deixa anar l'activitat fora del calendari:

el moviment es cancel·la.

No s'elimina cap activitat.

No apareixen errors.

Simplement es recupera la posició inicial.

---

# Objectiu

L'usuari ha de tenir confiança absoluta.

Mai ha de tenir por de moure una activitat.

Qualsevol acció incorrecta sempre ha de ser reversible.

---

# Comunicació entre frontend i backend

El frontend és responsable únicament de:

- mostrar el moviment
- capturar la posició final
- enviar la petició al backend
- representar el resultat

El frontend no decideix mai si un moviment és correcte.

El backend és l'única font de veritat.

---

# API

El moviment sempre ha de passar pel mateix cas d'ús.

No poden existir camins alternatius.

Tant si el moviment prové de:

- drag & drop
- doble clic
- editor
- assistent

sempre s'ha d'executar la mateixa lògica del backend.

---

# Integritat

Després de qualsevol moviment:

l'horari ha de continuar sent coherent.

No poden existir:

- activitats duplicades
- professors duplicats
- grups duplicats
- aules duplicades

excepte si aquests conflictes ja existien abans i el moviment no n'ha creat de nous.

Aquest és un principi fonamental del sistema.

---

# Validació incremental

La validació incremental és obligatòria.

Flux recomanat:

1. calcular els conflictes inicials

2. aplicar el moviment sobre una còpia

3. calcular els conflictes resultants

4. identificar únicament els conflictes nous

5. decidir si el moviment és acceptable

Aquest mecanisme permet corregir horaris imperfectes de forma progressiva.

---

# Rendiment

El moviment ha de donar una resposta molt ràpida.

Objectius orientatius:

- inici del moviment < 50 ms

- validació < 100 ms

- resposta del backend < 300 ms

- actualització del calendari < 100 ms

L'usuari ha de percebre el sistema com a instantani.

---

# Escalabilitat

El sistema ha de funcionar correctament amb:

- més de 1000 activitats

- més de 50 professors

- més de 30 grups

- més de 40 aules

El rendiment no ha de degradar-se de manera apreciable.

---

# Extensibilitat

En el futur es podran afegir:

- noves restriccions
- nous tipus d'activitat
- nous calendaris
- diverses seus
- horaris compartits
- calendaris personals

El sistema de moviment no s'haurà de reescriure.

Només s'hi afegiran noves regles de validació.

---

# Compatibilitat

El sistema de drag & drop ha de funcionar igual independentment de:

- navegador

- resolució

- mida de pantalla

- sistema operatiu

La lògica funcional no pot dependre de la interfície.

---

# Criteris per a qualsevol IA

Abans de modificar aquest sistema, qualsevol IA ha de verificar que:

1. El moviment continua passant sempre pel backend.

2. La validació incremental continua funcionant.

3. Els conflictes existents no impedeixen moviments que els mantenen.

4. Només els conflictes nous poden invalidar un moviment.

5. La persistència continua sent automàtica.

6. L'historial continua registrant totes les accions.

7. Les incidències continuen sincronitzades amb el calendari.

8. No apareixen regressions en activitats manuals, descansos o hores de dinar.

9. No es duplica la lògica entre frontend i backend.

10. El comportament continua sent coherent independentment de la tecnologia utilitzada.

---

# Casos de prova mínims

Qualsevol implementació ha de superar, com a mínim, aquestes proves:

✓ Moure una activitat a una franja lliure.

✓ Intentar moure una activitat sobre un professor ocupat.

✓ Intentar moure una activitat sobre un grup ocupat.

✓ Intentar moure una activitat sobre una aula ocupada.

✓ Moure una activitat de dues hores.

✓ Moure una activitat bloquejada.

✓ Moure una activitat manual.

✓ Col·locar una activitat pendent al calendari.

✓ Cancel·lar un moviment amb ESC.

✓ Desfer un moviment.

✓ Refer un moviment.

✓ Comprovar que només es detecten conflictes nous.

---

# Objectiu final

El sistema de drag & drop és una de les característiques diferencials de l'EMAD Scheduler.

Ha de ser ràpid, intuïtiu, segur i coherent.

L'usuari ha de poder reorganitzar un horari complex amb la mateixa naturalitat amb què mouria targetes sobre una taula.

Tota la lògica de validació ha de continuar residint al backend, mentre que el frontend s'encarrega exclusivament de proporcionar una experiència d'ús clara, fluida i fiable.

Aquest document és la referència funcional oficial del sistema de moviment d'activitats de l'EMAD Scheduler.