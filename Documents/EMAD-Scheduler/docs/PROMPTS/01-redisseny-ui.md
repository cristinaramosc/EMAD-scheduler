# Prompt 01 - Redisseny de la interfície d'EMAD Scheduler

## Objectiu

L'objectiu d'aquest document és definir el comportament esperat de tota la interfície gràfica de l'aplicació EMAD Scheduler.

Aquest document ha de ser utilitzat per qualsevol IA (ChatGPT, Copilot, Claude, Devin o similar) abans de modificar el frontend.

No s'han de fer canvis que contradiguin aquest document.

---

# Filosofia de la interfície

L'aplicació no és un programa tècnic destinat exclusivament a informàtics.

És una eina utilitzada diàriament per direcció, caps d'estudis i professorat.

Per tant la interfície ha de transmetre:

- senzillesa
- rapidesa
- claredat
- confiança
- estabilitat

No s'ha de buscar una interfície carregada.

L'usuari ha de poder entendre l'estat de l'horari en menys de cinc segons.

La informació important sempre ha de destacar visualment.

La informació secundària ha de quedar en segon terme.

---

# Inspiració visual

La interfície ha d'inspirar-se en aplicacions modernes com:

- Linear
- Notion
- Figma
- Google Calendar
- Cron
- ClickUp

No s'ha d'imitar Microsoft Outlook.

No s'han d'utilitzar taules antigues amb vores gruixudes.

No s'han d'utilitzar gradients exagerats.

No s'han d'utilitzar ombres molt marcades.

La sensació general ha de ser minimalista.

---

# Distribució general

La pantalla es divideix en tres zones.

--------------------------------------------------------

Barra superior

--------------------------------------------------------

Panell esquerre

Calendari central

Panell dret

--------------------------------------------------------

Barra inferior opcional

--------------------------------------------------------

El calendari sempre és l'element més important.

Ha d'ocupar aproximadament el 70% de l'amplada disponible.

Els panells laterals només mostren informació complementària.

---

# Barra superior

La barra superior conté:

- logotip
- nom del projecte
- selector de curs acadèmic
- botó Generar horari
- botó Desfer
- botó Refer
- botó Guardar
- botó Exportar
- menú Configuració

No hi ha d'haver més opcions visibles.

Les opcions avançades han d'anar dins del menú Configuració.

---

# Calendari

El calendari és el centre de tota l'aplicació.

Mai ha de quedar amagat darrere de panells.

Ha d'omplir gairebé tota la pantalla.

Els dies de la setmana apareixen en columnes.

Les hores apareixen en files.

Les hores han de tenir una alçada suficient perquè els blocs siguin fàcilment editables.

No s'han d'utilitzar files molt baixes.

---

# Blocs d'activitat

Cada activitat és una targeta.

La targeta mostra:

- assignatura
- professor
- grup
- aula

L'ordre és sempre aquest.

Quan no hi ha espai suficient:

1. assignatura
2. professor
3. grup
4. aula

L'assignatura mai no s'ha d'amagar.

---

# Colors

Els colors han de servir únicament per identificar.

No han de ser decoratius.

Cada grup tindrà un color principal.

Cada assignatura podrà tenir una variant lleugerament diferent.

Els conflictes utilitzaran vermell.

Els avisos utilitzaran taronja.

Les activitats bloquejades utilitzaran una icona de cadenat.

Les activitats seleccionades utilitzaran una vora visible.

---

# Selecció

Un sol clic selecciona una activitat.

La selecció mostra:

- vora destacada
- lleugera ombra
- informació completa al panell dret

No s'ha d'obrir cap finestra.

La selecció sempre és immediata.

---

# Doble clic

Un doble clic obre l'editor.

L'editor permet modificar:

- professor
- aula
- grup
- assignatura
- dia
- hora
- durada

També permet:

- bloquejar
- desbloquejar
- eliminar
- duplicar

Cap modificació s'aplica fins que l'usuari prem "Desar".
---

# Drag & Drop

El sistema de drag & drop és una de les funcionalitats principals de l'aplicació.

Ha de funcionar de manera fluida.

No s'han de produir salts visuals.

L'activitat s'ha de moure seguint el cursor.

Sempre s'ha de veure una previsualització de la nova posició.

Mai no s'ha de moure definitivament fins que es deixi anar.

---

# Validació durant el moviment

Mentre l'usuari arrossega una activitat, el sistema ha de calcular en temps real:

- conflictes de professor
- conflictes de grup
- conflictes d'aula
- restriccions de durada
- activitats bloquejades
- descansos
- hores de dinar
- restriccions fortes

Les restriccions toves també s'han de calcular però no han d'impedir el moviment.

Només les restriccions fortes poden impedir deixar anar una activitat.

---

# Previsualització

Durant el moviment:

la posició vàlida es mostra amb:

- contorn verd
- lleugera transparència

La posició amb advertències es mostra amb:

- contorn taronja

La posició invàlida es mostra amb:

- contorn vermell

No s'ha de mostrar cap missatge emergent.

La informació detallada apareix al panell dret.

---

# Confirmació

Quan l'usuari deixa anar una activitat:

si el moviment és vàlid:

- s'aplica immediatament
- es desa automàticament
- es recalculen incidències
- s'actualitza la puntuació

si el moviment és invàlid:

- l'activitat torna automàticament a la posició original
- s'explica el motiu

Mai no s'ha de deixar una activitat en una posició impossible.

---

# Animacions

Les animacions han de ser molt curtes.

Durada recomanada:

150 ms

No utilitzar:

- rebots
- efectes exagerats
- rotacions
- zooms

Només:

- translació
- canvi d'opacitat
- canvi de color

---

# Zoom

L'usuari ha de poder augmentar o reduir la mida del calendari.

No s'ha de modificar la mida del text.

Només:

- amplada de columnes
- alçada de files

---

# Scroll

El desplaçament vertical ha de ser molt fluid.

La capçalera dels dies ha de quedar fixa.

La columna de les hores també.

Només el calendari es desplaça.

---

# Activitat seleccionada

Quan una activitat està seleccionada:

- augmenta lleugerament la seva ombra
- mostra una vora
- envia la informació al panell dret

Només hi pot haver una activitat seleccionada.

---

# Activitats bloquejades

Les activitats bloquejades:

- mostren un cadenat
- no es poden arrossegar
- només es poden editar des del diàleg d'edició

Si l'usuari intenta moure-les:

mostrar un avís discret.

No mostrar finestres emergents.

---

# Edició ràpida

Amb el botó dret o menú contextual:

- editar
- duplicar
- eliminar
- bloquejar
- desbloquejar

Aquest menú ha de ser molt senzill.

---

# Informació emergent

Quan el cursor passa per sobre d'una activitat:

mostrar:

Assignatura

Professor

Grup

Aula

Durada

Estat

No mostrar informació tècnica.

No mostrar identificadors interns.

---

# Colors

Els colors han de ser consistents.

Un mateix grup sempre utilitza el mateix color.

Els colors no poden canviar entre sessions.

Els conflictes sempre utilitzen el mateix vermell.

Els avisos sempre utilitzen el mateix taronja.

Les activitats correctes no han de destacar.

Només destaquen els problemes.

---

# Espais buits

Les hores lliures s'han de veure clarament.

No utilitzar quadrícules molt fosques.

El calendari ha de respirar.

La informació ha de ser fàcil de llegir encara que hi hagi moltes activitats.

---

# Rendiment

El calendari ha de continuar sent fluid amb:

- més de 500 activitats
- més de 30 professors
- més de 15 grups
- més de 25 aules

No s'han de redibuixar totes les activitats quan només canvia una.

Només s'ha d'actualitzar la part afectada.

---

# Objectiu final

L'usuari ha de tenir la sensació que està movent peces sobre una taula.

No ha de pensar en fitxers.

No ha de pensar en bases de dades.

No ha de pensar en algoritmes.

Només ha de veure un horari viu que respon immediatament a totes les seves accions.

---

# Panell esquerre

El panell esquerre és el centre de control de l'aplicació.

No ha de mostrar informació redundant.

Només ha de contenir eines per treballar.

Ha de poder plegar-se completament.

Amplada recomanada:

280-340 px.

---

# Contingut del panell esquerre

Ha d'incloure:

• Grups

• Professors

• Aules

• Assignatures

• Filtres

• Cerca

• Llegenda de colors

• Accions ràpides

---

# Filtres

L'usuari pot filtrar per:

- grup

- professor

- aula

- assignatura

- curs

- cicle

- departament

Els filtres es poden combinar.

Els filtres han de ser instantanis.

No s'ha de recarregar la pàgina.

---

# Cerca

La cerca ha de funcionar mentre l'usuari escriu.

Ha de trobar:

- professors

- grups

- assignatures

- aules

No cal prémer Enter.

---

# Llegenda

La llegenda explica:

- colors dels grups

- símbol de bloqueig

- conflictes

- avisos

- activitats manuals

- activitats generades automàticament

Ha d'ocupar poc espai.

---

# Accions ràpides

El panell esquerre incorpora accessos ràpids:

• Generar horari

• Compactar

• Reequilibrar

• Assignar dinars

• Assignar descansos

• Validar

• Exportar

• Importar

Aquestes accions sempre han de ser visibles.

---

# Panell dret

El panell dret mostra informació contextual.

Mai no substitueix el calendari.

Només mostra informació relacionada amb la selecció actual.

Si no hi ha cap selecció:

mostrar informació general.

---

# Informació d'una activitat

Quan una activitat està seleccionada es mostra:

Assignatura

Professor

Grup

Aula

Durada

Dia

Hora

Tipus

Bloquejada o no

Origen

Manual

Automàtica

Importada

---

# Restriccions

També es mostren les restriccions que afecten aquella activitat.

Per exemple:

Professor no disponible.

Aula especial.

Només matí.

Mínim dos dies.

Màxim tres dies.

Assignatura compartida.

Tallers consecutius.

---

# Botons

Des del panell dret es poden executar:

Editar

Duplicar

Eliminar

Bloquejar

Desbloquejar

Veure incidències

Veure historial

---

# Historial

Cada modificació queda registrada.

Per exemple:

Moviment manual.

Canvi d'aula.

Canvi de professor.

Canvi d'horari.

Bloqueig.

Desbloqueig.

L'historial ajuda a entendre com ha evolucionat l'horari.

---

# Desfer

Qualsevol acció ha de poder desfer-se.

No només els moviments.

També:

edicions

eliminacions

duplicacions

compactacions

assignacions automàtiques

---

# Refer

Després d'un Desfer s'ha de poder executar Refer.

No es perd l'historial fins que l'usuari fa una nova acció.

---

# Missatges

Els missatges han de ser molt breus.

Correcte:

"Activitat moguda."

Incorrecte:

"La modificació de la planificació acadèmica s'ha executat correctament."

---

# Confirmacions

Només demanar confirmació quan:

- s'elimina informació

- s'importa un horari

- es reinicia el calendari

Mai demanar confirmació per moure una activitat.

---

# Accessibilitat

Tota la interfície ha de poder utilitzar-se:

- només amb teclat

- amb lectors de pantalla

- amb zoom del navegador

- en pantalles grans

- en pantalles petites

---

# Tipografia

Utilitzar una única família tipogràfica sans-serif.

Per exemple:

Inter

Roboto

Noto Sans

No barrejar tipografies.

La jerarquia s'ha de crear amb:

pes

mida

espai

Mai amb colors cridaners.

---

# Icones

Utilitzar una única biblioteca.

Preferiblement:

Lucide

Heroicons

Les icones han de ser simples.

Mai decoratives.

Sempre han de reforçar el significat del text.

---

# Objectiu del panell dret

El panell dret ha de respondre una única pregunta:

"Per què aquesta activitat és aquí i què puc fer amb ella?"

No ha de convertir-se en un formulari enorme.

Ha de ser ràpid de llegir i encara més ràpid d'utilitzar.

---

# Rendiment

La interfície ha de continuar sent fluida fins i tot amb horaris grans.

Objectiu de rendiment:

- més de 700 activitats
- més de 40 professors
- més de 20 grups
- més de 30 aules

Les operacions habituals han de semblar instantànies.

Objectius orientatius:

- seleccionar una activitat < 50 ms
- obrir l'editor < 100 ms
- moure una activitat < 100 ms
- recalcular la visualització < 200 ms

Les validacions complexes poden executar-se en segon pla sempre que la interfície continuï responent.

---

# Actualització de la interfície

Quan canvia una activitat:

- només s'ha de redibuixar aquesta activitat
- s'han d'actualitzar únicament les incidències afectades
- no s'ha de reconstruir tot el calendari

S'ha d'evitar qualsevol parpelleig.

---

# Estat de l'aplicació

El frontend ha de treballar sempre amb un únic estat coherent.

No hi ha d'haver còpies diferents del mateix horari.

Qualsevol modificació ha de passar pels casos d'ús del backend.

La interfície mai no ha d'inventar dades.

---

# Sincronització

Després de qualsevol acció:

- moure
- editar
- eliminar
- afegir
- bloquejar
- desbloquejar

el calendari, el panell dret, les incidències i la puntuació han de quedar sincronitzats.

No poden existir estats intermedis visibles.

---

# Errors

Els errors s'han de comunicar de forma clara.

Exemples:

Correcte:

"No és possible moure aquesta activitat perquè el professor ja té classe."

Correcte:

"L'aula ja està ocupada."

Incorrecte:

"Validation error."

Incorrecte:

"Unexpected exception."

Els missatges han de ser comprensibles per un usuari no tècnic.

---

# Confirmacions

Quan una operació és correcta, només cal un missatge breu.

Exemples:

Activitat actualitzada.

Professor assignat.

Horari desat.

No calen diàlegs innecessaris.

---

# Colors

Els colors mai no han de ser l'únic mecanisme per transmetre informació.

Els conflictes també han de tenir:

- icona
- text
- ressalt visual

Per facilitar l'accessibilitat.

---

# Consistència

Una mateixa acció sempre ha de produir el mateix resultat.

No hi pot haver diferències entre:

- arrossegar
- editar
- menú contextual

Tots els camins han d'acabar executant la mateixa lògica del backend.

---

# Compatibilitat

El frontend ha de continuar funcionant encara que s'afegeixin:

- noves restriccions
- nous tipus d'activitats
- nous tipus d'aules
- nous tipus de professors

La interfície ha de ser extensible.

---

# Codi

Qualsevol modificació del frontend ha de respectar:

- components petits
- responsabilitat única
- reutilització
- noms clars
- eliminació de codi duplicat

No s'han de crear components enormes.

---

# Comunicació amb el backend

El frontend no implementa regles de negoci.

El backend és l'única font de veritat.

El frontend:

- envia accions
- rep resultats
- actualitza la interfície

No calcula conflictes pel seu compte.

No modifica directament l'estat intern.

---

# Objectiu del projecte

L'EMAD Scheduler no és un simple editor d'horaris.

És un assistent visual per construir horaris complexos mantenint totes les restriccions acadèmiques.

L'usuari ha de tenir la sensació que treballa sobre un calendari intel·ligent que:

- detecta problemes
- evita errors
- explica els conflictes
- proposa solucions
- manté sempre la coherència de l'horari

---

# Directrius per a qualsevol IA

Abans de modificar el frontend, qualsevol IA ha de respectar aquestes normes:

1. No eliminar funcionalitats existents sense una justificació clara.

2. No modificar el comportament del calendari si no és imprescindible.

3. No duplicar la lògica del backend al frontend.

4. Prioritzar sempre la claredat visual per davant dels efectes gràfics.

5. Mantenir la coherència amb la resta de l'aplicació.

6. Documentar qualsevol canvi rellevant.

7. Evitar regressions. Qualsevol canvi ha de conservar el comportament correcte de les funcionalitats existents.

8. Si existeixen dubtes sobre el funcionament esperat, preval aquest document per sobre de decisions arbitràries.

---

# Visió final

L'objectiu és construir la millor eina possible per generar i editar horaris acadèmics complexos.

La interfície ha de transmetre una sensació de control, confiança i rapidesa.

L'usuari no ha de lluitar contra el programa.

El programa ha d'ajudar l'usuari a prendre decisions, detectar problemes i construir el millor horari possible.