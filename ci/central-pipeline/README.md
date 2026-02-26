# Pipeline Central — Génération de Données de Test SAS

Ce répertoire contient un pipeline CI/CD **autonome** qui génère des datasets
de test pour vos projets SAS, **sans modifier les repos SAS existants**.

## Principe

```
┌─────────────────────────────────────────────────────────┐
│  Repo central (ce repo)                                 │
│                                                         │
│  projects.yml ──→ Liste vos projets SAS                 │
│       │                                                 │
│       ▼                                                 │
│  .gitlab-ci.yml ──→ Pipeline qui:                       │
│       │             1. Clone chaque projet SAS           │
│       │             2. Installe sas-datagen              │
│       │             3. Génère les datasets               │
│       │             4. Publie en artifacts               │
│       ▼                                                 │
│  output/                                                │
│    ├── scoring-client/     ← datasets projet 1          │
│    ├── reporting-mensuel/  ← datasets projet 2          │
│    └── ...                                              │
└─────────────────────────────────────────────────────────┘
```

**Vos repos SAS ne sont PAS modifiés.** Ce repo les clone en lecture seule.

## Mise en place

### 1. Créer le repo GitLab

```bash
# Créer un nouveau repo GitLab et y copier ces fichiers:
# - .gitlab-ci.yml
# - projects.yml
# - scripts/generate.sh
```

### 2. Configurer `projects.yml`

Éditez `projects.yml` pour lister vos projets SAS:

```yaml
projects:
  - name: mon-projet
    repo: https://gitlab.example.com/equipe/mon-projet-sas.git
    branch: main
    entry: programmes/main.sas
    include_paths:
      - macros/
      - includes/
    macro_vars:
      ENV: RECETTE
    rows: 50
    enabled: true
```

| Champ           | Description                              | Obligatoire |
|-----------------|------------------------------------------|-------------|
| `name`          | Nom unique du projet                     | oui         |
| `repo`          | URL du repo GitLab (HTTPS ou SSH)        | oui         |
| `branch`        | Branche à cloner                         | non (main)  |
| `entry`         | Fichier SAS principal                    | non (auto)  |
| `include_paths` | Répertoires pour résoudre les %INCLUDE   | non         |
| `macro_vars`    | Variables macro SAS (&VAR.)              | non         |
| `rows`          | Nombre de lignes à générer               | non (30)    |
| `enabled`       | Activer/désactiver le projet             | non (true)  |

### 3. Configurer les variables CI/CD

Dans **Settings > CI/CD > Variables** du repo central:

| Variable         | Description                                    | Type     |
|------------------|------------------------------------------------|----------|
| `GITLAB_TOKEN`   | Token avec accès `read_repository` aux repos SAS | Secret  |
| `SAS_EXECUTABLE` | Chemin vers SAS (si pas sur PATH)               | Variable |

> **GITLAB_TOKEN**: Créez un Project Access Token ou Personal Access Token
> avec le scope `read_repository` pour que le pipeline puisse cloner vos repos SAS privés.

### 4. Lancer le pipeline

**Manuellement**: GitLab > CI/CD > Pipelines > Run pipeline

**Planifié**: GitLab > CI/CD > Schedules > New schedule (ex: tous les lundis à 8h)

**Sur push**: Automatiquement à chaque push dans ce repo

## Structure du pipeline

```
setup ──→ generate ──→ coverage ──→ report
           │              │
           │              └── Exécute SAS (runner avec tag 'sas')
           │                  Déclenché manuellement
           │
           └── Génère les datasets sans SAS (dry-run)
               Automatique à chaque push
```

| Stage      | Description                                | SAS requis ? | Déclenchement |
|------------|--------------------------------------------|-------------|---------------|
| `setup`    | Installe l'outil sas-datagen               | Non         | Auto          |
| `generate` | Clone les projets + génère les datasets    | Non         | Auto          |
| `coverage` | Exécute SAS + mesure la couverture         | Oui         | Manuel        |
| `report`   | Rapport de synthèse multi-projets          | Non         | Auto          |

## Utilisation locale

Vous pouvez aussi exécuter le script en local:

```bash
# Installer l'outil
pip install git+https://github.com/yerrochdi/sas_test_generator.git
pip install pyyaml

# Générer les datasets (sans SAS)
./scripts/generate.sh --config projects.yml --output output --dry-run --verbose

# Générer pour un seul projet
./scripts/generate.sh --project scoring-client --dry-run --verbose

# Avec SAS (si disponible sur la machine)
./scripts/generate.sh --config projects.yml --output output --verbose
```

## Récupérer les datasets générés

Les datasets sont publiés en **artifacts GitLab**:

1. Allez dans **CI/CD > Pipelines**
2. Cliquez sur le pipeline terminé
3. Job `generate-datasets` > **Download artifacts**
4. Les CSV sont dans `output/<nom-projet>/`

Ou via l'API:

```bash
curl --header "PRIVATE-TOKEN: $TOKEN" \
  "https://gitlab.example.com/api/v4/projects/$PROJECT_ID/jobs/artifacts/main/download?job=generate-datasets" \
  --output artifacts.zip
```
