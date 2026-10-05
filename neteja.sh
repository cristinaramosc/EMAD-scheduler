#!/bin/sh
# Neteja de l'arrel del repo: paquets i parches ja aplicats. Executa'l des de l'arrel.
set -e
git rm -q --ignore-unmatch \
  emad-1q2q-changes.patch \
  emad-hores-centre-tutoria-auto.tar.gz \
  emad-tutoria-auto-assignacio.tar.gz \
  emad-pdf-vertical-rutes.patch \
  emad-pdf-vertical-v2.tar.gz emad-pdf-vertical-v2.tar.gz.b64 \
  emad-scheduler-accept-error.tar.gz emad-scheduler-accept-error.tar.gz.b64 \
  emad-scheduler-compaction-fix.tar.gz emad-scheduler-compaction-fix.tar.gz.b64 \
  emad-scheduler-complet-sessio.tar.gz emad-scheduler-complet-sessio.tar.gz.b64 \
  emad-scheduler-final.tar.gz emad-scheduler-final.tar.gz.b64 \
  emad-scheduler-frontend-declutter-v2.tar.gz emad-scheduler-frontend-declutter-v2.tar.gz.b64
# Perquè no hi tornin a entrar (els paquets de feina no van al repo)
grep -qxF 'emad-*.tar.gz*' .gitignore || printf '\n# Paquets de feina\nemad-*.tar.gz*\nemad-*.patch\n' >> .gitignore
git status --short | head -30
