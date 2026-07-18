# EMAD Scheduler - AI Agent Guide

## Projecte

EMAD Scheduler és una aplicació per gestionar els horaris de l'Escola Municipal d'Art i Disseny de la Garriga.

L'objectiu és substituir FET per una interfície visual moderna.

Tecnologies:

- Backend: Python + FastAPI
- Frontend: React
- Base de dades: SQLite
- Font de dades: fitxer FET

---

## Regles

Mai eliminar funcionalitats existents.

Abans de modificar res:

1. Analitzar el projecte.
2. Explicar el pla.
3. Fer canvis petits.
4. Verificar que continua funcionant.

---

## Arquitectura

Backend

- Importa dades FET
- Gestiona conflictes
- Gestiona professors
- Gestiona grups
- Gestiona aules

Frontend

- Sidebar
- Toolbar
- Weekly Calendar
- Inspector

---

## Objectiu

Cada grup ha de tenir el seu propi horari.

No existeix un únic horari global.

Cada activitat conserva:

- professor
- aula
- durada
- grup
- restriccions

---

## Drag & Drop

Quan una activitat es mou:

- mantenir durada
- recalcular conflictes
- actualitzar backend

---

## Disseny

Inspiració:

- Figma
- Linear
- Google Calendar

No utilitzar interfícies tipus taula o Excel.

Utilitzar:

- targetes
- colors
- cantonades arrodonides
- animacions
- components reutilitzables

---

## Qualitat

Prioritzar:

- components petits
- codi reutilitzable
- tipatge
- documentació