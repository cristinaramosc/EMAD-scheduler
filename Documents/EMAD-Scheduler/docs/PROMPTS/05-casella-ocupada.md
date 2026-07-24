# Prompt 05 - Casella ocupada

## Objectiu

Aquest document defineix el comportament de l'EMAD Scheduler quan l'usuari intenta col·locar una activitat en una franja ja ocupada.

No és suficient detectar el conflicte.

El sistema ha d'ajudar l'usuari a entendre què està passant i, quan sigui possible, proposar alternatives.

Aquest document és aplicable tant al drag & drop com a qualsevol altre mecanisme de modificació manual de l'horari.

---

# Principi general

Una casella ocupada no implica necessàriament que el moviment sigui impossible.

Abans de rebutjar una acció cal analitzar:

- qui ocupa la franja
- quin recurs entra en conflicte
- si el conflicte ja existia
- si existeix una alternativa senzilla

Només després d'aquesta anàlisi es decideix si el moviment és acceptable.

---

# Recursos afectats

Una casella pot estar ocupada per:

- un professor

- un grup

- una aula

- diversos recursos alhora

Cada recurs s'ha de validar de forma independent.

---

# Professor ocupat

Quan el professor ja té una altra activitat:

No es permet el moviment.

Missatge recomanat:

Aquest professor ja té una classe en aquesta franja.

No suggerir automàticament moure l'altra activitat.

Aquest tipus de decisió correspon a l'assistent de resolució.

---

# Grup ocupat

Quan el grup ja està ocupat:

El moviment és invàlid.

Missatge:

Aquest grup ja té una altra activitat programada en aquesta hora.

---

# Aula ocupada

Quan només entra en conflicte l'aula:

El sistema ha de comprovar si existeix una altra aula equivalent.

Si no n'hi ha:

mostrar la incidència.

Si n'hi ha:

l'assistent pot proposar el canvi.

Mai aplicar-lo automàticament.

---

# Diversos conflictes

És possible que una mateixa casella presenti més d'un conflicte.

Per exemple:

Professor ocupat.

Aula ocupada.

Grup ocupat.

En aquest cas:

Tots els conflictes s'han de mostrar.

No només el primer detectat.

---

# Activitat bloquejada

Si la casella està ocupada per una activitat bloquejada:

No s'ha d'intentar substituir.

El bloqueig sempre té prioritat.

---

# Activitats manuals

Les activitats manuals tenen exactament la mateixa prioritat que les activitats generades.

No es poden substituir automàticament.

---

# Activitats pendents

Quan una activitat pendent s'arrossega sobre una casella ocupada:

S'apliquen les mateixes validacions.

No existeixen excepcions.

---

# Resposta visual

Durant el moviment:

Casella disponible

contorn verd

Casella amb advertiments

contorn taronja

Casella incompatible

contorn vermell

El calendari ha de mostrar clarament el resultat abans que l'usuari deixi anar l'activitat.

---

# Objectiu

L'usuari ha de saber immediatament:

què ocupa la casella

per què no pot utilitzar-la

què podria fer per solucionar-ho

---

# Suggeriments intel·ligents

Quan una casella no sigui disponible, l'assistent pot proposar alternatives.

Aquestes alternatives mai no s'han d'aplicar automàticament.

Sempre requereixen la confirmació de l'usuari.

---

# Ordre de les propostes

Les propostes s'han de generar segons aquest ordre de prioritat:

1. Canviar només l'hora.

2. Canviar d'aula mantenint professor i grup.

3. Moure l'activitat al mateix dia.

4. Moure-la a un altre dia.

5. Proposar un intercanvi amb una altra activitat.

6. Recomanar una regeneració parcial de l'horari.

Les propostes més senzilles s'han de mostrar primer.

---

# Intercanvis

En versions futures es podran proposar intercanvis.

Exemple:

Activitat A ocupa la franja de l'activitat B.

Si totes dues poden intercanviar-se sense generar conflictes nous:

l'assistent podrà oferir aquesta opció.

L'intercanvi sempre s'ha de validar com una única operació.

---

# Explicació

Cada suggeriment ha d'explicar:

- què canvia
- quins conflictes desapareixen
- quins recursos es mantenen
- si apareix algun inconvenient

L'usuari ha de poder comparar diferents opcions abans de decidir.

---

# Caselles parcialment compatibles

Pot existir una franja que sigui compatible amb alguns recursos però no amb tots.

Per exemple:

✓ Aula disponible

✓ Grup disponible

✗ Professor ocupat

El sistema ha de mostrar clarament quin recurs impedeix el moviment.

---

# Restriccions toves

Les restriccions toves no converteixen una casella en incompatible.

Només han de generar un avís.

Exemples:

- disminució de la compactació
- augment d'hores mortes
- preferència horària no respectada
- distribució menys equilibrada

L'usuari pot continuar si ho considera oportú.

---

# Transparència

Quan una proposta implica un compromís, aquest s'ha d'explicar.

Exemple:

"Aquest canvi elimina el conflicte d'aula, però incrementa el nombre d'hores mortes del grup."

No s'han d'amagar els efectes secundaris.

---

# Rendiment

La detecció de caselles ocupades ha de ser immediata.

Objectius orientatius:

- detecció < 50 ms
- validació < 100 ms
- actualització visual instantània

L'usuari no ha de percebre retards durant el moviment.

---

# Escalabilitat

El comportament ha de ser el mateix encara que el calendari contingui centenars o milers d'activitats.

El temps de resposta no ha de dependre perceptiblement de la mida de l'horari.

---

# Casos de prova mínims

Qualsevol implementació ha de superar, com a mínim, aquestes proves:

✓ Casella completament lliure.

✓ Professor ocupat.

✓ Grup ocupat.

✓ Aula ocupada.

✓ Professor i aula ocupats alhora.

✓ Activitat bloquejada.

✓ Activitat manual.

✓ Activitat pendent.

✓ Casella amb només restriccions toves.

✓ Suggeriment d'aula alternativa.

✓ Intercanvi vàlid (quan aquesta funcionalitat estigui disponible).

---

# Integració amb la resta del sistema

La gestió de caselles ocupades ha d'estar completament integrada amb:

- el calendari
- el panell d'incidències
- el sistema de puntuació
- l'historial
- l'assistent de resolució

No hi pot haver comportaments diferents segons el punt d'entrada.

---

# Objectiu final

Una casella ocupada no és només un obstacle.

És una oportunitat perquè el sistema expliqui el problema, proposi alternatives i ajudi l'usuari a prendre la millor decisió.

Aquest document estableix el comportament funcional oficial davant de qualsevol intent de col·locar una activitat en una franja ocupada dins de l'EMAD Scheduler.