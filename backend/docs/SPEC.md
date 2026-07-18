# EMAD Scheduler Functional Specification

## Actors

- Secretaria
- Professorat
- Administració

## Pantalla principal

Sidebar
- Cicles
- Grups
- Professors
- Aules

Toolbar
- Importar FET
- Exportar
- Desa
- Optimitzar

Calendari

- Dilluns a divendres
- Franges horàries
- Drag & Drop
- Colors per mòdul

Inspector

Mostra:

- Assignatura
- Professor
- Aula
- Durada
- Restriccions

## Regles

Una activitat:

- no es divideix
- manté la durada
- només pertany a un grup

Quan es mou:

- recalcular conflictes
- actualitzar backend
- actualitzar frontend