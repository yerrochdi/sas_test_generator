# Comment ca marche — SAS Data Generator

## Table des matieres

1. [Vue d'ensemble](#1-vue-densemble)
2. [Le cycle complet en 6 etapes](#2-le-cycle-complet-en-6-etapes)
3. [Module par module](#3-module-par-module)
   - 3.1 [sas_parser.py — Le parseur](#31-sas_parserpy--le-parseur)
   - 3.2 [sas_instrumenter.py — L'instrumenteur](#32-sas_instrumenterpy--linstrumenteur)
   - 3.3 [dataset_generator.py — Le generateur](#33-dataset_generatorpy--le-generateur)
   - 3.4 [sas_runner.py — L'executeur](#34-sas_runnerpy--lexecuteur)
   - 3.5 [coverage.py — L'analyseur de couverture](#35-coveragepy--lanalyseur-de-couverture)
   - 3.6 [cli.py — L'orchestrateur](#36-clipy--lorchestateur)
4. [Le pipeline GitLab CI](#4-le-pipeline-gitlab-ci)
5. [Exemple concret de bout en bout](#5-exemple-concret-de-bout-en-bout)
6. [Resume](#6-resume)

---

## 1. Vue d'ensemble

Le but du projet : tu as un **programme SAS** avec des branches
(`IF/ELSE`, `SELECT/WHEN`, `CASE/WHEN`). Tu veux **generer
automatiquement des datasets CSV** qui, quand SAS les traite, passent
dans **le maximum de branches possibles**.

C'est de la couverture de code, mais pour SAS, sans outil proprietaire.

Le principe general :

```
  Programme SAS          Parseur             Instrumenteur
  +-----------+       +--------------+      +------------------+
  | IF age>65 |------>| Detecte les  |----->| Injecte des PUT  |
  | THEN ...  |       | branches     |      | dans chaque      |
  | ELSE ...  |       | + variables  |      | branche          |
  +-----------+       +--------------+      +--------+---------+
                                                     |
                                                     v
  Datasets CSV        SAS batch             Code instrumente
  +-----------+       +--------------+      +------------------+
  | age=20    |------>| Execute le   |<-----| IF age>65 THEN   |
  | age=66    |       | programme    |      |   PUT "COV:P=3"; |
  | age=50    |       | SAS          |      |   status="OUI";  |
  +-----------+       +--------------+      +------------------+
                            |
                            v
                     +--------------+      +------------------+
                     | Log SAS      |----->| Analyseur de     |
                     | COV:POINT=1  |      | couverture       |
                     | COV:POINT=3  |      | "3/5 = 60%"      |
                     | COV:POINT=5  |      +--------+---------+
                     +--------------+               |
                                                    v
                                           +------------------+
                                           | Mutateur         |
                                           | "Point 2 manque, |
                                           |  condition age>65|
                                           |  -> ajouter      |
                                           |  age=64"         |
                                           +------------------+
                                                    |
                                           Reboucle avec les
                                           nouveaux datasets...
```

---

## 2. Le cycle complet en 6 etapes

Voici ce qui se passe quand on lance `sas-datagen run programme.sas` :

```
Etape 1 : PARSER     — Lire le .sas, identifier les branches et variables
Etape 2 : INSTRUMENT — Injecter des marqueurs PUT dans chaque branche
Etape 3 : GENERER    — Creer des CSV avec des valeurs ciblees
Etape 4 : EXECUTER   — Lancer SAS en batch avec les CSV
Etape 5 : ANALYSER   — Lire le log SAS, compter les branches atteintes
Etape 6 : MUTER      — Si couverture < cible, creer de nouvelles lignes
                        et retourner a l'etape 4
```

La boucle s'arrete quand :
- Le `--target` est atteint (ex: 90%)
- Ou le `--max-iter` est epuise (ex: 5 iterations)

---

## 3. Module par module

### 3.1 `sas_parser.py` — Le parseur

**Fichier** : `src/sas_data_generator/sas_parser.py`

**Ce qu'il fait** : Lit un fichier `.sas` et identifie les structures de
code via des expressions regulieres (regex).

Prenons cet exemple SAS :

```sas
data classified;
    set customers;
    if age < 25 then risk = "HIGH";
    else if age >= 65 then risk = "ELDER";
    else risk = "NORMAL";
run;
```

Le parseur produit :

| # | Point ID | Type        | Description                    | Condition  |
|---|----------|-------------|--------------------------------|------------|
| 1 | `f:1`    | STEP_ENTRY  | DATA step execute              | —          |
| 2 | `f:2`    | IF_TRUE     | Branche age < 25 vraie         | age < 25   |
| 3 | `f:3`    | IF_FALSE    | Branche age < 25 fausse        | age < 25   |
| 4 | `f:4`    | IF_TRUE     | Branche age >= 65 vraie        | age >= 65  |
| 5 | `f:5`    | IF_FALSE    | Branche age >= 65 fausse (ELSE)| age >= 65  |

Il detecte aussi :
- **Variables** : `age` (numerique, trouvee dans une condition)
- **Dataset d'entree** : `customers` (vu dans le `SET`)
- **Dataset de sortie** : `classified` (vu dans le `DATA`)

**Comment ca marche en interne** :

1. Supprime les commentaires (`/* ... */` et `* ... ;`) tout en preservant
   les numeros de ligne
2. Cherche les blocs `DATA ... RUN;` avec une regex
3. Cherche les blocs `PROC SQL ... QUIT;` avec une regex
4. Dans chaque bloc, cherche les patterns :
   - `IF ... THEN` → cree un point IF_TRUE + un point IF_FALSE
   - `SELECT ... WHEN ... OTHERWISE ... END` → un point par WHEN + OTHERWISE
   - `SET ...` / `MERGE ...` → identifie les datasets d'entree
   - `INPUT ...` → identifie les variables et leurs types
5. Dans PROC SQL, cherche :
   - `WHERE condition` → point SQL_WHERE
   - `CASE WHEN ... THEN ... ELSE ... END` → points SQL_CASE_WHEN + SQL_CASE_ELSE
6. Extrait les noms de variables depuis les conditions
   (`age > 65` → variable `age`, type `numeric`)

**Ce qu'il ne fait PAS (limitations MVP)** :
- Ne resout pas les macros (`%IF`, `%DO`, `%INCLUDE`)
- Ne gere pas le code dans les chaines de caracteres ou commentaires imbriques
- Ne parse pas les arrays, les boucles DO iteratives, ni les PROC autres que SQL

---

### 3.2 `sas_instrumenter.py` — L'instrumenteur

**Fichier** : `src/sas_data_generator/sas_instrumenter.py`

**Ce qu'il fait** : Prend le code SAS original et **injecte des marqueurs**
dans chaque branche, sans modifier la logique du programme.

Le code original :

```sas
data classified;
    set customers;
    if age < 25 then risk = "HIGH";
    else risk = "NORMAL";
run;
```

Devient (simplifie) :

```sas
/*************************************************************/
/* PREAMBLE auto-genere — definitions des macros de tracking */
/*************************************************************/

%macro _cov_hit(point_id);
  %put COV:POINT=&point_id;
%mend _cov_hit;

data _cov_tracker;
  length point_id $50 hit_time 8;
  stop;
run;

/* ------- Code original avec marqueurs injectes ------- */

data classified;
  put "COV:POINT=f:1";                /* <-- INJECTE : step entry */
    set customers;
    if age < 25 then do;
    put "COV:POINT=f:2";              /* <-- INJECTE : IF true */
      risk = "HIGH";
    end;
    else do;
    put "COV:POINT=f:3";              /* <-- INJECTE : ELSE */
      risk = "NORMAL";
    end;
run;

/*************************************************************/
/* POSTAMBLE — export du tracker + marqueur de fin           */
/*************************************************************/

proc export data=_cov_tracker
  outfile="coverage.csv" dbms=csv replace;
run;

%put COV:COMPLETE;
```

**Principe** : Chaque `PUT "COV:POINT=<id>";` ecrit une ligne dans le
**log SAS**. Apres execution, on parse le log pour voir quels points
ont ete atteints.

**Pourquoi `PUT` ?**

- Ca marche partout dans un DATA step
- C'est robuste : meme si le code plante plus loin, les PUT deja
  executes sont dans le log
- Ca ne modifie pas les donnees de sortie
- C'est facile a parser (juste un grep sur le log)

**Le preamble ajoute** :

| Element            | Role                                            |
|--------------------|-------------------------------------------------|
| `%macro _cov_hit`  | Macro pour `%PUT` (utilise dans PROC SQL)       |
| `_cov_tracker`     | Dataset vide qui accumule les hits (secondaire) |
| `%macro _cov_record`| Macro pour ecrire dans `_cov_tracker`          |

**Le postamble ajoute** :

| Element            | Role                                            |
|--------------------|-------------------------------------------------|
| `PROC EXPORT`      | Exporte `_cov_tracker` en CSV (mecanisme secondaire)|
| `%PUT COV:COMPLETE`| Marqueur de fin : confirme que SAS a termine    |

**Pour PROC SQL** : `PUT` n'existe pas en SQL, donc on utilise
`%_cov_hit()` qui fait un `%PUT` (macro facility, fonctionne partout).

---

### 3.3 `dataset_generator.py` — Le generateur

**Fichier** : `src/sas_data_generator/dataset_generator.py`

**Ce qu'il fait** : Cree des fichiers CSV intelligents. Pas des donnees
aleatoires — des donnees **ciblees pour declencher les branches**.

**Phase SEED (generation initiale)** :

Pour la condition `age < 25`, il ne genere pas `age = 7843`.
Il analyse la condition et produit des **valeurs limites** :

```
Condition: age < 25      →  genere age = 24, 25, 26
Condition: age >= 65     →  genere age = 64, 65, 66
Condition: score >= 80   →  genere score = 79, 80, 81
Condition: status = "ACTIVE" → genere "ACTIVE", "SUSPENDED", ""
```

Le CSV produit ressemble a :

```csv
age,income,score,status
24,50000,79,ACTIVE
25,100001,80,SUSPENDED
66,30000,81,
0,0,800,ACTIVE
-1,999999,400,
65,29999,600,BLOCK
```

Il ajoute aussi des **edge cases** automatiquement :
- Valeurs numeriques : `0`, `-1`, `999999`, `-999999`, `0.5`
- Caracteres : `""` (vide), `" "` (espace), `"NULL"`, chaine longue
- Dates : `1960-01-01`, `2000-01-01`, `2025-12-31`
- Missing : des `NaN` (qui deviennent `.` en SAS = valeur manquante)

**Phase MUTATION (apres un run SAS)** :

Apres chaque execution SAS, l'analyseur de couverture dit :
"Le point `f:4` (IF_TRUE pour `age >= 65`) n'a pas ete atteint."

Le mutateur analyse la condition `age >= 65` et genere :
- Pour faire IF_TRUE : `age = 66` (satisfait `>= 65`)
- Pour faire IF_FALSE : `age = 64` (viole `>= 65`)

Il ajoute ces lignes au dataset existant et relance SAS.

**Logique de generation des valeurs ciblees** :

| Operateur | Pour satisfaire  | Pour violer     |
|-----------|------------------|-----------------|
| `> N`     | `N + 1`          | `N - 1`         |
| `>= N`   | `N`              | `N - 1`         |
| `< N`    | `N - 1`          | `N + 1`         |
| `<= N`   | `N`              | `N + 1`         |
| `= N`    | `N`              | `N + 1`         |
| `ne N`   | `N + 1`          | `N`             |

Pour les chaines : si la condition est `status = "ACTIVE"`, on genere
`"ACTIVE"` (satisfait) et `"ZZZZ_NOMATCH"` (viole).

Pour OTHERWISE/ELSE final : on genere des valeurs extremes qui ne
matchent aucun WHEN precedent.

---

### 3.4 `sas_runner.py` — L'executeur

**Fichier** : `src/sas_data_generator/sas_runner.py`

**Ce qu'il fait** : Lance SAS en mode batch (headless) et recupere le log.

**Commande executee** :

```bash
sas -batch -noterminal -nologo \
    -log /tmp/workdir/_sas_datagen_run.log \
    -print /tmp/workdir/_sas_datagen_run.lst \
    -work /tmp/workdir/ \
    /tmp/workdir/_sas_datagen_run.sas
```

| Option SAS       | Signification                                    |
|------------------|--------------------------------------------------|
| `-batch`         | Mode batch (pas d'interface graphique)           |
| `-noterminal`    | Pas de sortie terminal interactive               |
| `-nologo`        | Pas de banniere SAS au demarrage                 |
| `-log`           | Chemin du fichier log                            |
| `-print`         | Chemin du fichier listing (sortie PROC PRINT etc)|
| `-work`          | Repertoire WORK temporaire                       |

**Ce qu'il retourne** :

| Champ              | Description                                  |
|--------------------|----------------------------------------------|
| `return_code`      | 0 = OK, autre = erreur                       |
| `log_text`         | Contenu complet du log SAS                   |
| `sas_errors`       | Liste des lignes commencant par `ERROR`      |
| `sas_warnings`     | Liste des lignes commencant par `WARNING`    |
| `duration_seconds` | Duree d'execution en secondes                |
| `work_dir`         | Chemin du repertoire de travail              |

**Avant d'executer, il injecte dans le code SAS** :

1. Les `libname` (si `--libnames` fourni) :
   ```sas
   libname mylib "/data/shared/mylib";
   ```
2. Les variables macro (si `--macros` fourni) :
   ```sas
   %let ENV = TEST;
   %let SEUIL = 65;
   ```
3. Le chargement des CSV generes :
   ```sas
   proc import datafile="/tmp/iter_0/customers.csv"
     out=customers dbms=csv replace;
     getnames=yes;
   run;
   ```

**Detection de l'executable SAS** (dans cet ordre) :

1. Option CLI `--sas /chemin/vers/sas`
2. Variable d'environnement `SAS_EXECUTABLE`
3. Commande `sas` sur le PATH systeme
4. Chemins standards :
   - `/usr/local/SASHome/SASFoundation/9.4/sas`
   - `/opt/sas/sas`
   - `/usr/local/bin/sas`

**Mode dry-run** (`--dry-run`) : Ecrit le fichier `.sas` complet
sur disque mais ne lance pas SAS. Utile pour :
- Tester le pipeline sans installation SAS
- Inspecter le code instrumente genere
- Valider la structure des CSV

---

### 3.5 `coverage.py` — L'analyseur de couverture

**Fichier** : `src/sas_data_generator/coverage.py`

**Ce qu'il fait** : Lit le log SAS, cherche les marqueurs
`COV:POINT=<id>`, et calcule le pourcentage de couverture.

**Exemple de log SAS apres execution** :

```
NOTE: The data set WORK.CLASSIFIED has 20 observations
COV:POINT=f:1
COV:POINT=f:2
COV:POINT=f:3
NOTE: PROCEDURE SQL used (Total process time):
COV:POINT=f:6
COV:COMPLETE
```

**L'analyseur fait** :

```
Attendus : f:1, f:2, f:3, f:4, f:5, f:6
Trouves  : f:1, f:2, f:3, f:6
Manques  : f:4 (IF_TRUE age>=65), f:5 (IF_FALSE age>=65)
Couverture : 4/6 = 66.7%
```

**Fusion de plusieurs runs** :

Si le run 1 touche `f:1, f:2, f:3` et le run 2 touche `f:1, f:4, f:5`,
la couverture cumulee est `f:1, f:2, f:3, f:4, f:5` = 5/6 = 83.3%.

Un point est "couvert" des qu'**au moins un run** l'a atteint.

**Formats de rapport** :

Le rapport JSON (`*_coverage_report.json`) :

```json
{
  "total_points": 6,
  "hit_points": 4,
  "coverage_pct": 66.67,
  "is_complete": true,
  "hit_point_ids": ["f:1", "f:2", "f:3", "f:6"],
  "missed_point_ids": ["f:4", "f:5"],
  "missed_details": [
    {
      "point_id": "f:4",
      "type": "IF_TRUE",
      "line": 5,
      "description": "IF true: age >= 65",
      "condition": "age >= 65"
    },
    {
      "point_id": "f:5",
      "type": "IF_FALSE",
      "line": 5,
      "description": "IF false/ELSE: age >= 65",
      "condition": "age >= 65"
    }
  ]
}
```

Le rapport texte (`*_coverage_report.txt`) :

```
Coverage: 4/6 (66.7%)
  Hit:    ['f:1', 'f:2', 'f:3', 'f:6']
  Missed: ['f:4', 'f:5']

Missed Points Detail:
  [f:4] IF_TRUE line 5: IF true: age >= 65
    Condition: age >= 65
  [f:5] IF_FALSE line 5: IF false/ELSE: age >= 65
    Condition: age >= 65
```

**Champs du rapport JSON** :

| Champ              | Description                                         |
|--------------------|-----------------------------------------------------|
| `total_points`     | Nombre total de points de couverture instrumentes   |
| `hit_points`       | Nombre de points atteints (au moins une fois)       |
| `coverage_pct`     | Pourcentage de couverture                           |
| `is_complete`      | `true` si SAS a termine normalement (COV:COMPLETE)  |
| `hit_point_ids`    | Liste des IDs des points atteints                   |
| `missed_point_ids` | Liste des IDs des points manques                    |
| `missed_details`   | Detail de chaque point manque (type, ligne, condition)|

---

### 3.6 `cli.py` — L'orchestrateur

**Fichier** : `src/sas_data_generator/cli.py`

**Ce qu'il fait** : La commande `run` enchaine tous les modules en boucle.

**Deroulement detaille d'un `sas-datagen run programme.sas --max-iter 3 --target 90`** :

```
ITERATION 1 :
  1. Parse programme.sas
     → 6 coverage points, 3 variables (age, income, score)
  2. Instrumente le code (injecte 6 PUT)
  3. Genere seed dataset : 20 lignes CSV
     - age = [24, 25, 26, 64, 65, 66, 0, -1, ...]
     - income = [49999, 50000, 50001, 100000, ...]
     - score = [79, 80, 81, 599, 600, 601, 799, 800, ...]
  4. Exporte CSV dans output/iter_0/customers.csv
  5. Construit le code SAS complet :
     - PROC IMPORT du CSV
     - Preamble (macros de couverture)
     - Code instrumente
     - Postamble (export + COV:COMPLETE)
  6. Execute SAS batch
  7. Parse le log → couverture 66.7% (4/6)
  8. 66.7% < 90% (cible) → on continue

  Mutation : points f:4 et f:5 manques
  - f:4 : IF_TRUE pour "age >= 65" → ajouter age=66
  - f:5 : IF_FALSE pour "age >= 65" → ajouter age=40
  → 2 nouvelles lignes ajoutees au dataset

ITERATION 2 :
  1. Dataset = 20 lignes originales + 2 mutations = 22 lignes
  2. Exporte CSV dans output/iter_1/customers.csv
  3. Execute SAS batch
  4. Parse le log → couverture 100% (6/6)
  5. 100% >= 90% (cible) → STOP, objectif atteint !

EXPORT FINAL :
  - output/final/customers.csv (22 lignes, le dataset optimal)
  - output/programme_coverage_report.json
  - output/programme_coverage_report.txt
  - output/programme_instrumented.sas (pour debug)
```

**Code de retour du processus** :

| Code | Signification                                          |
|------|--------------------------------------------------------|
| `0`  | Couverture cible atteinte                              |
| `1`  | Couverture cible NON atteinte apres toutes les iterations|

Cela permet en CI de faire echouer le pipeline si la couverture est
insuffisante.

---

## 4. Le pipeline GitLab CI

Le fichier `.gitlab-ci.yml` definit 5 stages sequentiels :

```
lint ──> test ──> generate ──> coverage ──> report
                                |     |
                           (avec SAS) (dry-run)
```

| Stage       | Job                 | SAS requis ? | Declenchement     | Description                                |
|-------------|---------------------|--------------|-------------------|--------------------------------------------|
| `lint`      | `lint`              | Non          | Automatique       | Verification qualite code Python (ruff)    |
| `test`      | `unit-tests`        | Non          | Automatique       | Tests unitaires pytest + couverture Python |
| `generate`  | `generate-datasets` | Non          | Si `*.sas` existe | Genere les datasets CSV                    |
| `coverage`  | `sas-coverage`      | **Oui**      | **Manuel**        | Execute SAS + mesure couverture            |
| `coverage`  | `sas-coverage-dry`  | Non          | Si `*.sas` existe | Dry-run (valide le pipeline sans SAS)      |
| `report`    | `coverage-report`   | Non          | Apres coverage    | Affiche les rapports dans le log CI        |

**Important** : Le job `sas-coverage` est en declenchement **manuel**
car il necessite un runner avec SAS installe. Cliquer sur le bouton
"Play" dans l'interface GitLab pour le lancer.

**Artifacts produits et telechargeables depuis GitLab** :

| Artifact                  | Provenance     | Contenu                           |
|---------------------------|----------------|-----------------------------------|
| `report.xml`              | unit-tests     | Rapport JUnit (tests Python)      |
| `coverage.xml`            | unit-tests     | Rapport Cobertura (Python)        |
| `htmlcov/`                | unit-tests     | Rapport HTML couverture Python    |
| `output/datasets/*.csv`   | generate       | Datasets CSV generes              |
| `output/coverage/*.json`  | sas-coverage   | Rapports couverture SAS           |
| `output/coverage/*.txt`   | sas-coverage   | Rapports couverture SAS (texte)   |
| `output/coverage/*.sas`   | sas-coverage   | Code instrumente                  |
| `output/coverage/*.log`   | sas-coverage   | Logs SAS                          |

---

## 5. Exemple concret de bout en bout

Voici un exemple complet avec le programme `examples/sample_program.sas`
qui contient :
- 1 DATA step avec 5 branches IF/ELSE + 1 SELECT/WHEN/OTHERWISE
- 1 PROC SQL avec WHERE + 2 CASE/WHEN/ELSE

**Etape 1 : Analyser**

```bash
$ sas-datagen analyze examples/sample_program.sas

File: examples/sample_program.sas
  Blocks: 2
  Coverage points: 18+
  Variables: 5

Coverage Points:
  sample_program:1   STEP_ENTRY        L17   DATA step entry: classified
  sample_program:2   IF_TRUE           L22   IF true: age < 25
  sample_program:3   IF_FALSE          L22   IF false: age < 25
  sample_program:4   IF_TRUE           L26   IF true: age >= 25 and age < 45
  sample_program:5   IF_FALSE          L26   IF false: age >= 25 and age < 45
  ...
  sample_program:X   SELECT_WHEN       L48   WHEN: score >= 800
  sample_program:X   SELECT_WHEN       L49   WHEN: score >= 600
  sample_program:X   SELECT_WHEN       L50   WHEN: score >= 400
  sample_program:X   SELECT_OTHERWISE  L51   OTHERWISE
  ...
  sample_program:X   SQL_CASE_WHEN     L70   CASE WHEN: mean(score) >= 700
  sample_program:X   SQL_CASE_ELSE     L72   CASE ELSE branch

Detected Variables:
  age      numeric     condition   L22
  income   numeric     condition   L38
  score    numeric     condition   L48
  status   character   condition   L54
```

**Etape 2 : Generer les datasets**

```bash
$ sas-datagen generate examples/sample_program.sas -o output/ -n 30

Generated: customers -> ['output/customers.csv']
  Seed dataset with 30 rows, 4 columns
  Variables: ['age', 'income', 'score', 'status']
  Conditions analyzed: 12
```

Le CSV `output/customers.csv` contient 30 lignes avec des valeurs
calculees autour des seuils : 24/25/26 (pour age<25), 64/65/66
(pour age>=65), 79/80/81 (pour score>=80), etc.

**Etape 3 : Lancer la boucle complete**

```bash
$ sas-datagen run examples/sample_program.sas \
    --output output/coverage \
    --rows 30 --max-iter 5 --target 90 \
    --verbose

=== Processing: examples/sample_program.sas ===
  Parsed: 2 blocks, 18 coverage points
  Instrumented code: output/coverage/sample_program_instrumented.sas

  --- Iteration 1/5 ---
  Coverage: 12/18 (66.7%)

  --- Iteration 2/5 ---
  Coverage: 16/18 (88.9%)

  --- Iteration 3/5 ---
  Coverage: 17/18 (94.4%)
  Target coverage reached!

  Final coverage: 94.4%
  Report: output/coverage/sample_program_coverage_report.json

=== Overall Coverage: 94.4% ===
  Missed points (1):
    [sample_program:16] SQL_CASE_ELSE line 74: CASE ELSE branch
```

---

## 6. Resume

Le projet resout ce probleme :

> "J'ai du code SAS, je veux des donnees de test qui passent dans
> toutes les branches, automatiquement, dans ma CI."

Il le fait **sans outil SAS proprietaire**, avec :

| Composant     | Role                                    | Technique utilisee |
|---------------|-----------------------------------------|--------------------|
| Parseur       | Comprendre le code SAS                  | Expressions regulieres (regex) |
| Instrumenteur | Injecter des marqueurs dans le code     | Statements `PUT` dans le log SAS |
| Generateur    | Creer des donnees ciblees               | Analyse de conditions + valeurs limites |
| Executeur     | Lancer SAS en batch                     | Commande `sas -batch` |
| Analyseur     | Mesurer la couverture                   | Grep des marqueurs `COV:POINT=` dans le log |
| Orchestrateur | Boucler jusqu'a la couverture cible     | Mutation iterative des datasets |
