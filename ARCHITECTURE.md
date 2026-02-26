# SAS Data Generator — Architecture

## Vue d'ensemble

Outil Python qui **genere des datasets de test** concus pour maximiser la couverture
d'execution des programmes SAS. Il fonctionne en :

1. **Parsant** le code SAS pour identifier les branches, conditions et variables
2. **Instrumentant** le code SAS avec des marqueurs de couverture
3. **Generant** des datasets de test avec des valeurs ciblees
4. **Executant** le SAS instrumente en mode batch
5. **Analysant** la couverture et **mutant** les datasets pour combler les manques

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│ Fichiers SAS│────>│  sas_parser  │────>│Points couverture│
│  (.sas)     │     │  (regex)     │     │ + Variables      │
└─────────────┘     └──────────────┘     └───────┬─────────┘
                                                  │
                    ┌──────────────┐               │
                    │ instrumenter │<──────────────┘
                    │ (injecte PUT)│      ┌─────────────────┐
                    └──────┬───────┘      │dataset_generator│
                           │              │ (seed+mutation)  │
                           v              └───────┬─────────┘
                    ┌──────────────┐               │
                    │  sas_runner  │<──────────────┘
                    │  (batch sas) │     (datasets CSV)
                    └──────┬───────┘
                           │
                           v
                    ┌──────────────┐     ┌─────────────────┐
                    │  Log SAS     │────>│   coverage.py   │
                    │  (COV:POINT) │     │ (parse+stats)   │
                    └──────────────┘     └───────┬─────────┘
                                                  │
                                          ┌───────v─────────┐
                                          │Rapport couverture│
                                          │ (JSON/texte)     │
                                          └─────────────────┘
```

## Strategie de couverture

### Points de couverture

Chaque emplacement instrumentable recoit un identifiant unique : `<nom_fichier>:<compteur>`.

| Type               | Construction SAS             | Comment instrumente                         |
|--------------------|------------------------------|---------------------------------------------|
| STEP_ENTRY         | `DATA ...;`                  | PUT apres l'instruction DATA                |
| IF_TRUE            | `IF condition THEN`          | PUT dans le bloc THEN                       |
| IF_FALSE           | `ELSE` (ou ELSE absent)      | PUT dans le bloc ELSE / ajout ELSE+PUT      |
| SELECT_WHEN        | `WHEN (condition)`           | PUT dans le bloc WHEN                       |
| SELECT_OTHERWISE   | `OTHERWISE`                  | PUT dans le bloc OTHERWISE                  |
| SQL_WHERE          | `WHERE condition`            | %PUT avant l'instruction SQL                |
| SQL_CASE_WHEN      | `CASE WHEN condition THEN`   | %PUT avant l'instruction SQL                |
| SQL_CASE_ELSE      | `CASE ... ELSE`              | %PUT avant l'instruction SQL                |

### Double mecanisme d'enregistrement

1. **Primaire — Marqueurs dans le log** : `PUT "COV:POINT=<id>";` ecrit dans le log SAS.
   Parse par `coverage.py` apres execution.
2. **Secondaire — Dataset de couverture** : le dataset `_cov_tracker` accumule les hits.
   Exporte en CSV dans le postamble.

### Pourquoi des PUT ?

- Fonctionne partout (DATA step, macro, certains contextes PROC)
- Aucune configuration de librairie/dataset supplementaire requise
- Survit aux erreurs dans d'autres parties du programme
- Facile a extraire des fichiers log en CI (grep)

## Reference des modules

### `sas_parser.py`

Parseur base sur des expressions regulieres. Identifie les DATA steps, PROC SQL,
IF/ELSE, SELECT/WHEN, SET/MERGE, statements INPUT, et extrait les references
de variables depuis les conditions.

### `sas_instrumenter.py`

Prend les resultats du parseur et injecte des PUT a chaque point de couverture.
Encapsule le code original avec un preambule (definitions de macros, init du tracker)
et un postamble (export CSV, marqueur de fin).

### `dataset_generator.py`

**Phase seed** : Extrait les variables et conditions des resultats du parseur.
Genere des valeurs autour des seuils des conditions (test aux limites).

**Phase mutation** : Analyse les points de couverture manques, genere des lignes
ciblees qui devraient declencher les branches non couvertes.

### `sas_runner.py`

Trouve l'executable SAS, ecrit le code instrumente dans un fichier temporaire,
execute `sas -batch -noterminal`, recupere le log.

### `coverage.py`

Parse les marqueurs `COV:POINT=<id>` depuis le log SAS (ou le CSV). Calcule
les hits/manques/pourcentage. Supporte la fusion de plusieurs executions.

### `include_resolver.py`

Resout les directives `%INCLUDE`/`%INC` recursivement. Gere les chemins
entre guillemets simples/doubles, l'expansion des variables macro dans les chemins,
la detection des inclusions circulaires (profondeur max 20). Produit un code
complet assemble comme s'il s'agissait d'un seul fichier.

### `cli.py`

CLI base sur Typer avec les commandes : `analyze`, `instrument`, `generate`, `run`.
Supporte les modes `--project-dir`, `--entry`, `--include-path` pour les projets
multi-fichiers.

## Flux de donnees (boucle complete)

```
pour iteration dans 1..max_iterations :
    1. Exporter les datasets en CSV
    2. Construire le code SAS : chargement_donnees + programme_instrumente
    3. Executer SAS en batch
    4. Parser la couverture depuis le log
    5. Si couverture >= cible : arreter
    6. Analyser les points manques → generer des lignes de mutation ciblees
    7. Ajouter les lignes de mutation aux datasets
```

## Limitations (MVP)

| Limitation                          | Impact                            | Correction prevue (V1)                |
|-------------------------------------|-----------------------------------|---------------------------------------|
| Pas de resolution de macros         | %IF/%THEN non instrumente         | Pre-processeur de macros              |
| Parseur regex                       | Peut mal parser certains cas      | Grammaire tree-sitter ou ANTLR       |
| Chaines dans commentaires/guillemets| Faux positifs possibles           | Tokeniseur complet                    |
| PROC SQL CASE/WHEN                  | Couverture au niveau log seulement| Analyse post-execution des sorties    |
| Blocs DO imbriques                  | Suivi de profondeur approximatif  | Tracker de blocs base sur une pile    |
| Formats/informats                   | Detection basique uniquement      | Catalogue complet des formats SAS     |
| Arrays                              | Non parses                        | Expansion des references d'arrays     |
| Statements SET multiples            | Detectes mais non sequences       | Analyse du flux de controle           |

## Feuille de route

### MVP (actuel)
- [x] Parseur regex pour DATA + PROC SQL
- [x] Instrumentation de couverture basee sur PUT
- [x] Generateur de datasets seed + mutation
- [x] Executeur SAS batch avec parsing du log
- [x] CLI avec commandes analyze/generate/run
- [x] Pipeline GitLab CI
- [x] Tests unitaires
- [x] Resolution des %INCLUDE (projets multi-fichiers)
- [x] Pipeline central CI/CD (sans modifier les repos SAS existants)

### V1 (prochaine)
- [ ] Detection basique des limites %MACRO/%MEND
- [ ] Export SAS7BDAT via pyreadstat
- [ ] Rapport HTML de couverture avec source SAS annotee
- [ ] Fichier de configuration YAML pour les parametres de projet
- [ ] Execution SAS parallele pour plusieurs variantes de test

### V2 (futur)
- [ ] Tokeniseur SAS complet (gestion correcte chaines/commentaires)
- [ ] Points de couverture pour PROC FREQ/MEANS/REG
- [ ] Graphe de flux de controle des DATA steps
- [ ] Generation de donnees par contraintes (solveur SMT)
- [ ] Integration avec SAS Viya / SAS Studio APIs
- [ ] Badge de couverture pour GitLab
