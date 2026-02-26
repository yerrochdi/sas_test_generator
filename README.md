# SAS Data Generator

Generateur de datasets de test pour maximiser la couverture d'execution du code SAS.

## Principe

Cet outil analyse vos programmes SAS, detecte les branches (`IF/ELSE`, `SELECT/WHEN`,
`CASE/WHEN`), et genere automatiquement des datasets CSV avec des valeurs ciblees
pour passer dans le maximum de branches possibles.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Architecture technique et details de conception
- [docs/GUIDE_UTILISATION.md](docs/GUIDE_UTILISATION.md) — Guide d'utilisation complet (installation, CLI, CI/CD)
- [docs/COMMENT_CA_MARCHE.md](docs/COMMENT_CA_MARCHE.md) — Explication detaillee du fonctionnement interne

## Installation rapide

```bash
pip install git+https://github.com/yerrochdi/sas_test_generator.git
```

## Utilisation rapide

```bash
# Analyser un programme SAS
sas-datagen analyze mon_programme.sas

# Generer des datasets de test (sans SAS)
sas-datagen generate mon_programme.sas -o output/

# Boucle complete avec execution SAS
sas-datagen run mon_programme.sas --output output/ --max-iter 5 --target 90

# Projet multi-fichiers avec %INCLUDE
sas-datagen run --project-dir /mon/projet/sas/ --entry main.sas -o output/
```

## Pipeline Central (CI/CD)

Pour generer les datasets de tous vos projets SAS **sans modifier leurs repos
existants**, utilisez le pipeline central : voir [ci/central-pipeline/](ci/central-pipeline/).
