# Guide complet : Générer des datasets de test pour une migration SAS → Python

# À partir de l'ordonnanceur du projet

---

# PARTIE I — COMPRENDRE L'APPROCHE

---

## À qui s'adresse ce guide ?

Ce guide est destiné aux **actuaires**, **développeurs SAS** et **équipes de
migration** qui doivent générer des jeux de données de test couvrant le maximum
de code SAS, dans le cadre d'une migration vers Python.

Vous n'avez pas besoin d'être expert Python ou en testing pour suivre ce guide.
Chaque étape est expliquée, et les prompts sont prêts à être copiés-collés
dans **Claude Code** (l'outil en ligne de commande d'Anthropic).

---

## Le problème qu'on résout

Quand on migre du SAS vers Python, la question critique est toujours la même :

> **« Comment prouver que le code Python fait exactement la même chose que le code SAS ? »**

La réponse passe par des **jeux de données de test** (appelés "DataFrames" en
Python/pandas) qui :

1. Activent **chaque branche** du code SAS (chaque IF, ELSE, WHERE, cas particulier)
2. Capturent les **résultats produits par le SAS original** comme référence
3. Sont rejoués sur le **code Python migré** pour vérifier que les résultats sont identiques
4. Mesurent une **couverture de code réelle**, pas simplement déclarative

---

## Le principe en une phrase

> On lit le fichier d'ordonnancement du projet (`run_sas_param.json`),
> on en déduit les workflows d'exécution, on découpe chaque workflow en blocs
> de complexité maîtrisée, puis on génère des DataFrames pandas de test
> qui couvrent toutes les branches de chaque bloc.

---

## Pourquoi partir de l'ordonnanceur ?

Un projet SAS n'est pas une collection de fichiers indépendants. C'est un
ensemble de **workflows** (chaînes de programmes exécutés dans un ordre précis)
où les sorties d'un programme sont les entrées du suivant.

Tester fichier par fichier n'a pas de sens parce que :

- Un programme isolé peut lire un dataset produit par le programme précédent.
  Sans les bonnes données en entrée, le test est vide ou incohérent.
- Les branches intéressantes apparaissent souvent à cause de l'**interaction**
  entre les programmes (ex : le programme 1 crée un flag, le programme 3
  fait un IF sur ce flag).
- L'ordonnanceur (`run_sas_param.json`) définit les vrais points d'entrée
  et les vrais enchaînements. C'est la source de vérité.

Le bon raisonnement :

```
run_sas_param.json
  → définit N workflows
    → chaque workflow est une chaîne : prog_A → prog_B → prog_C
      → on découpe la chaîne en BLOCS testables (10-25 branches chacun)
        → pour chaque bloc, on génère les DataFrames de test
```

---

## Vocabulaire pour les non-initiés

| Terme | Ce que ça veut dire |
|-------|---------------------|
| **Workflow** | Une chaîne de programmes SAS exécutés dans l'ordre, définie dans `run_sas_param.json`. |
| **Bloc de test** | Un sous-ensemble d'un workflow regroupant quelques macros/programmes liés. On teste bloc par bloc pour garder une qualité de données élevée. |
| **Point d'entrée** | Le premier programme d'un workflow. Ses datasets d'entrée sont les seuls qu'on doit fournir comme données de test. |
| **Dataset intermédiaire** | Un dataset créé par un programme du workflow et lu par le suivant. On ne le fournit PAS : il est produit par l'exécution du workflow. |
| **Dataset d'entrée externe** | Un dataset lu par le workflow mais produit par AUCUN programme du workflow (ex : tables de référence, données de production). C'est ce qu'on doit fournir comme données de test. |
| **Branche** | Un endroit dans le code SAS où le programme choisit un chemin selon les données (IF/ELSE, WHERE, SELECT/WHEN, %IF, etc.). |
| **Couverture de branches** | Le pourcentage de branches activées par nos données de test. Si on a 8 branches et que nos données passent dans 7, la couverture est de 87.5%. |
| **DataFrame** | L'équivalent Python d'un dataset SAS. Un tableau avec des colonnes typées. |
| **Fixture pytest** | Une fonction Python qui prépare un DataFrame de test. C'est l'équivalent d'un DATA step qui crée un jeu de test. |
| **Ground truth** | Les résultats réels produits par le SAS original. C'est la référence absolue pour vérifier que le Python fait pareil. |
| **Claude Code** | L'outil en ligne de commande d'Anthropic qui permet de piloter Claude directement dans un terminal, avec accès à votre système de fichiers local. |

---

## Comment lire ce guide

Chaque prompt est encadré entre deux lignes de `═` :

```
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT X
════════════════════════════════════════════════════════════

  (le texte à copier-coller dans Claude Code)

════════════════════════════════════════════════════════════
FIN DU PROMPT X
════════════════════════════════════════════════════════════
```

**Avant de copier-coller**, remplacez toujours les éléments entre crochets :

| Placeholder | Ce qu'il faut mettre | Exemple |
|-------------|----------------------|---------|
| `[CHEMIN_DU_PROJET]` | Chemin absolu vers votre projet SAS | `/home/moi/projet-sas` |
| `[SEUIL]` | Pourcentage de couverture cible | `80` pour 80%, `100` pour 100% |
| `[NOM_WORKFLOW]` | Nom du workflow (tiré de 00_workflows.md) | `workflow_01` |
| `[NOM_BLOC]` | Nom du bloc (tiré de 00_blocs_test.md) | `Bloc 2 - Vérif + vues` |
| `[NOM_MODULE_PYTHON]` | Nom du futur module Python cible | `calcul_provisions` |

---

## Vue d'ensemble du processus

```
PROMPT 0     ─ Découverte des workflows
               Lit run_sas_param.json → identifie les workflows

PROMPT 0-BIS ─ Schémas des sources dynamiques + découpage en blocs
               Résout les tables dont le schéma n'est pas visible
               dans le code, et découpe chaque workflow en blocs de
               10-25 branches testables indépendamment.

PROMPT 1     ─ Analyse + génération pour UN bloc
               Lit le code SAS du bloc, identifie chaque branche,
               et génère les DataFrames de test.
               (Répéter pour chaque bloc identifié au prompt 0-BIS.)

PROMPT 2     ─ Validation SAS (si accès SAS disponible)
               Crée les scripts pour exécuter le SAS original avec
               les données de test et capturer les vrais résultats.

PROMPT 3     ─ Tests pytest (quand le code Python est migré)
               Assemble les tests automatisés pour le code Python.

PROMPT 4     ─ Combler les trous (itératif)
               Relancé après mesure de couverture pour compléter.
```

**En résumé, ce que vous allez faire concrètement :**

```
1. Lancez PROMPT 0      → vous obtenez la liste des workflows
2. Lancez PROMPT 0-BIS  → vous obtenez les schémas + les blocs de test
3. Pour chaque bloc :
   Lancez PROMPT 1      → vous obtenez les DataFrames de test
4. (Optionnel) PROMPT 2 → validation par le SAS original
5. (Après migration) PROMPT 3 → tests pytest
6. (Si trous) PROMPT 4  → itération jusqu'au seuil
```

---

## Qu'est-ce qu'une « branche » ? (exemple concret)

En SAS, chaque fois que le code prend une décision, c'est une branche :

```sas
/* Ceci crée 2 branches : age >= 18 (VRAI) et age < 18 (FAUX) */
IF age >= 18 THEN statut = "MAJEUR";
ELSE statut = "MINEUR";

/* Ceci crée 3 branches : une par WHEN + le OTHERWISE */
SELECT (type_contrat);
  WHEN ("VIE")    DO; ... END;
  WHEN ("IARD")   DO; ... END;
  OTHERWISE        DO; ... END;
END;
```

Pour couvrir tout le code, il faut des données de test qui passent dans
**chaque** branche au moins une fois.

Pour couvrir les 5 branches ci-dessus, il suffit de 3 lignes de données :

| # | age | type_contrat | Branches couvertes |
|---|-----|--------------|-------------------|
| 1 | 25  | VIE          | age >= 18 VRAI, WHEN VIE |
| 2 | 15  | IARD         | age < 18 FAUX, WHEN IARD |
| 3 | 30  | PREVOYANCE   | age >= 18 VRAI, OTHERWISE |

C'est exactement **ça** que ce guide vous fait générer par Claude Code :
des lignes de données concrètes, avec les bonnes valeurs aux bons endroits,
pour chaque programme SAS de votre projet.

---

---

# PARTIE II — LES PROMPTS

---

---

# PROMPT 0 — Découverte des workflows

---

## Ce que fait ce prompt

C'est le **point d'entrée obligatoire**. Il lit le fichier d'ordonnancement
du projet (`ordonnanceur/run_sas_param.json`) et produit une cartographie :
quels workflows existent, quels programmes ils contiennent, dans quel ordre,
et quels sont les datasets d'entrée qu'il faudra fournir comme données de test.

## Ce que vous obtenez

Un fichier `00_workflows.md` qui vous dit :

- « Votre projet a **N workflows** »
- « Le workflow X exécute ces programmes dans cet ordre »
- « Pour le tester, vous devez fournir les datasets A, B et C en entrée »
- « Commencez par le workflow le plus simple »

---

### 📋 PROMPT 0

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 0
════════════════════════════════════════════════════════════

Tu es un expert SAS senior spécialisé en architecture de projets SAS
et en ordonnancement.

PROJET : [CHEMIN_DU_PROJET]

ÉTAPE 1 — Lis le fichier d'ordonnancement :
  [CHEMIN_DU_PROJET]/ordonnanceur/run_sas_param.json

Ce fichier JSON décrit les workflows d'exécution du projet SAS :
quels programmes sont exécutés, dans quel ordre, avec quels paramètres.

Lis-le attentivement et extrais CHAQUE workflow défini.

ÉTAPE 2 — Pour chaque workflow trouvé dans le JSON :

  a) Identifie la CHAÎNE D'EXÉCUTION : la liste ordonnée des programmes
     SAS qui s'exécutent dans ce workflow.

  b) Pour chaque programme de la chaîne, lis le fichier .sas correspondant
     et identifie :
     - Les datasets qu'il LIT (SET, MERGE, PROC SQL FROM, %include data, etc.)
     - Les datasets qu'il ÉCRIT (DATA ..., CREATE TABLE, PROC EXPORT, etc.)
     - Les macros qu'il appelle et les fichiers %include
     - Les macros appelées indirectement (via call execute, %do loops, etc.)

  c) Trace le FLUX DE DONNÉES à travers le workflow :
     - Quels datasets sont PRODUITS par un programme et LUS par le suivant ?
       → Ce sont des datasets INTERMÉDIAIRES (on ne les fournit pas en test)
     - Quels datasets sont LUS par un programme mais PRODUITS par AUCUN
       programme du workflow ?
       → Ce sont des datasets D'ENTRÉE EXTERNES (on doit les fournir en test)
     - Quels datasets sont le résultat final du workflow ?
       → Ce sont les SORTIES à vérifier

  d) Identifie les MACROS-VARIABLES et PARAMÈTRES du workflow :
     - Ceux définis dans le JSON d'ordonnancement
     - Ceux définis dans un autoexec.sas ou un fichier de config
     - Ceux passés par l'environnement système (%sysget)
     - Leurs valeurs par défaut et leurs valeurs possibles

ÉTAPE 3 — Produis le livrable ./test-plan/00_workflows.md :

Pour CHAQUE workflow, écris un bloc structuré comme ceci :

---

### Workflow : [NOM DU WORKFLOW]

**Source** : run_sas_param.json → [chemin dans le JSON]

**Chaîne d'exécution** :
```
[1] chargement.sas
 ↓  écrit → WORK.DONNEES_BRUTES
[2] nettoyage.sas
 ↓  lit ← WORK.DONNEES_BRUTES
 ↓  écrit → WORK.DONNEES_CLEAN
[3] calcul_provisions.sas
 ↓  lit ← WORK.DONNEES_CLEAN, LIB.TABLES_MORTALITE
 ↓  écrit → LIB.PROVISIONS
```

**Analyse par programme de la chaîne** :
Pour chaque programme, détaille :
- Ce qu'il lit, ce qu'il écrit
- Les macros appelées (directes ET indirectes)
- Les %include

**Datasets d'entrée externes** (à fournir en données de test) :
| Dataset | Utilisé par | Variables clés | Description probable |
|---------|-------------|----------------|---------------------|
| LIB.POLICES | chargement.sas | num_police, date_effet | Portefeuille |
| LIB.TABLES_MORTALITE | calcul.sas | age, sexe, qx | Tables actuarielles |

**Datasets intermédiaires** (produits par le workflow, pas à fournir) :
- WORK.DONNEES_BRUTES (chargement → nettoyage)
- WORK.DONNEES_CLEAN (nettoyage → calcul)

**Datasets de sortie** (à vérifier) :
- LIB.PROVISIONS
- /export/rapport.xlsx

**Paramètres / macro-variables** :
| Variable | Source | Impact |
|----------|--------|--------|
| &DATE_CALCUL | autoexec ou %sysget | Date de référence |
| &env | %sysget(env) | Sélection environnement DEV/REC/PROD |

**Fichiers %include de configuration** :
- autoexec.sas → inclut tel et tel fichier de config

**Complexité estimée** :
- Nombre de programmes dans la chaîne JSON : X
- Nombre de programmes/macros effectivement exécutés : Y
- Nombre de branches estimé : ~Z

---

ÉTAPE 4 — Produis un RÉSUMÉ FINAL à la fin du document :

**Tableau récapitulatif des workflows** :

| # | Workflow | Nb programmes | Nb entrées externes | Complexité | Ordre de test |
|---|----------|---------------|---------------------|------------|---------------|
| 1 | workflow_01 | 4 | 3 | Élevée | 2 |
| 2 | workflow_02 | 2 | 1 | Faible | 1 |

**Ordre de test recommandé** :
Commence par les workflows les plus simples (moins de programmes,
moins de branches) pour valider l'approche, puis passe aux plus complexes.

**Datasets d'entrée partagés** :
Si plusieurs workflows lisent le même dataset, signale-le.
On pourra créer un jeu de données de test unique, réutilisé partout.

Sauvegarde dans ./test-plan/00_workflows.md

════════════════════════════════════════════════════════════
FIN DU PROMPT 0
════════════════════════════════════════════════════════════
```

`── Fin du prompt 0 ──`

---

---

# PROMPT 0-BIS — Schémas des sources dynamiques + découpage en blocs

---

## Ce que fait ce prompt

Le prompt 0 a identifié les workflows, mais deux problèmes empêchent la
génération correcte de données de test :

1. **Certaines tables sont dynamiques** : leur nom et leur schéma sont
   déterminés à l'exécution par le contenu d'un fichier de configuration
   (ex : un mapping Excel). Sans connaître leurs colonnes et types exacts,
   Claude va inventer des données génériques et incohérentes.

2. **Un workflow complexe (30+ branches) est trop gros pour un seul prompt.**
   Claude perd en qualité au-delà de 20-25 branches. Il faut découper le
   workflow en blocs testables de taille maîtrisée.

## Ce que vous obtenez

Deux fichiers :

- `00_schemas_sources.md` — Le schéma exact de chaque table source dynamique
- `00_blocs_test.md` — Le workflow découpé en blocs de 10-25 branches, chacun
  avec ses entrées/sorties clairement définies

## Quand l'utiliser

**Toujours**, sauf si votre workflow est très simple (un seul programme,
moins de 20 branches, pas de tables dynamiques).

---

### 📋 PROMPT 0-BIS

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 0-BIS
════════════════════════════════════════════════════════════

Tu es un expert SAS senior. J'ai analysé les workflows de mon projet
(voir ./test-plan/00_workflows.md).

Avant de générer les données de test, j'ai besoin de résoudre deux problèmes :
les tables sources dynamiques et le découpage du workflow en blocs testables.

═══ PARTIE A : Résoudre les tables sources dynamiques ═══

Dans le résultat du prompt 0 (./test-plan/00_workflows.md), certains datasets
d'entrée ont un schéma inconnu ou dynamique : leur nom est construit à
l'exécution à partir d'un fichier de paramétrage (mapping Excel, table de
configuration, macro-variable, etc.).

Pour CHAQUE dataset d'entrée dont le schéma n'est pas directement visible :

1. Identifie le fichier de paramétrage qui détermine ces tables.
   Exemples courants :
   - Un fichier Excel de mapping (MAPPING_SINAPPS.xlsx, etc.)
   - Un dataset SAS de configuration (PARAM_TABLES.sas7bdat)
   - Des macro-variables qui construisent des noms de tables dynamiquement

2. Lis ce fichier de paramétrage (ou le code SAS qui l'importe) et extrais
   la LISTE COMPLÈTE des tables sources qui en découlent.

3. Pour CHAQUE table source identifiée, lis les macros qui la traitent et
   déduis le SCHÉMA COMPLET :
   - Colonnes lues par le code SAS
   - Type de chaque colonne (num/char) — déduis-le des opérations :
     * calcul arithmétique, SUM, MEAN → num
     * SUBSTR, COMPRESS, SCAN, UPCASE → char
     * format DATE9., DDMMYY10. → num (date SAS)
     * comparaison avec une chaîne entre guillemets → char
   - Format probable (DATE9., $50., BEST12., etc.)
   - Contraintes déduites (clé primaire, NOT NULL implicite, etc.)
   - Dans quels programmes/macros cette colonne est utilisée

4. Produis le fichier ./test-plan/00_schemas_sources.md :

   Pour chaque table source dynamique, un bloc comme :

   ### [NOM_TABLE_SOURCE] (exemple : SINAPPS.MISSION_DARVA)

   **Comment elle est déterminée** : via la colonne TABLE_A_RECUP du
   mapping MAPPING_SINAPPS.xlsx
   **Table temporaire associée** : ATNTMP.MISSION_DARVA
   **Table datamart finale** : ATNDTM.ATN_SUIVOMT_DARVA (contribue à)
   **Traitements appliqués** : %F0_310, %F0_320, RG01, RG03, RG08

   | Variable | Type SAS | Format | Utilisée dans | Nullable |
   |----------|----------|--------|---------------|----------|
   | prestations_darva_idx | num | BEST12. | %F0_310 (clé) | NON |
   | date_creation | num | DATE9. | %F0_333_RG03 | OUI |
   | statut_code | char(10) | $10. | %F0_333_RG08 | OUI |
   | montant_prestation | num | BEST12. | %F0_333_RG01 | OUI |

   IMPORTANT : si tu n'arrives pas à déduire le schéma complet d'une table
   parce que le code est trop dynamique (ex : CALL EXECUTE avec des noms
   de colonnes construits à la volée), indique-le clairement et liste les
   colonnes que tu as pu identifier avec certitude vs celles qui sont
   incertaines.

═══ PARTIE B : Découper chaque workflow en blocs testables ═══

Pour CHAQUE workflow identifié dans 00_workflows.md, découpe la chaîne
d'exécution en BLOCS DE TEST. Chaque bloc doit :
- Regrouper des programmes/macros qui forment une unité logique
- Avoir des entrées et sorties clairement définies
- Contenir entre **10 et 25 branches maximum**
- Être testable indépendamment des autres blocs

Critères de découpage (dans cet ordre de priorité) :
1. Découper aux frontières naturelles des datasets
   (là où un dataset est écrit puis relu)
2. Regrouper les macros qui travaillent sur le même dataset
3. Si un groupe a plus de 25 branches, sous-découper par
   famille fonctionnelle (ex : par type de règle de gestion)

Pour CHAQUE bloc, documente :

### Bloc [N] — [Nom descriptif]

**Programmes / macros** : [liste]
**Entrées** :
- [dataset] — source : externe / produit par Bloc N-1
**Sorties** :
- [dataset] — consommé par : Bloc N+1 / sortie finale
**Nb branches estimé** : ~X
**Pièges de migration SAS→Python identifiés** :
- [piège 1] dans [macro] à la ligne [X]
- [piège 2] ...

Produis le fichier ./test-plan/00_blocs_test.md avec cette structure,
terminé par un tableau récapitulatif :

| Bloc | Programmes/macros | Entrées | Sorties | Nb branches | Ordre |
|------|-------------------|---------|---------|-------------|-------|
| 1 | F0_200 | Excel × 2 | ATNREF.* × 3 | ~8 | 1er |
| 2 | F0_310, F0_320 | ATNREF + SINAPPS.* | ATNTMP.* | ~12 | 2e |
| 3 | F0_330..F0_339 | ATNTMP.* | ATNTMP.* enrichi | ~20 | 3e |
| 4 | F0_340..F0_342 | ATNTMP.* enrichi | ATNDTM.* | ~15 | 4e |

Si un bloc dépasse 25 branches, SOUS-DÉCOUPE-LE et explique pourquoi.

Sauvegarde dans :
- ./test-plan/00_schemas_sources.md
- ./test-plan/00_blocs_test.md

════════════════════════════════════════════════════════════
FIN DU PROMPT 0-BIS
════════════════════════════════════════════════════════════
```

`── Fin du prompt 0-bis ──`

---

### Comment utiliser le résultat du prompt 0-bis

Après ce prompt, vous avez deux fichiers qui débloquent tout :

- **00_schemas_sources.md** : Claude connaît maintenant les colonnes exactes de
  chaque table source. Il ne va plus inventer de données génériques.
- **00_blocs_test.md** : Le workflow est découpé en blocs de taille raisonnable
  avec un ordre d'exécution.

Vous allez maintenant lancer le **prompt 1 une fois par bloc**, dans l'ordre
indiqué par le tableau récapitulatif.

---

---

# PROMPT 1 — Analyse + génération des données de test pour UN bloc

---

## Ce que fait ce prompt

C'est le prompt principal. Il prend **un seul bloc** identifié au prompt 0-bis,
lit TOUS les fichiers SAS de ce bloc, identifie TOUTES les branches, et
génère les DataFrames de test.

## Ce que vous obtenez

Pour chaque bloc :
- Un fichier `[bloc]_test_data.py` contenant des fonctions Python qui
  retournent les DataFrames de test (entrées + résultats attendus)
- Un fichier `[bloc]_branches.md` documentant chaque branche et la
  couverture atteinte

## Combien de fois le lancer

**Une fois par bloc.** Si le prompt 0-bis a identifié 4 blocs, vous lancez
ce prompt 4 fois.

## Point crucial : enchaînement entre blocs

- **Bloc 1** : les entrées sont les datasets **externes** (fichiers Excel,
  tables de référence, données sources).
- **Bloc 2, 3, 4...** : les entrées sont les **sorties du bloc précédent**.
  On dit à Claude de réutiliser les résultats attendus du bloc N-1 comme
  entrées du bloc N.

---

### 📋 PROMPT 1 — Pour le premier bloc (entrées externes)

> Lancez cette version pour le PREMIER bloc de chaque workflow.
> Pour les blocs suivants, utilisez la variante "blocs suivants" plus bas.

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 1 (premier bloc)
════════════════════════════════════════════════════════════

Tu es un expert SAS et Python spécialisé en génération de données de test.

BLOC À ANALYSER : [NOM_BLOC] (voir ./test-plan/00_blocs_test.md)
SCHÉMAS DES SOURCES : ./test-plan/00_schemas_sources.md
COUVERTURE CIBLE : [SEUIL]%

Exécute les 4 sous-tâches suivantes DANS L'ORDRE, dans une seule réponse.

═══ SOUS-TÂCHE A : Lire et comprendre le code ═══

1. Lis ./test-plan/00_blocs_test.md pour retrouver le périmètre de ce bloc :
   quels programmes/macros, quelles entrées, quelles sorties.

2. Lis CHAQUE fichier SAS / macro de ce bloc.
   Lis aussi les macros appelées indirectement et les fichiers %include.

3. Pour chaque dataset d'entrée, retrouve son schéma dans
   ./test-plan/00_schemas_sources.md. Si le schéma n'y figure pas
   (dataset non dynamique), déduis-le du code SAS.

═══ SOUS-TÂCHE B : Lister chaque branche ═══

Parcours le code ligne par ligne et liste CHAQUE branche.

FORMAT OBLIGATOIRE pour chaque branche :

   BRANCHE : BR_[programme/macro]_[numéro]
   FICHIER : [nom du fichier .sas]
   LIGNE : [numéro de ligne]
   CODE SAS : [la ligne de code exacte]
   CONDITION VRAI : [condition]  →  exemple de valeur
   CONDITION FAUX : [condition]  →  exemple de valeur
   IMPACT : [ce qui change dans les données si on passe par VRAI vs FAUX]

N'oublie AUCUNE branche, y compris :
- Les WHERE implicites dans les SET / MERGE
- Les conditions IN= des MERGE (correspondance ou non)
- Les FIRST. / LAST. (première et dernière obs d'un groupe BY)
- Les cas de missing qui modifient le résultat des IF
  (RAPPEL : en SAS, . < 0 est VRAI, donc IF montant > 0 est FAUX
  quand montant est missing — c'est différent de Python)
- Les %IF / %THEN / %ELSE dans les macros
- Les conditions dans les CALL EXECUTE (exécution dynamique)
- Les CASE/WHEN dans les PROC SQL

PIÈGES DE MIGRATION SAS → PYTHON à repérer systématiquement :

- RETAIN / accumulation entre observations
- FIRST. / LAST. (traitement par groupe BY)
- MERGE avec IN= (jointures partielles)
- Missing numérique (SAS : . < 0 est VRAI ; Python : NaN < 0 est FAUX)
- Missing chaîne (SAS padde de blancs, Python non)
- Dates SAS (jours depuis 01/01/1960)
- Tri implicite (BY dans MERGE, FIRST./LAST.)
- ROUND SAS (away from zero) vs Python (banker's rounding)
- MERGE avec doublons (appariement séquentiel SAS vs cartésien Python)
- LAG / DIF (décalage global en SAS, pas par groupe)

Pour chaque occurrence, note :
   PIÈGE MIGRATION : [type] — [fichier:ligne] — [valeur de test nécessaire]

═══ SOUS-TÂCHE C : Concevoir les lignes de données ═══

Conçois les DataFrames pour les datasets D'ENTRÉE EXTERNES de ce bloc.

RAISONNEMENT À SUIVRE :

Pour chaque branche identifiée en B, détermine quelle valeur dans quel
dataset d'entrée l'active. Puis construis un tableau minimal où chaque
ligne est conçue pour activer un ensemble spécifique de branches.

RÈGLES OBLIGATOIRES (à respecter impérativement pour éviter les données
vides ou incohérentes) :

□ JAMAIS de dataset vide.
  Chaque dataset d'entrée a AU MINIMUM autant de lignes qu'il y a de
  combinaisons de branches qui dépendent de ses valeurs.

□ JAMAIS de valeurs génériques ou "placeholder".
  Chaque valeur est choisie SPÉCIFIQUEMENT pour activer une branche précise.
  MAUVAIS : client_id = 1, 2, 3, 4 (séquentiel sans raison)
  BON : age = 25 (pour activer BR_001 VRAI), age = 15 (pour BR_001 FAUX)

□ COHÉRENCE entre datasets liés par des jointures.
  Si le code fait MERGE A B BY clé :
  - Au moins 2 lignes de A avec correspondance dans B
  - Au moins 1 ligne de A SANS correspondance dans B
  - Au moins 1 ligne de B SANS correspondance dans A

□ MISSINGS testés.
  Au moins une ligne avec missing sur chaque variable qui apparaît dans
  une condition IF/WHERE/CASE. UN seul missing par ligne pour isoler l'effet.

□ VALEURS LIMITES.
  Pour chaque condition numérique (IF x > 100), inclure :
  x = 99 (juste en dessous), x = 100 (pile dessus), x = 101 (juste au-dessus).

□ FIRST. / LAST.
  Si présent : inclure des groupes de taille 1, 2, et 3+.

□ TRI respecté.
  Les données doivent être dans l'ordre trié si le code suppose un tri
  (PROC SORT, BY dans MERGE).

□ DOUBLONS sur clés de jointure.
  Si MERGE BY : au moins un cas avec doublons sur la clé dans UN des
  datasets pour vérifier le comportement SAS vs Python.

□ CHAQUE LIGNE EST DOCUMENTÉE.
  Pour chaque ligne du tableau, indiquer quelles branches elle active.

Présente les données en TABLEAUX LISIBLES :

  DATASET D'ENTRÉE : LIB.POLICES (7 observations)
  Utilisé par : chargement.sas
  Trié par : num_police

  | # | num_police | montant | type_contrat | Branches activées |
  |---|------------|---------|--------------|-------------------|
  | 1 | POL-001    | 150000  | VIE          | BR_calc_001V, BR_calc_003V |
  | 2 | POL-002    | 500     | IARD         | BR_calc_001V, BR_calc_003F |
  | 3 | POL-003    | 0       | VIE          | BR_calc_004V |
  | 4 | POL-004    | -200    | PREVOYANCE   | BR_calc_005V, BR_calc_006V |
  | 5 | POL-005    | NaN     | VIE          | BR_calc_005V (missing→ELSE) |

═══ SOUS-TÂCHE D : Générer le code Python ═══

Produis DEUX fichiers :

FICHIER 1 : ./test-plan/data/[NOM_BLOC]_test_data.py

   Ce fichier contient des fonctions qui retournent les DataFrames de test.

   Structure obligatoire :

   ```python
   """
   Données de test pour le bloc : [NOM_BLOC]
   Programmes couverts : [liste]
   Couverture de branches visée : [SEUIL]%
   Généré par Claude Code.
   """
   import pandas as pd
   import numpy as np


   # ════════════════════════════════════════════════════════
   # DATASETS D'ENTRÉE EXTERNES
   # Ce sont les seules données à injecter pour ce bloc.
   # ════════════════════════════════════════════════════════

   def get_input_[nom_dataset]() -> pd.DataFrame:
       """
       Dataset [NOM] — [N] observations.
       Utilisé par : [programme/macro]
       """
       df = pd.DataFrame({
           "colonne_1": [
               "valeur_a",    # Ligne 1 : BR_001 VRAI (explication)
               "valeur_b",    # Ligne 2 : BR_001 FAUX (explication)
               "valeur_c",    # Ligne 3 : BR_002 VRAI (explication)
           ],
           "colonne_2": [
               1500.0,        # > 0 → BR_003 VRAI
               0.0,           # = 0 → BR_004 VRAI
               np.nan,        # missing → BR_005 (piège SAS : . < 0)
           ],
           # ... toutes les colonnes nécessaires
       })
       # Typage strict aligné sur le schéma SAS
       df["colonne_1"] = df["colonne_1"].astype("string")
       # Les colonnes numériques restent en float64 (comme SAS)
       return df


   # ════════════════════════════════════════════════════════
   # RÉSULTATS ATTENDUS EN SORTIE DU BLOC
   # SOURCE : estimés par analyse du code SAS.
   # À remplacer par les vrais résultats SAS quand disponibles
   # (voir prompt 2).
   # ════════════════════════════════════════════════════════

   def get_expected_[nom_dataset_sortie]() -> pd.DataFrame:
       """
       Dataset de sortie [NOM] — résultat attendu.
       Produit par : [programme/macro]
       """
       df = pd.DataFrame({
           # ... résultats tracés à partir du code SAS
       })
       return df


   # ════════════════════════════════════════════════════════
   # MACRO-VARIABLES / PARAMÈTRES DU WORKFLOW
   # ════════════════════════════════════════════════════════

   PARAMS = {
       "DATE_CALCUL": "31/12/2024",
       "env": "DEV",
       # ... toutes les macro-variables nécessaires
   }
   ```

   RÈGLES DE QUALITÉ DU CODE GÉNÉRÉ :
   - CHAQUE valeur a un COMMENTAIRE indiquant la branche qu'elle active
   - Les types sont explicitement définis (jamais de type "object" par défaut)
   - float64 pour les numériques (comme SAS qui est tout en float 8 bytes)
   - pd.StringDtype() ("string") pour les chaînes, PAS object
   - datetime64[ns] pour les dates
   - Les NaN/NaT sont utilisés correctement selon le type
   - Le DataFrame n'est JAMAIS vide
   - Pas de colonnes inutiles (uniquement celles utilisées par le code SAS)

FICHIER 2 : ./test-plan/data/[NOM_BLOC]_branches.md

   Documentation résumant :
   - La liste de toutes les branches avec leur ID
   - Le tableau des données et quelles branches chaque ligne couvre
   - Le taux de couverture atteint
   - Les branches non couvertes (s'il y en a) et pourquoi
   - Les pièges de migration SAS → Python identifiés dans ce bloc

═══ VÉRIFICATION FINALE ═══

Avant de terminer, RELIS le code SAS du bloc et vérifie :

□ Chaque branche identifiée en B est activée par au moins une ligne en C
□ Aucun dataset n'est vide
□ Les clés de jointure sont cohérentes entre datasets liés
□ Les missings sont testés sur chaque variable conditionnelle
□ Les valeurs limites sont testées (pile sur le seuil, ±1)
□ Le code Python en D correspond exactement aux données du tableau en C
□ Les commentaires de chaque valeur sont présents et corrects
□ Les types sont explicitement définis dans le code Python

════════════════════════════════════════════════════════════
FIN DU PROMPT 1 (premier bloc)
════════════════════════════════════════════════════════════
```

`── Fin du prompt 1 (premier bloc) ──`

---

### 📋 PROMPT 1 — Pour les blocs suivants (entrées = sorties du bloc précédent)

> Lancez cette version pour les blocs 2, 3, 4, etc. d'un même workflow.
> La seule différence : les entrées viennent du bloc précédent, pas de l'extérieur.

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 1 (blocs suivants)
════════════════════════════════════════════════════════════

Tu es un expert SAS et Python spécialisé en génération de données de test.

BLOC À ANALYSER : [NOM_BLOC] (voir ./test-plan/00_blocs_test.md)
SCHÉMAS DES SOURCES : ./test-plan/00_schemas_sources.md
COUVERTURE CIBLE : [SEUIL]%

CONTEXTE D'ENCHAÎNEMENT :
Les entrées de ce bloc sont les SORTIES du bloc précédent.
Utilise les résultats attendus du bloc précédent comme données d'entrée :
- Lis ./test-plan/data/[BLOC_PRECEDENT]_test_data.py
- Les fonctions get_expected_*() de ce fichier fournissent les DataFrames
  d'entrée de CE bloc.

Si des données d'entrée supplémentaires sont nécessaires pour ce bloc
(ex : des tables de référence qui ne viennent pas du bloc précédent
mais sont des entrées externes partagées), réutilise celles déjà
générées dans les fichiers précédents sans les recréer de zéro.
Si les données existantes ne suffisent pas (il manque des lignes pour
couvrir de nouvelles branches), AJOUTE des lignes aux DataFrames existants
du bloc précédent et signale-le clairement :
  "AJOUT NÉCESSAIRE : ajouter dans get_expected_xxx() du bloc N-1
  une ligne avec [valeur] pour couvrir la branche BR_yyy dans ce bloc."

═══ Ensuite, exécute exactement les mêmes sous-tâches A, B, C, D
    que le prompt 1 du premier bloc (ci-dessus). ═══

Les règles sont identiques :
- Sous-tâche A : lire et comprendre le code du bloc
- Sous-tâche B : lister chaque branche avec le format BR_xxx
- Sous-tâche C : concevoir les lignes de données (mêmes règles anti-datasets-vides)
- Sous-tâche D : générer [NOM_BLOC]_test_data.py et [NOM_BLOC]_branches.md

PARTICULARITÉ : dans le fichier _test_data.py de ce bloc, les fonctions
d'entrée doivent DOCUMENTER qu'elles viennent du bloc précédent :

   ```python
   def get_input_atntmp_tables() -> pd.DataFrame:
       """
       Entrée de ce bloc = sortie du Bloc 2.
       Correspond à get_expected_atntmp_tables() dans bloc_2_test_data.py.
       Si vous modifiez les données du bloc 2, mettez à jour ici aussi.
       """
       # Option 1 : importer directement
       from .bloc_2_test_data import get_expected_atntmp_tables
       return get_expected_atntmp_tables()

       # Option 2 : copie explicite si l'import pose problème
       # (dans ce cas, documenter la source)
   ```

Sauvegarde dans ./test-plan/data/

════════════════════════════════════════════════════════════
FIN DU PROMPT 1 (blocs suivants)
════════════════════════════════════════════════════════════
```

`── Fin du prompt 1 (blocs suivants) ──`

---

---

# PROMPT 2 — Validation SAS (optionnel mais recommandé)

---

## Ce que fait ce prompt

Si vous avez accès à un environnement SAS, ce prompt crée les scripts
pour exécuter le code SAS original avec vos données de test et capturer
les vrais résultats. Ces résultats remplaceront les estimations de Claude.

**Si vous n'avez pas accès à SAS**, sautez ce prompt et revenez-y plus tard.
Les données de test sont utilisables telles quelles — les résultats attendus
seront simplement des estimations à confirmer.

## Pourquoi c'est important

Claude peut lire du code SAS et en déduire les résultats. Mais sur du code
complexe (RETAIN imbriqués, macros dynamiques, interactions entre DATA steps),
il va se tromper. La seule source de vérité fiable, c'est le SAS original.

---

### 📋 PROMPT 2

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 2
════════════════════════════════════════════════════════════

Tu es un expert SAS senior. En utilisant :
- ./test-plan/00_workflows.md (les workflows)
- ./test-plan/00_blocs_test.md (les blocs de test)
- ./test-plan/data/*_test_data.py (les DataFrames de test générés)

Crée des scripts SAS pour valider les résultats estimés en exécutant
le vrai code SAS avec les données de test.

═══ Pour CHAQUE bloc de test : ═══

1. Crée ./test-plan/sas_validation/[bloc]_run.sas qui :

   a) PRÉPARE L'ENVIRONNEMENT ISOLÉ :
      - Crée des LIBNAME temporaires pointant vers des dossiers de test
      - NE TOUCHE PAS aux données de production
      - Applique les macro-variables du workflow
        (tirées du PARAMS de *_test_data.py et de run_sas_param.json)
      - Active les options de debug : MPRINT MLOGIC SYMBOLGEN
      - Active les options de robustesse : NOSYNTAXCHECK NOERRORABEND

   b) CHARGE LES DONNÉES DE TEST :
      - Pour chaque dataset d'entrée du bloc, un PROC IMPORT depuis CSV
        ou un DATA step qui recrée les données
      - Applique les formats, longueurs et labels corrects
        (basés sur ./test-plan/00_schemas_sources.md)
      - Place le dataset dans la bibliothèque attendue par le code SAS
      - Pour les blocs 2+ : charge aussi les sorties du bloc précédent
        comme entrées

   c) EXÉCUTE le code SAS original :
      - Les programmes/macros du bloc, dans l'ordre d'exécution
      - Avec le code ORIGINAL, sans modification

   d) CAPTURE LES RÉSULTATS :
      - PROC EXPORT de chaque dataset de sortie vers CSV
      - PROC CONTENTS de chaque dataset vers CSV (métadonnées :
        noms de variables, types, formats, longueurs, nb observations)
      - Copie du log complet dans [bloc]_execution.log

   IMPORTANT :
   Le code SAS doit être SIMPLE et LISIBLE. Pas de macros d'abstraction.
   Du code procédural basique qu'un développeur SAS peut lire et modifier.
   Commente abondamment chaque section.

2. Crée ./test-plan/sas_validation/compare_results.py qui :
   - Lit les CSV exportés par SAS (résultats réels)
   - Lit les DataFrames get_expected_*() des fichiers *_test_data.py
   - Compare les deux et affiche clairement :
     * Nombre de lignes : attendu vs réel
     * Colonnes manquantes ou en trop
     * Valeurs différentes (avec tolérance float de 1e-10)
     * Chaînes différentes (après strip des espaces SAS)
   - Si des différences existent :
     * Affiche un diff lisible
     * Propose le code Python pour mettre à jour le fichier _test_data.py
       avec les VRAIES valeurs SAS
   - Ajoute un flag "ground_truth" aux résultats validés

3. Crée ./test-plan/sas_validation/README.md expliquant :
   - Comment exécuter les scripts SAS (en batch ou interactif)
   - Comment lancer la comparaison
   - Comment mettre à jour les données de test avec les vrais résultats

Structure des fichiers :
  ./test-plan/sas_validation/
  ├── bloc_1_import_refs_run.sas
  ├── bloc_2_verif_vues_run.sas
  ├── bloc_3_regles_gestion_run.sas
  ├── bloc_4_tables_finales_run.sas
  ├── compare_results.py
  ├── README.md
  └── output/
      ├── bloc_1/
      │   ├── REF_STATUTS.csv
      │   ├── REF_STATUTS_meta.csv
      │   └── execution.log
      ├── bloc_2/
      └── ...

Sauvegarde dans ./test-plan/sas_validation/

════════════════════════════════════════════════════════════
FIN DU PROMPT 2
════════════════════════════════════════════════════════════
```

`── Fin du prompt 2 ──`

---

---

# PROMPT 3 — Tests pytest (quand le code Python est migré)

---

## Ce que fait ce prompt

Ce prompt n'est utile que **quand vous commencez à écrire le code Python migré**.
Avant ça, les fichiers `_test_data.py` de l'étape 1 suffisent : ils contiennent
vos données de test et les résultats attendus, prêts à l'emploi.

## Ce que vous obtenez

- Des fichiers de test pytest (`test_[bloc].py`) qui exécutent le code Python
  avec les données de test et vérifient les résultats
- Une configuration pytest + coverage (pyproject.toml, Makefile)
- Un utilitaire de comparaison `assert_sas_equal()` qui gère les subtilités
  de la migration

---

### 📋 PROMPT 3

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 3
════════════════════════════════════════════════════════════

Le code Python migré est disponible pour le bloc [NOM_BLOC].
MODULE(S) PYTHON : [CHEMIN DES MODULES PYTHON MIGRÉS]
DONNÉES DE TEST : ./test-plan/data/[bloc]_test_data.py
BRANCHES : ./test-plan/data/[bloc]_branches.md

═══ PARTIE A : Utilitaire de comparaison ═══

Crée ./test-plan/tests/helpers/comparison.py (s'il n'existe pas déjà) :

```python
"""
Utilitaire de comparaison SAS vs Python.
Équivalent de PROC COMPARE mais en Python.
"""
import pandas as pd
import numpy as np
from pandas.testing import assert_frame_equal


def assert_sas_equal(
    result: pd.DataFrame,
    expected: pd.DataFrame,
    float_tolerance: float = 1e-10,
    check_row_order: bool = True,
    sort_by: list[str] | None = None,
    strip_strings: bool = True,
    check_dtypes: bool = True,
) -> None:
    """
    Compare deux DataFrames en tenant compte des différences SAS vs Python.

    Paramètres :
    - float_tolerance : tolérance pour les nombres décimaux
      (SAS et Python arrondissent différemment)
    - check_row_order : si False, trie les deux DataFrames avant de comparer
    - sort_by : colonnes de tri si check_row_order=False
    - strip_strings : applique .strip() sur les colonnes texte
      (SAS padde les chaînes avec des espaces)
    - check_dtypes : vérifie que les types sont identiques
    """
    r = result.copy().reset_index(drop=True)
    e = expected.copy().reset_index(drop=True)

    # Strip les chaînes (padding SAS)
    if strip_strings:
        for col in r.select_dtypes(include=["string", "object"]).columns:
            r[col] = r[col].str.strip()
        for col in e.select_dtypes(include=["string", "object"]).columns:
            e[col] = e[col].str.strip()

    # Tri optionnel
    if not check_row_order and sort_by:
        r = r.sort_values(sort_by).reset_index(drop=True)
        e = e.sort_values(sort_by).reset_index(drop=True)

    assert_frame_equal(
        r, e,
        check_exact=False,
        atol=float_tolerance,
        check_dtype=check_dtypes,
    )
```

═══ PARTIE B : Fichier de test pytest ═══

Crée ./test-plan/tests/test_[bloc].py :

```python
"""
Tests de migration pour le bloc : [NOM_BLOC]
Programmes SAS couverts : [liste]
Couverture de branches visée : [SEUIL]%

Chaque test vérifie que le code Python migré produit le même résultat
que le code SAS original pour un ensemble de données de test.
"""
import pandas as pd
import numpy as np
import pytest
from helpers.comparison import assert_sas_equal

# Import des données de test
from data.[bloc]_test_data import (
    get_input_[dataset],
    get_expected_[dataset_sortie],
    PARAMS,
)

# Import du code Python migré
from [NOM_PACKAGE].[module] import [fonction_principale]


class TestBlocComplet:
    """Test d'intégration : exécute tout le bloc et vérifie la sortie."""

    def test_resultat_global(self):
        """
        Exécute le bloc complet avec toutes les données de test
        et vérifie le résultat final.
        """
        input_df = get_input_[dataset]()
        expected = get_expected_[dataset_sortie]()

        result = [fonction_principale](input_df, **PARAMS)

        assert_sas_equal(result, expected)


class TestBranchesIndividuelles:
    """Un test par branche critique pour isoler les problèmes."""

    def test_br_xxx_description(self):
        """
        BR_[xxx] : [description de la branche]
        Condition VRAI : [condition]
        Attendu : [ce qui doit se passer]
        """
        input_df = get_input_[dataset]()
        result = [fonction_principale](input_df, **PARAMS)

        # Vérification spécifique à cette branche
        lignes_concernees = result[result["colonne"] == "valeur_attendue"]
        assert len(lignes_concernees) == N


class TestPiegesMigration:
    """
    Tests ciblant les différences de comportement SAS vs Python.
    Ces tests ne correspondent pas à des scénarios métier mais à des
    pièges techniques de la migration.
    """

    def test_missing_dans_comparaison(self):
        """
        En SAS : IF montant > 0 est FAUX quand montant = .
                 car . (missing) est inférieur à 0.
        En Python : montant > 0 est FAUX quand montant = NaN,
                    MAIS pour une raison différente.

        ATTENTION : IF montant < 0 serait VRAI en SAS (. < 0)
        et FAUX en Python (NaN < 0). Ce test vérifie ce cas.
        """
        ...

    def test_merge_avec_doublons(self):
        """
        En SAS : MERGE BY avec doublons fait un appariement SÉQUENTIEL.
        En Python : pd.merge fait un produit CARTÉSIEN.
        Résultats DIFFÉRENTS.
        """
        ...

    def test_tri_avec_missing(self):
        """
        En SAS : PROC SORT met les missings EN PREMIER.
        En pandas : sort_values() met les NaN EN DERNIER.
        """
        ...

    def test_arrondi(self):
        """
        SAS : ROUND(2.5, 1) = 3 (away from zero)
        Python : round(2.5) = 2 (banker's rounding)
        """
        ...

    def test_retain_accumulation(self):
        """
        SAS : RETAIN cumul 0; cumul = cumul + montant;
        Python : groupby().cumsum() — attention, NaN casse la suite.
        """
        ...

    def test_first_last(self):
        """
        SAS : FIRST.var / LAST.var dépend du tri et du BY.
        Python : groupby + shift / transform — vérifier l'équivalence.
        """
        ...

    def test_chaines_paddees(self):
        """
        SAS : "ABC" dans une variable CHAR(10) = "ABC       ".
        Python : "ABC" != "ABC       ".
        """
        ...
```

═══ PARTIE C : Configuration pytest ═══

Crée (ou mets à jour) ./test-plan/pyproject.toml :

```toml
[project]
name = "test-migration-sas"
version = "1.0.0"
description = "Tests de couverture pour la migration SAS → Python"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "p1: chemin nominal",
    "p2: cas limites",
    "p3: gestion erreurs",
    "migration_trap: piège SAS vers Python",
    "ground_truth: résultat validé par exécution SAS réelle",
    "estimated_by_llm: résultat estimé par Claude — à confirmer",
]
addopts = ["-v", "--tb=short", "--strict-markers"]

[tool.coverage.run]
source = ["[NOM_PACKAGE]"]
branch = true

[tool.coverage.report]
fail_under = [SEUIL]
show_missing = true
```

Crée ./test-plan/Makefile :

```makefile
.PHONY: help test test-p1 test-migration coverage

help:               ## Afficher cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

test:               ## Lancer TOUS les tests
	pytest tests/ -v

test-p1:            ## Tests nominaux uniquement (P1)
	pytest tests/ -v -m p1

test-migration:     ## Tests pièges SAS→Python uniquement
	pytest tests/ -v -m migration_trap

coverage:           ## Mesurer la couverture de code
	pytest tests/ --cov=[NOM_PACKAGE] --cov-branch \
	  --cov-report=term-missing \
	  --cov-report=html:results/htmlcov \
	  --cov-report=json:results/coverage.json
	@echo ""
	@echo "Rapport HTML : results/htmlcov/index.html"

coverage-check:     ## Vérifier que le seuil est atteint
	pytest tests/ --cov=[NOM_PACKAGE] --cov-branch \
	  --cov-fail-under=[SEUIL]
```

Crée ./test-plan/tests/README.md expliquant :
- Comment lancer les tests (make test, make coverage)
- Comment lire le rapport de couverture HTML
- Comment ajouter un nouveau test
- Comment passer du mode "estimated_by_llm" au mode "ground_truth"

Sauvegarde dans ./test-plan/

════════════════════════════════════════════════════════════
FIN DU PROMPT 3
════════════════════════════════════════════════════════════
```

`── Fin du prompt 3 ──`

---

---

# PROMPT 4 — Combler les trous de couverture (itératif)

---

## Ce que fait ce prompt

Après avoir lancé `make coverage`, l'outil pytest-cov vous dit quelles lignes
et branches du code Python n'ont pas été exécutées par les tests. Ce prompt
donne cette information à Claude pour qu'il génère les données et tests
manquants.

## Combien de fois le lancer

Autant de fois que nécessaire. L'idée est de boucler :

```
make coverage → rapport → PROMPT 4 → nouveaux tests → make coverage → ...
```

Jusqu'à atteindre le seuil cible.

---

### 📋 PROMPT 4

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 4
════════════════════════════════════════════════════════════

Tu es un expert en test Python et migration SAS.

BLOC : [NOM_BLOC]
CODE PYTHON : [CHEMIN DES MODULES]
CODE SAS ORIGINAL : [CHEMIN DES FICHIERS SAS DU BLOC]
DONNÉES ACTUELLES : ./test-plan/data/[bloc]_test_data.py
SEUIL CIBLE : [SEUIL]%

Voici le rapport de couverture de pytest-cov :

─── DÉBUT DU RAPPORT ───
[COLLEZ ICI LA SORTIE DE : make coverage]
─── FIN DU RAPPORT ───

Pour CHAQUE ligne ou branche non couverte dans le rapport :

1. Lis le code Python de la ligne manquante
2. Lis le code SAS original correspondant pour comprendre le cas métier
3. Détermine quelles données d'entrée activeraient cette branche
4. AJOUTE des lignes au DataFrame existant dans [bloc]_test_data.py
   Ne recrée PAS le fichier en entier. Ajoute uniquement les lignes
   manquantes aux fonctions get_input_*() existantes.
5. Ajoute le test correspondant dans test_[bloc].py

Pour chaque nouvelle ligne ajoutée, documente en commentaire :
- Quelle ligne/branche Python elle couvre (numéro de ligne du rapport)
- Quel programme SAS original est concerné
- Pourquoi les données existantes ne couvraient pas ce cas

Si une branche est INATTEIGNABLE (code mort, condition impossible) :
- Ajoute un commentaire `# pragma: no cover` sur la ligne Python concernée
- Explique pourquoi dans [bloc]_branches.md
- Ne génère PAS de données pour cette branche

RÈGLES :
- Chaque nouveau test couvre AU MOINS une ligne/branche non couverte
- Pas de tests redondants avec ceux qui existent déjà
- Les nouvelles lignes de données sont COHÉRENTES avec les données existantes
  (mêmes types, clés de jointure valides, etc.)
- Mets à jour le fichier [bloc]_branches.md avec les nouvelles branches couvertes

Après cette génération, je relancerai make coverage pour vérifier.

════════════════════════════════════════════════════════════
FIN DU PROMPT 4
════════════════════════════════════════════════════════════
```

`── Fin du prompt 4 ──`

---

---

# PARTIE III — RÉFÉRENCE

---

---

# Arborescence complète des livrables

---

```
test-plan/
│
├── 00_workflows.md                          ← PROMPT 0
│   Liste des workflows, chaînes, entrées/sorties.
│
├── 00_schemas_sources.md                    ← PROMPT 0-BIS
│   Schéma exact de chaque table source dynamique.
│
├── 00_blocs_test.md                         ← PROMPT 0-BIS
│   Découpage en blocs testables avec tableau récap.
│
├── data/                                    ← PROMPT 1 (un jeu par bloc)
│   ├── bloc_1_import_refs_test_data.py       ← DataFrames entrée + expected
│   ├── bloc_1_import_refs_branches.md        ← Branches + couverture
│   ├── bloc_2_verif_vues_test_data.py
│   ├── bloc_2_verif_vues_branches.md
│   ├── bloc_3_regles_gestion_test_data.py
│   ├── bloc_3_regles_gestion_branches.md
│   ├── bloc_4_tables_finales_test_data.py
│   ├── bloc_4_tables_finales_branches.md
│   └── *.csv                                 ← Exports CSV pour SAS
│
├── sas_validation/                          ← PROMPT 2 (optionnel)
│   ├── bloc_1_run.sas
│   ├── bloc_2_run.sas
│   ├── bloc_3_run.sas
│   ├── bloc_4_run.sas
│   ├── compare_results.py
│   ├── README.md
│   └── output/
│       ├── bloc_1/ (CSV + meta + log)
│       ├── bloc_2/
│       └── ...
│
├── tests/                                   ← PROMPT 3 (après migration Python)
│   ├── helpers/
│   │   └── comparison.py                     ← assert_sas_equal()
│   ├── test_bloc_1_import_refs.py
│   ├── test_bloc_2_verif_vues.py
│   ├── test_bloc_3_regles_gestion.py
│   ├── test_bloc_4_tables_finales.py
│   └── README.md
│
├── results/                                 ← Résultats d'exécution
│   ├── coverage.json
│   └── htmlcov/index.html                    ← Rapport couverture navigable
│
├── pyproject.toml                           ← Config pytest + coverage
└── Makefile                                 ← Commandes simplifiées
```

---

---

# Pièges de migration SAS → Python — Référence rapide

---

Les données de test doivent systématiquement couvrir ces différences.
Le prompt 1 génère automatiquement des lignes pour chaque piège détecté.

---

### 1. Missing dans les comparaisons

```sas
/* SAS : . (missing) est INFÉRIEUR à tout nombre */
IF montant > 0 THEN ...    /* FAUX si montant = . */
IF montant < 0 THEN ...    /* VRAI si montant = . (car . < 0) */
```

```python
# Python : NaN n'est ni supérieur, ni inférieur, ni égal à rien
montant > 0    # False si NaN  ← même résultat par coïncidence
montant < 0    # False si NaN  ← DIFFÉRENT de SAS !
```

**Donnée de test** : une ligne avec `montant = NaN` pour chaque IF/WHERE
portant sur montant.

---

### 2. MERGE avec doublons

```sas
DATA result;
  MERGE a b; BY key;
RUN;
/* Si a a 2 lignes et b a 3 lignes pour key=1 :
   SAS produit 3 lignes (appariement séquentiel avec RETAIN implicite) */
```

```python
pd.merge(a, b, on="key")
# Produit 2 × 3 = 6 lignes (produit cartésien) → DIFFÉRENT
```

**Donnée de test** : doublons sur la clé dans les DEUX datasets.

---

### 3. Ordre de tri des valeurs manquantes

```sas
PROC SORT DATA=x; BY montant; RUN;
/* Résultat : ., -5, 0, 10, 100 (missings en PREMIER) */
```

```python
df.sort_values("montant")
# Résultat : -5, 0, 10, 100, NaN (NaN en DERNIER)
# Pour reproduire SAS : df.sort_values("montant", na_position="first")
```

**Donnée de test** : NaN dans toute variable utilisée comme clé de tri.

---

### 4. Arrondi

```sas
x = ROUND(2.5, 1);    /* → 3 (away from zero) */
x = ROUND(3.5, 1);    /* → 4 */
```

```python
round(2.5)    # → 2 (banker's rounding, toward even)
round(3.5)    # → 4
# Pour reproduire SAS :
from decimal import Decimal, ROUND_HALF_UP
float(Decimal("2.5").quantize(Decimal("1"), rounding=ROUND_HALF_UP))  # → 3
```

**Donnée de test** : valeurs en x.5 pour chaque ROUND() du code.

---

### 5. RETAIN / accumulation

```sas
DATA result;
  SET input; BY groupe;
  RETAIN cumul 0;
  IF FIRST.groupe THEN cumul = 0;
  cumul = cumul + montant;
RUN;
```

```python
df["cumul"] = df.groupby("groupe")["montant"].cumsum()
# ATTENTION : si montant contient NaN, cumsum propage NaN à toute la suite.
# En SAS : . + 100 = . mais la ligne SUIVANTE reprend l'accumulation.
```

**Données de test** : un groupe sans NaN, un groupe avec NaN au milieu.

---

### 6. FIRST. / LAST.

```sas
DATA result;
  SET input; BY client_id;
  IF FIRST.client_id THEN nb = 0;
  nb + 1;
  IF LAST.client_id THEN OUTPUT;
RUN;
```

**Données de test** : groupe de 1, groupe de 2, groupe de 3+ observations.
Aussi : données NON triées pour vérifier que Python ne dépend pas du tri.

---

### 7. Chaînes paddées

```sas
/* SAS : LENGTH nom $10 → "ABC" stocké comme "ABC       " */
IF nom = "ABC" THEN ...    /* VRAI (SAS ignore le padding) */
```

```python
# Python : "ABC       " != "ABC" → il faut .str.strip()
```

**Donnée de test** : chaîne courte dans une variable de grande longueur.

---

### 8. Dates SAS

```sas
/* Une date SAS = nombre de jours depuis le 01/01/1960 */
date_effet = '15MAR2024'd;    /* stocké comme un entier */
```

```python
# Conversion Python :
pd.to_datetime(sas_date, unit="D", origin="1960-01-01")
```

**Données de test** : date "normale", date extrême (01/01/1960), date missing (NaT).

---

### 9. LAG / DIF

```sas
/* SAS : LAG est GLOBAL, pas par groupe BY */
prev_montant = LAG(montant);
/* Si les données ont des groupes, LAG renvoie la valeur de la ligne
   précédente TOUS GROUPES CONFONDUS */
```

```python
# Python : shift() est par groupe par défaut avec groupby
df.groupby("groupe")["montant"].shift(1)  # PAR groupe → DIFFÉRENT de SAS
df["montant"].shift(1)  # global → comme SAS
```

**Donnée de test** : données multi-groupes pour vérifier le périmètre du LAG.

---

### 10. PUT / INPUT avec formats

```sas
/* Conversion numérique → chaîne avec un format */
code_str = PUT(code_num, Z5.);    /* 42 → "00042" */
/* Conversion chaîne → numérique avec un informat */
montant = INPUT(montant_str, COMMA12.2);    /* "1,234.56" → 1234.56 */
```

**Donnée de test** : valeurs nécessitant des conversions de format.

---

---

# Résumé : quoi faire concrètement

---

```
1. Ouvrez Claude Code dans le dossier de votre projet SAS

2. PROMPT 0
   → Claude lit ordonnanceur/run_sas_param.json
   → Vous obtenez 00_workflows.md

3. PROMPT 0-BIS
   → Claude résout les schémas des tables dynamiques
   → Claude découpe chaque workflow en blocs de 10-25 branches
   → Vous obtenez 00_schemas_sources.md + 00_blocs_test.md

4. Pour chaque bloc (dans l'ordre du tableau de 00_blocs_test.md) :

   → PROMPT 1 (premier bloc) ou PROMPT 1 (blocs suivants)
   → Vous obtenez [bloc]_test_data.py + [bloc]_branches.md

   → VÉRIFICATION RAPIDE (30 secondes) :
     • Les DataFrames sont-ils non vides ?
     • Chaque branche a-t-elle une ligne de données ?
     • Les clés de jointure sont-elles cohérentes entre datasets ?
     Si non → relancez le prompt 1 en signalant le problème.

5. (Optionnel) PROMPT 2
   → Si accès SAS disponible
   → Exécutez les scripts SAS
   → Les résultats réels remplacent les estimations de Claude

6. (Après migration Python) PROMPT 3
   → Tests pytest + configuration + Makefile

7. (Si trous de couverture) PROMPT 4
   → Lancez make coverage
   → Collez le rapport dans le prompt
   → Claude génère les tests manquants
   → Relancez make coverage
   → Répétez jusqu'au seuil cible
```

---

---

# Niveaux de confiance

---

| Niveau | Ce qu'on a fait | Confiance | Quand |
|--------|-----------------|-----------|-------|
| **Bronze** | Prompts 0 + 0-bis + 1 | Moyenne | Début de migration. On a les données de test et les résultats estimés. |
| **Argent** | Bronze + Prompt 3 + Prompt 4 | Bonne | Migration en cours. Couverture MESURÉE par pytest-cov. |
| **Or** | Argent + Prompt 2 | Excellente | Validation finale. Résultats vérifiés contre le SAS original. |

Pour les modules critiques (calculs actuariels, provisions, etc.),
visez le niveau **Or**.
Pour le reste (import, reporting), le niveau **Argent** suffit.
