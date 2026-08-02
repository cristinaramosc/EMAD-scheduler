# EMAD-Scheduler - Millores funcionals i de planificació

Analitza completament el repositori abans de modificar cap fitxer.

NO canviïs l'arquitectura del projecte, el backend, l'API ni el model de dades llevat que sigui estrictament necessari.

Reutilitza la lògica existent i aplica els canvis de forma incremental.

Abans de començar:

1. Identifica quins fitxers intervenen en:
   - Scheduler
   - Validació de moviments
   - Drag & Drop
   - Renderització del calendari
   - Vista d'horaris
   - Dades acadèmiques
   - CSS del calendari

2. Explica molt breument què modificaràs i per què.

Només després implementa els canvis.

--------------------------------------------------
1. DESCANSOS MÒBILS
--------------------------------------------------

La pastilla grisa de descans NO representa una franja fixa.

Representa un descans obligatori d'una franja que es pot desplaçar una franja amunt o una franja avall.

Per tant:

• No s'ha de considerar una ocupació fixa.
• El scheduler ha de poder moure-la automàticament.
• El Drag & Drop també.
• Només si no existeix cap posició possible s'ha de considerar conflicte.

Quan la validació detecti un conflicte provocat pel descans ha d'intentar:

1. deixar-lo on és
2. moure'l una franja amunt
3. moure'l una franja avall

Només si totes les opcions fallen retornar:

validation_failed

--------------------------------------------------
2. ASSIGNATURES 1Q / 2Q
--------------------------------------------------

Les assignatures que acaben amb:

1Q
2Q

són assignatures quadrimestrals.

Aquestes assignatures:

• poden compartir exactament la mateixa franja
• el scheduler ho ha de considerar la millor opció possible

No és només una excepció.

És una preferència forta.

Exemple:

Dibuix 1Q
Dibuix 2Q

han d'intentar anar exactament a la mateixa hora.

--------------------------------------------------
3. PRIORITAT SI TENEN EL MATEIX PROFESSOR
--------------------------------------------------

Si dues assignatures 1Q/2Q tenen el mateix professor,

aquesta situació ha de tenir encara més puntuació.

Ordre de preferència:

1. Mateix professor + mateixa franja.
2. Mateix grup + mateixa franja.
3. Mateix dia.
4. Qualsevol altra opció.

Aquesta regla ha de formar part del càlcul de score/fitness/cost.

--------------------------------------------------
4. ORDRE DE PLANIFICACIÓ
--------------------------------------------------

Abans de començar la cerca, ordena les assignatures.

Prioritat:

1. Professors amb restriccions de dies.
2. Assignatures amb restriccions de dies.
3. Assignatures amb menys franges disponibles.
4. Assignatures amb més hores.
5. Parelles 1Q / 2Q.
6. Resta.

L'algorisme ha de col·locar primer les assignatures difícils.

No utilitzis un ordre aleatori.

--------------------------------------------------
5. VALIDACIÓ DEL DRAG & DROP
--------------------------------------------------

Quan es mou una assignatura:

abans de retornar

validation_failed

la validació ha de seguir aquest ordre:

1. comprovar professor
2. comprovar grup
3. comprovar aula
4. intentar moure el descans
5. permetre compartir franja si és una parella 1Q/2Q
6. recalcular els elements afectats

Només si totes les opcions fallen retornar:

validation_failed

--------------------------------------------------
6. HORARI DEL PROFESSOR
--------------------------------------------------

Aquesta funcionalitat ja existia parcialment.

Recupera-la.

Ha d'existir una vista equivalent a l'horari del grup però filtrada per professor.

Ha de mostrar:

• assignatura
• grup
• aula
• dia
• hora

Utilitza exactament el mateix component visual del calendari.

No creïs una vista diferent.

--------------------------------------------------
7. DADES ACADÈMIQUES - ASSIGNACIONS DOCENTS
--------------------------------------------------

A:

Dades acadèmiques
→ Assignacions docents

afegir una columna:

AULA

Mostrant l'aula assignada.

Si ja existeix la relació al model, simplement mostrar-la i permetre editar-la.

--------------------------------------------------
8. DADES ACADÈMIQUES - GRUPS
--------------------------------------------------

Afegir una nova secció:

Disponibilitat del grup

Cada grup ha de definir:

• dies lectius
• franges horàries disponibles

No tots els grups tenen cinc dies.

Exemples:

2n APGI → 4 dies
2n COM → 4 dies

Per tant, el scheduler NO pot generar classes en un dia que el grup no assisteix.

--------------------------------------------------
9. DISPONIBILITAT DEL GRUP
--------------------------------------------------

La configuració NO ha de ser només una llista.

Crear una graella similar al calendari setmanal.

Files:

Franges horàries.

Columnes:

Dilluns
Dimarts
Dimecres
Dijous
Divendres

Cada cel·la indicarà si aquella franja està disponible.

Exemple:

☑ Dilluns 8:30-9:30

☐ Divendres 15:30-16:30

Això permet definir casos com:

• grups de matí
• grups de tarda
• grups que no venen divendres
• grups que entren més tard algun dia

És molt més flexible que definir dies i franges per separat.

--------------------------------------------------
10. INTEGRACIÓ AMB EL SCHEDULER
--------------------------------------------------

La disponibilitat del grup és una restricció forta.

Abans de provar una posició el scheduler ha de comprovar:

• que el dia està habilitat
• que totes les franges necessàries estan disponibles

Si no ho estan,

ni tan sols ha d'intentar aquella posició.

--------------------------------------------------
11. CALENDARI
--------------------------------------------------

Continuar mantenint les millores ja implementades:

• blocs de dues hores fusionats
• alçada correcta dels blocs
• files més altes
• text llegible
• representació correcta dels blocs 1Q/2Q

--------------------------------------------------
12. COMPROVACIONS FINALS
--------------------------------------------------

Verifica que:

✓ El descans es pot moure una franja amunt o avall.

✓ Els moviments no fallen si només cal reubicar el descans.

✓ Les assignatures 1Q i 2Q comparteixen franja sempre que sigui possible.

✓ Si comparteixen professor aquesta és la primera opció.

✓ El scheduler col·loca primer els professors amb restriccions.

✓ Després les assignatures amb restriccions.

✓ Després les assignatures difícils.

✓ Torna a existir l'horari del professor.

✓ A Assignacions docents es mostra també l'aula.

✓ A Grups es pot configurar la disponibilitat mitjançant una graella setmanal.

✓ El scheduler respecta aquesta disponibilitat.

--------------------------------------------------
13. ENTREGA
--------------------------------------------------

En acabar, mostra:

1. Fitxers modificats.
2. Explicació breu de cada canvi.
3. Justificació de les decisions de disseny.
4. Confirmació que no s'han introduït regressions en la resta del sistema.

IMPORTANT:

Prioritza sempre les modificacions mínimes, reutilitzant la lògica existent. Evita duplicar funcionalitats o crear components nous si els actuals es poden ampliar.