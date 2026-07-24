# EMAD-Scheduler

## Visió

EMAD-Scheduler és un editor visual d'horaris intel·ligent.

L'usuari no ha de conèixer les restriccions del sistema.

Ha de poder editar l'horari de forma natural mentre el motor resol automàticament els conflictes.

---

# Estat del projecte

## Prompt 1 · Redisseny del frontend (només UI)

Estat: 🟢 Gairebé complet

Implementat

- Nou calendari
- Targetes
- Sidebar
- Estadístiques

Pendent

- petits ajustos visuals

---

## Prompt 2 · Nou panell d'incidències

Estat: 🟢

Implementat

- incidències
- activitats sense planificar

Pendent

- mostrar totes les explicacions

---

## Prompt 3 · Explicar els motius de cada incidència

Estat: 🟡

Objectiu

Eliminar tots els missatges genèrics.

---

## Prompt 4 · Drag & Drop robust

Estat: 🟡

Implementat

- drag
- drop

Pendent

- moviment backend
- robustesa

---

## Prompt 5 · Moure damunt d'una casella ocupada

Estat: 🔴

Objectiu

Permetre deixar una activitat damunt d'una altra.

No mostrar error immediat.

Intentar:

1. swap
2. reorganització local
3. explicació

---

## Prompt 6 · Assistent de resolució

Estat: ⚪

Objectiu

Proposar moviments intel·ligents per eliminar incidències.

---

# Principis

- Backend intel·ligent.
- Frontend senzill.
- Explicacions clares.
- Canvis petits.
- Tests sempre que sigui possible.