# Guide d'utilisation — SAS Data Generator

## Table des matieres

1. [Prerequis](#1-prerequis)
2. [Installation](#2-installation)
3. [Structure du projet attendue](#3-structure-du-projet-attendue)
4. [Commandes CLI](#4-commandes-cli)
   - 4.1 [analyze — Analyser un programme SAS](#41-analyze--analyser-un-programme-sas)
   - 4.2 [instrument — Voir le code instrumente](#42-instrument--voir-le-code-instrumente)
   - 4.3 [generate — Generer des datasets de test](#43-generate--generer-des-datasets-de-test)
   - 4.4 [run — Boucle complete avec execution SAS](#44-run--boucle-complete-avec-execution-sas)
5. [Projets multi-fichiers et %INCLUDE](#5-projets-multi-fichiers-et-include)
   - 5.1 [Mode projet (--project-dir)](#51-mode-projet---project-dir)
   - 5.2 [Chemins d'inclusion (--include-path)](#52-chemins-dinclusion---include-path)
   - 5.3 [Comment fonctionne la resolution](#53-comment-fonctionne-la-resolution)
   - 5.4 [Exemples concrets multi-fichiers](#54-exemples-concrets-multi-fichiers)
6. [Fichiers de configuration](#6-fichiers-de-configuration)
   - 5.1 [Variables macro (--macros)](#51-variables-macro---macros)
   - 5.2 [Mapping libname (--libnames)](#52-mapping-libname---libnames)
7. [Configuration de l'executable SAS](#7-configuration-de-lexecutable-sas)
8. [Comprendre les sorties](#8-comprendre-les-sorties)
9. [Integration GitLab CI/CD](#9-integration-gitlab-cicd)
10. [Scenarios d'utilisation](#10-scenarios-dutilisation)
11. [Points de couverture](#11-points-de-couverture)
12. [Tuning et optimisation](#12-tuning-et-optimisation)
13. [Depannage](#13-depannage)
14. [Limitations connues](#14-limitations-connues)

---

## 1. Prerequis

| Composant        | Version minimale | Obligatoire ?                         |
|------------------|------------------|---------------------------------------|
| Python           | 3.9+             | Oui                                   |
| pip              | 21+              | Oui                                   |
| SAS              | 9.4+             | Seulement pour la commande `run`      |
| pandas           | 2.0+             | Installe automatiquement              |
| typer            | 0.9+             | Installe automatiquement              |
| pyreadstat       | 1.2+             | Optionnel (export SAS7BDAT)           |

> **Note** : Les commandes `analyze`, `instrument` et `generate` ne necessitent
> **aucune installation SAS**. Seule la commande `run` execute SAS en batch.

---

## 2. Installation

### Depuis les sources (recommande)

```bash
# Cloner le repo
git clone <url-du-repo> sas_data_generator
cd sas_data_generator

# Installation en mode editable
pip install -e .

# Avec les dependances de developpement (tests, linter)
pip install -e ".[dev]"

# Avec le support SAS7BDAT (optionnel)
pip install -e ".[sas7bdat]"

# Tout installer
pip install -e ".[dev,sas7bdat]"
```

### Verifier l'installation

```bash
sas-datagen --version
# Affiche: sas-data-generator 0.1.0
```

---

## 3. Structure du projet attendue

L'outil s'attend a trouver vos programmes SAS quelque part sur le disque.
Voici l'organisation recommandee pour un repo GitLab :

```
mon-projet-sas/
├── sas_programs/           # Vos programmes SAS a analyser
│   ├── programme1.sas
│   ├── programme2.sas
│   └── sous_dossier/
│       └── programme3.sas
├── config/                 # Fichiers de configuration (optionnel)
│   ├── macros.json         # Variables macro SAS
│   └── libnames.json       # Mapping libname -> chemin
├── output/                 # Genere automatiquement
│   ├── datasets/           # Datasets CSV generes
│   ├── coverage/           # Rapports de couverture
│   └── final/              # Datasets finaux optimises
├── .gitlab-ci.yml          # Pipeline CI/CD
└── pyproject.toml          # sas-data-generator installe ici
```

---

## 4. Commandes CLI

### Vue d'ensemble

```
sas-datagen [OPTIONS] COMMAND [ARGS]

Commandes :
  analyze     Analyser un ou plusieurs fichiers SAS
  instrument  Afficher le code SAS instrumente
  generate    Generer des datasets de test (sans SAS)
  run         Boucle complete : generer + executer SAS + mesurer la couverture
```

Option globale :
- `--version`, `-V` : Afficher la version et quitter

---

### 4.1 `analyze` — Analyser un programme SAS

Analyse le code SAS et affiche les points de couverture detectes
et les variables identifiees. **Ne necessite pas SAS.**

```bash
sas-datagen analyze <fichiers_sas...> [OPTIONS]
```

**Arguments :**

| Argument          | Description                              |
|-------------------|------------------------------------------|
| `fichiers_sas`    | Un ou plusieurs fichiers `.sas` a analyser |

**Options :**

| Option            | Defaut  | Description                                |
|-------------------|---------|--------------------------------------------|
| `--verbose`, `-v` | `false` | Activer les logs detailles (niveau DEBUG)  |

**Exemple :**

```bash
# Analyser un seul fichier
sas-datagen analyze sas_programs/mon_programme.sas

# Analyser plusieurs fichiers
sas-datagen analyze sas_programs/*.sas

# Avec logs detailles
sas-datagen analyze sas_programs/mon_programme.sas -v
```

**Sortie :**

```
File: sas_programs/sample_program.sas
  Blocks: 2
  Coverage points: 18
  Variables: 5

┌─────────────────────┬──────────────┬──────┬──────────────────────┬──────────────────┐
│ ID                  │ Type         │ Line │ Description          │ Condition        │
├─────────────────────┼──────────────┼──────┼──────────────────────┼──────────────────┤
│ sample_program:1    │ STEP_ENTRY   │ 17   │ DATA step entry      │                  │
│ sample_program:2    │ IF_TRUE      │ 22   │ IF true: age < 25    │ age < 25         │
│ sample_program:3    │ IF_FALSE     │ 22   │ IF false: age < 25   │ age < 25         │
│ ...                 │ ...          │ ...  │ ...                  │ ...              │
└─────────────────────┴──────────────┴──────┴──────────────────────┴──────────────────┘
```

---

### 4.2 `instrument` — Voir le code instrumente

Affiche ou ecrit le code SAS apres injection des marqueurs de couverture.
Utile pour **debugger** et verifier ce que l'outil injecte.

```bash
sas-datagen instrument <fichier_sas> [OPTIONS]
```

**Arguments :**

| Argument        | Description                   |
|-----------------|-------------------------------|
| `fichier_sas`   | Le fichier `.sas` a instrumenter |

**Options :**

| Option              | Defaut    | Description                                |
|---------------------|-----------|--------------------------------------------|
| `--output`, `-o`    | `stdout`  | Fichier de sortie (affiche sur stdout si omis) |
| `--verbose`, `-v`   | `false`   | Logs detailles                             |

**Exemples :**

```bash
# Afficher sur stdout
sas-datagen instrument sas_programs/mon_programme.sas

# Sauvegarder dans un fichier
sas-datagen instrument sas_programs/mon_programme.sas -o output/instrumented.sas

# Verifier le code instrumente avant de lancer SAS
sas-datagen instrument sas_programs/mon_programme.sas -o /tmp/check.sas
cat /tmp/check.sas
```

---

### 4.3 `generate` — Generer des datasets de test

Analyse le code SAS, detecte les variables et conditions, et genere
des datasets CSV avec des valeurs ciblees. **Ne necessite pas SAS.**

```bash
sas-datagen generate <fichiers_sas...> [OPTIONS]
```

**Arguments :**

| Argument          | Description                              |
|-------------------|------------------------------------------|
| `fichiers_sas`    | Un ou plusieurs fichiers `.sas`          |

**Options :**

| Option              | Defaut     | Description                                              |
|---------------------|------------|----------------------------------------------------------|
| `--output`, `-o`    | `./output` | Repertoire de sortie pour les datasets                   |
| `--rows`, `-n`      | `20`       | Nombre de lignes par dataset                             |
| `--seed`, `-s`      | `42`       | Graine aleatoire (reproductibilite)                      |
| `--format`, `-f`    | `csv`      | Format(s) de sortie : `csv` et/ou `sas7bdat`            |
| `--verbose`, `-v`   | `false`    | Logs detailles                                           |

**Exemples :**

```bash
# Generation basique
sas-datagen generate sas_programs/mon_programme.sas

# Avec parametrage
sas-datagen generate sas_programs/mon_programme.sas \
  --output output/datasets \
  --rows 50 \
  --seed 123 \
  --format csv

# Generer en CSV et SAS7BDAT (necessite pyreadstat)
sas-datagen generate sas_programs/mon_programme.sas \
  --format csv --format sas7bdat \
  --output output/datasets

# Traiter tous les fichiers SAS d'un dossier
sas-datagen generate sas_programs/*.sas -o output/datasets -n 30
```

**Logique de generation :**

1. Le parseur detecte les datasets d'entree (`SET`, `MERGE`, `FROM`)
2. Il identifie les variables et leurs types (numerique, caractere, date)
3. Il extrait les seuils des conditions (`age > 65` → genere 64, 65, 66)
4. Il ajoute des valeurs limites (0, -1, vide, NULL, extremes)
5. Le tout est exporte en CSV dans le dossier de sortie

**A propos du seed :**

Le parametre `--seed` garantit que **deux executions avec le meme seed
produisent les memes datasets**. C'est essentiel pour la reproductibilite
en CI. Changez le seed pour obtenir des variations differentes.

---

### 4.4 `run` — Boucle complete avec execution SAS

C'est la commande principale. Elle orchestre tout le cycle :
1. Analyse du code SAS
2. Instrumentation (injection des marqueurs)
3. Generation des datasets initiaux
4. Execution SAS en batch
5. Lecture de la couverture
6. Mutation des datasets pour cibler les branches manquees
7. Re-execution (boucle jusqu'au seuil ou max iterations)

```bash
sas-datagen run <fichiers_sas...> [OPTIONS]
```

**Arguments :**

| Argument          | Description                              |
|-------------------|------------------------------------------|
| `fichiers_sas`    | Un ou plusieurs fichiers `.sas`          |

**Options — Generation :**

| Option              | Defaut     | Description                                              |
|---------------------|------------|----------------------------------------------------------|
| `--output`, `-o`    | `./output` | Repertoire de sortie (datasets + rapports)               |
| `--rows`, `-n`      | `20`       | Nombre de lignes dans les datasets initiaux               |
| `--seed`, `-s`      | `42`       | Graine aleatoire                                         |
| `--format`, `-f`    | `csv`      | Format(s) de sortie : `csv` et/ou `sas7bdat`            |

**Options — Execution SAS :**

| Option              | Defaut     | Description                                              |
|---------------------|------------|----------------------------------------------------------|
| `--sas`             | auto-detect| Chemin vers l'executable SAS                              |
| `--timeout`         | `300`      | Timeout d'execution SAS en secondes                      |
| `--dry-run`         | `false`    | Sauter l'execution SAS (genere les fichiers seulement)   |

**Options — Boucle de couverture :**

| Option              | Defaut     | Description                                              |
|---------------------|------------|----------------------------------------------------------|
| `--max-iter`, `-i`  | `5`        | Nombre maximum d'iterations de mutation                   |
| `--target`, `-t`    | `100.0`    | Objectif de couverture en % (arrete quand atteint)       |

**Options — Configuration SAS :**

| Option              | Defaut     | Description                                              |
|---------------------|------------|----------------------------------------------------------|
| `--macros`          | aucun      | Chemin vers un fichier JSON de variables macro            |
| `--libnames`        | aucun      | Chemin vers un fichier JSON de mapping libname            |
| `--verbose`, `-v`   | `false`    | Logs detailles                                           |

**Exemples :**

```bash
# Boucle complete (SAS doit etre installe)
sas-datagen run sas_programs/mon_programme.sas \
  --output output/coverage \
  --rows 30 \
  --max-iter 5 \
  --target 90

# Dry-run (pas besoin de SAS, teste le pipeline)
sas-datagen run sas_programs/mon_programme.sas \
  --output output/test \
  --dry-run

# Avec un executable SAS specifique
sas-datagen run sas_programs/mon_programme.sas \
  --sas /opt/SASHome/SASFoundation/9.4/sas \
  --timeout 600

# Avec macros et libnames
sas-datagen run sas_programs/mon_programme.sas \
  --macros config/macros.json \
  --libnames config/libnames.json \
  --output output/coverage \
  --max-iter 10 \
  --target 95

# Traiter plusieurs programmes
sas-datagen run sas_programs/*.sas \
  --output output/coverage \
  --rows 50 \
  --verbose
```

**Code de retour :**

| Code | Signification                                       |
|------|-----------------------------------------------------|
| `0`  | Couverture cible atteinte                           |
| `1`  | Couverture cible NON atteinte apres toutes les iterations |

Utile en CI pour echouer le pipeline si la couverture est insuffisante.

---

## 5. Projets multi-fichiers et %INCLUDE

La plupart des projets SAS reels utilisent plusieurs fichiers :
un programme principal qui fait des `%INCLUDE` vers des macros,
des initialisations, et des etapes de traitement.

L'outil gere ce cas avec deux options : `--project-dir` et `--include-path`.

### 5.1 Mode projet (`--project-dir`)

Quand tu as un repertoire de projet SAS complet :

```
/projets/sas/projet_A/
├── main.sas                 <- point d'entree
├── macros/
│   ├── macro_risque.sas
│   └── macro_calcul.sas
├── includes/
│   └── init.sas
└── programmes/
    ├── etape1.sas
    └── etape2.sas
```

Tu pointes vers le repertoire avec `--project-dir` et tu indiques
le fichier d'entree avec `--entry` :

```bash
# Analyser tout le projet
sas-datagen analyze \
  --project-dir /projets/sas/projet_A/ \
  --entry main.sas

# Generer les datasets pour tout le projet
sas-datagen generate \
  --project-dir /projets/sas/projet_A/ \
  --entry main.sas \
  --output output/

# Boucle complete
sas-datagen run \
  --project-dir /projets/sas/projet_A/ \
  --entry main.sas \
  --output output/ \
  --dry-run
```

**Ce qui se passe** :
1. L'outil scanne le repertoire et trouve tous les `.sas`
2. Il lit `main.sas` et suit chaque `%INCLUDE`
3. Il inline le contenu de chaque fichier inclus
4. Il parse le code complet resolu (comme si tout etait dans un seul fichier)
5. Il genere les datasets en analysant TOUTES les branches de TOUS les fichiers

**Detection automatique du point d'entree** :

Si tu ne specifies pas `--entry`, l'outil cherche un fichier nomme :
`main.sas`, `run_all.sas`, `autoexec.sas`, `master.sas`, ou `run.sas`.

### 5.2 Chemins d'inclusion (`--include-path`)

Si tu ne veux pas utiliser le mode projet mais que tes fichiers font
des `%INCLUDE` vers d'autres repertoires, utilise `--include-path` :

```bash
# Le fichier main.sas fait %include "macro_risque.sas"
# mais ce fichier est dans un autre dossier
sas-datagen analyze main.sas \
  --include-path /projets/sas/macros \
  --include-path /projets/sas/includes

# Plusieurs chemins possibles
sas-datagen run main.sas \
  --include-path ./macros \
  --include-path ./includes \
  --include-path /shared/sas/common_macros \
  --output output/
```

**Ordre de recherche des fichiers inclus** :

1. Chemin absolu (si le `%INCLUDE` donne un chemin absolu)
2. Relatif au fichier qui fait le `%INCLUDE`
3. Chaque repertoire `--include-path`, dans l'ordre
4. Sous-repertoires du repertoire parent du fichier d'entree

### 5.3 Comment fonctionne la resolution

Quand l'outil rencontre :

```sas
%include "macros/macro_risque.sas";
```

Il :
1. Cherche le fichier dans les chemins configures
2. Lit son contenu
3. Remplace la ligne `%INCLUDE` par le contenu du fichier
4. Si ce fichier contient lui-meme des `%INCLUDE`, il les resout aussi (recursif)
5. Detecte et signale les inclusions circulaires

**Patterns supportes** :

```sas
%include "chemin/fichier.sas";        /* double quotes */
%include 'chemin/fichier.sas';        /* single quotes */
%inc "fichier.sas";                   /* forme courte %inc */
%include "&MACRO_VAR./fichier.sas";   /* variable macro dans le chemin */
```

**Variables macro dans les chemins** :

Si tes `%INCLUDE` utilisent des variables macro dans les chemins
(ex: `%include "&ROOT./macros/init.sas"`), fournis-les via `--macros` :

```json
{
  "ROOT": "/projets/sas/projet_A"
}
```

```bash
sas-datagen run main.sas \
  --macros config/macros.json \
  --include-path /projets/sas/
```

### 5.4 Exemples concrets multi-fichiers

**Cas 1 : Projet avec macros dans un sous-dossier**

```
mon_projet/
├── main.sas           ← %include "macros/calc.sas";
└── macros/
    └── calc.sas       ← contient des IF/ELSE
```

```bash
# L'outil trouve automatiquement macros/calc.sas (sous-dossier)
sas-datagen analyze --project-dir mon_projet/ --entry main.sas
```

**Cas 2 : Macros partagees dans un repertoire commun**

```
/projets/sas/
├── commun/            ← macros partagees entre projets
│   └── utils.sas
├── projet_A/
│   └── main.sas      ← %include "/projets/sas/commun/utils.sas";
└── projet_B/
    └── main.sas
```

```bash
sas-datagen run /projets/sas/projet_A/main.sas \
  --include-path /projets/sas/commun
```

**Cas 3 : Plusieurs niveaux d'inclusion**

`main.sas` inclut `init.sas` qui inclut `formats.sas` :

```bash
# L'outil suit toute la chaine automatiquement
sas-datagen analyze --project-dir mon_projet/ --entry main.sas -v
# Les logs montrent chaque fichier resolu :
#   Resolved: init.sas -> /chemin/includes/init.sas
#   Resolved: formats.sas -> /chemin/includes/formats.sas
```

---

## 6. Fichiers de configuration

### 5.1 Variables macro (`--macros`)

Fichier JSON definissant des variables macro SAS injectees au debut
du programme. Utile quand vos programmes SAS dependent de `%let` ou
`&variable` definies ailleurs.

**Fichier : `config/macros.json`**

```json
{
  "ENV": "TEST",
  "DATE_REF": "01JAN2025",
  "SEUIL_AGE": "65",
  "NB_MOIS": "12",
  "CHEMIN_DATA": "/data/test"
}
```

Cela genere dans le code SAS, avant votre programme :

```sas
%let ENV = TEST;
%let DATE_REF = 01JAN2025;
%let SEUIL_AGE = 65;
%let NB_MOIS = 12;
%let CHEMIN_DATA = /data/test;
```

**Usage :**

```bash
sas-datagen run programme.sas --macros config/macros.json
```

### 5.2 Mapping libname (`--libnames`)

Fichier JSON mappant les librefs SAS vers des chemins physiques.
Indispensable si vos programmes SAS referent des librairies
(`mylib.dataset` au lieu de `work.dataset`).

**Fichier : `config/libnames.json`**

```json
{
  "mylib": "/data/shared/mylib",
  "refdata": "/data/reference",
  "outlib": "./output/sas_output"
}
```

Cela genere :

```sas
libname mylib "/data/shared/mylib";
libname refdata "/data/reference";
libname outlib "/chemin/absolu/output/sas_output";
```

> **Note** : Les chemins relatifs sont resolus en chemins absolus
> automatiquement. Les repertoires sont crees s'ils n'existent pas.

**Usage :**

```bash
sas-datagen run programme.sas --libnames config/libnames.json
```

**Combinaison macros + libnames :**

```bash
sas-datagen run programme.sas \
  --macros config/macros.json \
  --libnames config/libnames.json
```

---

## 7. Configuration de l'executable SAS

L'outil cherche l'executable SAS dans cet ordre :

1. **Option CLI** : `--sas /chemin/vers/sas`
2. **Variable d'environnement** : `SAS_EXECUTABLE`
3. **PATH systeme** : commande `sas`
4. **Chemins standards** :
   - `/usr/local/SASHome/SASFoundation/9.4/sas`
   - `/opt/sas/sas`
   - `/usr/local/bin/sas`

**Recommandation pour le serveur :**

```bash
# Methode 1 : Variable d'environnement (recommande)
export SAS_EXECUTABLE="/chemin/vers/votre/sas"
sas-datagen run programme.sas

# Methode 2 : Option CLI
sas-datagen run programme.sas --sas /chemin/vers/votre/sas

# Methode 3 : Verifier que SAS est sur le PATH
which sas
# /usr/local/bin/sas  -> OK, l'outil le trouvera tout seul
```

**Commande SAS executee :**

L'outil lance SAS avec ces options :

```bash
sas -batch -noterminal -nologo \
  -log <workdir>/_sas_datagen_run.log \
  -print <workdir>/_sas_datagen_run.lst \
  -work <workdir> \
  <workdir>/_sas_datagen_run.sas
```

Si vous avez un `autoexec.sas` a charger, vous pouvez l'ajouter
en modifiant le code (support via `autoexec_path` dans l'API Python,
pas encore expose en CLI — prevu pour V1).

---

## 8. Comprendre les sorties

### 7.1 Arborescence de sortie

Apres `sas-datagen run programme.sas -o output/ --max-iter 3` :

```
output/
├── programme_instrumented.sas     # Code SAS avec marqueurs injectes
├── programme_coverage.csv         # Coverage CSV genere par SAS
├── programme_coverage_report.json # Rapport de couverture (machine)
├── programme_coverage_report.txt  # Rapport de couverture (humain)
├── iter_0/                        # Iteration 0 (seed initial)
│   ├── customers.csv              # Dataset genere
│   └── _sas_datagen_run.sas       # Code SAS complet execute
│   └── _sas_datagen_run.log       # Log SAS
├── iter_1/                        # Iteration 1 (premiere mutation)
│   ├── customers.csv
│   └── ...
├── iter_2/                        # Iteration 2
│   └── ...
└── final/                         # Datasets finaux (apres toutes les iterations)
    └── customers.csv
```

### 7.2 Rapport de couverture JSON

Fichier : `*_coverage_report.json`

```json
{
  "total_points": 18,
  "hit_points": 15,
  "coverage_pct": 83.33,
  "is_complete": true,
  "hit_point_ids": [
    "sample_program:1",
    "sample_program:2",
    "..."
  ],
  "missed_point_ids": [
    "sample_program:7",
    "sample_program:12",
    "sample_program:16"
  ],
  "missed_details": [
    {
      "point_id": "sample_program:7",
      "type": "IF_FALSE",
      "line": 35,
      "description": "IF false/ELSE: age >= 45 and age < 65",
      "condition": "age >= 45 and age < 65"
    }
  ]
}
```

**Champs :**

| Champ              | Description                                          |
|--------------------|------------------------------------------------------|
| `total_points`     | Nombre total de points de couverture instrumentes    |
| `hit_points`       | Nombre de points atteints (au moins une fois)        |
| `coverage_pct`     | Pourcentage de couverture                            |
| `is_complete`      | `true` si SAS a termine normalement                  |
| `hit_point_ids`    | Liste des IDs des points atteints                    |
| `missed_point_ids` | Liste des IDs des points manques                     |
| `missed_details`   | Detail de chaque point manque (type, ligne, condition)|

### 7.3 Rapport de couverture texte

Fichier : `*_coverage_report.txt`

```
Coverage: 15/18 (83.3%)
  Hit:    ['sample_program:1', 'sample_program:2', ...]
  Missed: ['sample_program:7', 'sample_program:12', 'sample_program:16']

Missed Points Detail:
  [sample_program:7] IF_FALSE line 35: IF false/ELSE: age >= 45 and age < 65
    Condition: age >= 45 and age < 65
  [sample_program:12] SELECT_OTHERWISE line 52: OTHERWISE branch
  [sample_program:16] SQL_CASE_ELSE line 74: CASE ELSE branch
```

### 7.4 Code instrumente

Le fichier `*_instrumented.sas` contient votre code SAS original
avec les marqueurs injectes. Vous pouvez l'ouvrir pour verifier
ce qui a ete injecte :

```sas
/* === Marqueur de couverture injecte === */
put "COV:POINT=sample_program:2";
```

Ces marqueurs ecrivent dans le log SAS des lignes au format
`COV:POINT=<id>` qui sont ensuite parsees pour calculer la couverture.

---

## 9. Integration GitLab CI/CD

### 8.1 Organisation du repo GitLab

```
mon-repo/
├── sas_programs/           # OBLIGATOIRE : vos fichiers .sas ici
│   └── *.sas
├── config/                 # OPTIONNEL
│   ├── macros.json
│   └── libnames.json
├── src/                    # sas-data-generator (ou pip install depuis PyPI)
├── pyproject.toml
└── .gitlab-ci.yml          # Copier depuis le modele fourni
```

> Le pipeline detecte automatiquement les fichiers `sas_programs/*.sas`.
> Si aucun fichier `.sas` n'est present dans ce dossier, les stages
> `generate` et `coverage` sont ignores.

### 8.2 Variables CI/CD a configurer

Dans **Settings > CI/CD > Variables** de votre projet GitLab :

| Variable            | Obligatoire | Description                                        | Exemple                                          |
|---------------------|-------------|----------------------------------------------------|--------------------------------------------------|
| `SAS_EXECUTABLE`    | Si SAS pas sur PATH | Chemin absolu de l'executable SAS            | `/usr/local/SASHome/SASFoundation/9.4/sas`       |
| `SAS_DOCKER_IMAGE`  | Non         | Image Docker custom avec SAS (si applicable)       | `registry.example.com/sas:9.4`                   |
| `MACRO_VARS_FILE`   | Non         | Chemin vers le fichier JSON des macros             | `config/macros.json`                             |
| `LIBNAME_FILE`      | Non         | Chemin vers le fichier JSON des libnames           | `config/libnames.json`                           |

### 8.3 Stages du pipeline

```
lint ──> test ──> generate ──> coverage ──> report
                               │     │
                          (avec SAS) (dry-run)
```

| Stage       | Job                | SAS requis ? | Declenchement      | Description                                  |
|-------------|--------------------|--------------|--------------------|----------------------------------------------|
| `lint`      | `lint`             | Non          | Automatique        | Verification qualite code (ruff)             |
| `test`      | `unit-tests`       | Non          | Automatique        | Tests unitaires pytest + couverture Python   |
| `generate`  | `generate-datasets`| Non          | Si `*.sas` existe  | Genere les datasets CSV                      |
| `coverage`  | `sas-coverage`     | **Oui**      | **Manuel**         | Execute SAS + mesure couverture              |
| `coverage`  | `sas-coverage-dry` | Non          | Si `*.sas` existe  | Dry-run (valide le pipeline sans SAS)        |
| `report`    | `coverage-report`  | Non          | Apres coverage     | Affiche les rapports dans le log CI          |

> **Important** : Le job `sas-coverage` est en declenchement **manuel**
> car il necessite un runner avec SAS installe. Cliquez sur le bouton "Play"
> dans l'interface GitLab pour le lancer.

**Artifacts produits :**

- `report.xml` — Rapport JUnit (tests Python)
- `coverage.xml` — Rapport Cobertura (couverture Python)
- `htmlcov/` — Rapport HTML de couverture Python
- `output/datasets/*.csv` — Datasets generes
- `output/coverage/*` — Rapports de couverture SAS + logs + code instrumente

### 8.4 Personnalisation du pipeline

**Changer le nombre de lignes generees :**

Dans `.gitlab-ci.yml`, modifiez `--rows` :

```yaml
sas-datagen generate sas_programs/*.sas --rows 100
```

**Changer l'objectif de couverture :**

```yaml
sas-datagen run sas_programs/*.sas --target 80
```

**Augmenter le nombre d'iterations :**

```yaml
sas-datagen run sas_programs/*.sas --max-iter 10
```

**Augmenter le timeout SAS :**

```yaml
sas-datagen run sas_programs/*.sas --timeout 600
```

**Utiliser un tag de runner specifique :**

```yaml
sas-coverage:
  tags:
    - sas
    - linux
```

---

## 10. Scenarios d'utilisation

### 9.1 Utilisation locale sans SAS

Vous n'avez pas SAS sur votre poste mais voulez preparer les datasets :

```bash
# 1. Analyser le code
sas-datagen analyze mon_programme.sas

# 2. Generer les datasets
sas-datagen generate mon_programme.sas -o output/ -n 50

# 3. Verifier le code instrumente
sas-datagen instrument mon_programme.sas -o output/instrumented.sas

# 4. Copier les datasets sur le serveur SAS et executer manuellement
scp output/*.csv serveur_sas:/data/test/
scp output/instrumented.sas serveur_sas:/data/test/
```

### 9.2 Utilisation locale avec SAS

SAS est installe sur votre machine :

```bash
# Verifier que SAS est trouve
export SAS_EXECUTABLE=/opt/sas/sas

# Boucle complete
sas-datagen run mon_programme.sas \
  --output output/ \
  --rows 30 \
  --max-iter 5 \
  --target 90 \
  --verbose

# Consulter les resultats
cat output/mon_programme_coverage_report.txt
python -m json.tool output/mon_programme_coverage_report.json
```

### 9.3 Utilisation en CI avec SAS

1. Copiez `.gitlab-ci.yml` dans votre repo
2. Placez vos `.sas` dans `sas_programs/`
3. Configurez `SAS_EXECUTABLE` dans les variables CI/CD
4. Poussez — le pipeline demarre automatiquement
5. Le job `sas-coverage` se lance manuellement (bouton Play)
6. Les artifacts sont telechargeables depuis l'interface GitLab

### 9.4 Traiter plusieurs programmes SAS

```bash
# Tous les fichiers d'un dossier
sas-datagen run sas_programs/*.sas -o output/

# Fichiers specifiques
sas-datagen run prog1.sas prog2.sas prog3.sas -o output/

# Chaque programme produit ses propres rapports :
#   output/prog1_coverage_report.json
#   output/prog2_coverage_report.json
#   output/prog3_coverage_report.json
```

La couverture globale est calculee et affichee a la fin :

```
=== Overall Coverage: 87.5% ===
  Missed points (3):
    [prog1:7] IF false/ELSE: age >= 65
    [prog2:4] SELECT OTHERWISE
    [prog3:11] CASE ELSE branch
```

---

## 11. Points de couverture

L'outil detecte et instrumente les types de branches suivants :

| Type               | Construct SAS                 | Ce qui est mesure                       |
|--------------------|-------------------------------|-----------------------------------------|
| `STEP_ENTRY`       | `DATA ...;` / `PROC SQL;`    | Le step a ete execute                   |
| `IF_TRUE`          | `IF condition THEN`           | La condition a ete evaluee a VRAI       |
| `IF_FALSE`         | `ELSE` (ou absence de ELSE)   | La condition a ete evaluee a FAUX       |
| `SELECT_WHEN`      | `WHEN (condition)`            | Le WHEN a matche au moins une ligne     |
| `SELECT_OTHERWISE` | `OTHERWISE`                   | Aucun WHEN n'a matche                   |
| `SQL_WHERE`        | `WHERE condition`             | Le SQL avec ce WHERE a ete execute      |
| `SQL_CASE_WHEN`    | `CASE WHEN condition THEN`    | Le bloc SQL contenant ce CASE a ete execute |
| `SQL_CASE_ELSE`    | `CASE ... ELSE`               | Le bloc SQL contenant ce CASE a ete execute |

> **Limitation MVP** : Pour PROC SQL, la couverture est au niveau du
> **bloc SQL** et non au niveau de chaque ligne de donnees. Cela signifie
> que le CASE_WHEN est marque comme "atteint" si le SQL s'execute,
> meme si aucune ligne ne passe dans ce WHEN specifique.

---

## 12. Tuning et optimisation

### Nombre de lignes (`--rows`)

| Valeur | Usage                                                    |
|--------|----------------------------------------------------------|
| `10`   | Tests rapides, validation de pipeline                     |
| `20`   | Defaut, bon compromis vitesse/couverture                 |
| `50`   | Recommande pour des programmes avec beaucoup de branches |
| `100+` | Programmes complexes avec des conditions combinees        |

### Nombre d'iterations (`--max-iter`)

| Valeur | Usage                                                    |
|--------|----------------------------------------------------------|
| `1`    | Pas de mutation, seulement le seed initial               |
| `3`    | Rapide, suffisant pour la majorite des cas               |
| `5`    | Defaut, bon compromis                                    |
| `10`   | Programmes tres branches avec conditions combinees       |

### Objectif de couverture (`--target`)

| Valeur | Signification                                            |
|--------|----------------------------------------------------------|
| `100`  | Viser 100% (defaut, peut ne jamais etre atteint)         |
| `90`   | Recommande pour CI (certaines branches sont inatteignables)|
| `80`   | Seuil minimum raisonnable                                |

### Seed (`--seed`)

- **Meme seed = memes datasets** (reproductibilite)
- Changez le seed pour explorer differentes valeurs aleatoires
- En CI, gardez un seed fixe pour des builds reproductibles

---

## 13. Depannage

### "SAS executable not found"

```
FileNotFoundError: SAS executable not found. Set SAS_EXECUTABLE...
```

**Solution :**
```bash
# Trouver le chemin SAS
find / -name "sas" -type f 2>/dev/null
# ou
which sas

# Le definir
export SAS_EXECUTABLE=/chemin/trouve
```

### "No coverage points found"

Le parseur n'a pas detecte de branches dans votre code.

**Causes possibles :**
- Le code n'a pas de IF/ELSE, SELECT/WHEN ou PROC SQL avec CASE
- Le code utilise des macros (`%IF/%THEN`) que le parseur MVP ne gere pas
- Les blocs sont dans des `%INCLUDE` non resolus

**Solution :** Utiliser `analyze` pour verifier ce qui est detecte :
```bash
sas-datagen analyze mon_programme.sas -v
```

### "SAS errors found"

Des erreurs SAS dans le log. Verifiez :
```bash
# Consulter le log SAS complet
cat output/iter_0/_sas_datagen_run.log | grep ERROR
```

**Causes frequentes :**
- Dataset d'entree manquant (le nom detecte ne correspond pas)
- Libname non defini (ajouter `--libnames`)
- Variable macro non definie (ajouter `--macros`)

### Les datasets generes n'ont pas les bonnes colonnes

Le parseur infere les colonnes depuis les conditions (`IF age > 65`)
et les statements `INPUT`. Si vos variables viennent d'un `SET` sans
conditions, elles ne seront pas detectees.

**Contournement :** Ajoutez un commentaire avec les variables attendues
ou utilisez un fichier de configuration (prevu pour V1).

---

## 14. Limitations connues

| Limitation                             | Impact                                         | Contournement                           |
|----------------------------------------|------------------------------------------------|-----------------------------------------|
| Macros `%IF/%THEN` non instrumentees   | Branches macro invisibles                      | Deployer les macros avant analyse       |
| `%INCLUDE` non resolus                 | Code inclus non analyse                        | Concatener les fichiers manuellement    |
| Parseur regex (pas AST)               | Faux positifs possibles dans commentaires/strings| Verifier avec `instrument`             |
| PROC SQL CASE = couverture bloc        | Pas de couverture par-ligne-de-donnee          | Analyser les outputs manuellement       |
| Pas de support arrays SAS             | Boucles DO sur arrays ignorees                 | -                                       |
| Formats/informats basiques            | Types de variables parfois mal inferes         | Verifier avec `analyze`                 |
| Conditions combinees (AND/OR)          | Chaque IF est un seul point (pas MC/DC)        | Augmenter `--rows` pour plus de combinaisons |
