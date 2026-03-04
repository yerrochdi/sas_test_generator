# Guide : Générer des datasets de test pour une migration SAS → Python

# À partir de l'ordonnanceur du projet

---

## À qui s'adresse ce guide ?

Ce guide est destiné aux **actuaires**, **développeurs SAS** et **équipes de migration**
qui doivent générer des jeux de données de test couvrant le maximum de code SAS,
dans le cadre d'une migration vers Python.

Vous n'avez pas besoin d'être expert Python ou en testing. Chaque étape est
expliquée, et les prompts sont prêts à copier-coller dans **Claude Code**.

---

## Le principe en une phrase

> On lit le fichier d'ordonnancement du projet (`run_sas_param.json`),
> on en déduit les workflows d'exécution, puis on génère des DataFrames
> pandas de test qui couvrent toutes les branches de chaque workflow.

---

## Pourquoi partir de l'ordonnanceur ?

Un projet SAS n'est pas une collection de fichiers indépendants. C'est un
ensemble de **workflows** (chaînes de programmes exécutés dans un ordre précis)
où les sorties d'un programme sont les entrées du suivant.

Tester fichier par fichier n'a pas de sens parce que :
- Un programme isolé peut lire un dataset produit par le programme précédent.
  Sans les bonnes données en entrée, le test est vide ou incohérent.
- Les branches intéressantes apparaissent souvent à cause de l'INTERACTION
  entre les programmes (ex : le programme 1 crée un flag, le programme 3
  fait un IF sur ce flag).
- L'ordonnanceur (`run_sas_param.json`) définit les vrais points d'entrée
  et les vrais enchaînements. C'est la source de vérité.

Le bon raisonnement est donc :

```
run_sas_param.json
  → définit N workflows
    → chaque workflow est une chaîne : prog_A → prog_B → prog_C
      → les ENTRÉES du workflow sont les datasets lus par prog_A
        qui ne sont produits par aucun autre programme du workflow
      → les SORTIES du workflow sont les datasets finaux
      → les données de test doivent être injectées AUX ENTRÉES
        et les résultats vérifiés AUX SORTIES
```

---

## Vocabulaire

| Terme | Ce que ça veut dire |
|-------|---------------------|
| **Workflow** | Une chaîne de programmes SAS exécutés dans l'ordre, définie dans `run_sas_param.json`. Exemple : "chargement → calcul → reporting". |
| **Point d'entrée** | Le premier programme d'un workflow. Ses datasets d'entrée sont les seuls qu'on doit fournir comme données de test. |
| **Dataset intermédiaire** | Un dataset créé par un programme du workflow et lu par le suivant. On ne le fournit PAS en entrée de test : il est produit par l'exécution du workflow. |
| **Dataset d'entrée externe** | Un dataset lu par le workflow mais produit par AUCUN programme du workflow (ex : tables de référence, données de production). C'est ce qu'on doit fournir comme données de test. |
| **Branche** | Un endroit dans le code où le programme choisit un chemin selon les données (IF/ELSE, WHERE, SELECT/WHEN, %IF, etc.). |
| **Couverture** | Le pourcentage de branches activées par nos données de test. |
| **DataFrame** | L'équivalent Python d'un dataset SAS. |

---

## Le workflow en 4 prompts

```
PROMPT 0 ─ Découverte des workflows
            Lit run_sas_param.json, identifie chaque workflow,
            trace la chaîne de programmes, et détermine les datasets
            d'entrée externes à fournir.

PROMPT 1 ─ Analyse + génération pour UN workflow
            Lit tous les fichiers SAS d'un workflow, identifie toutes
            les branches, et génère les DataFrames de test.
            (Répéter pour chaque workflow identifié au prompt 0.)

PROMPT 2 ─ Validation SAS (si accès SAS disponible)
            Crée les scripts pour exécuter le SAS original avec les
            données de test et capturer les vrais résultats.

PROMPT 3 ─ Tests pytest (quand le code Python est migré)
            Assemble les tests automatisés pour le code Python.

PROMPT 4 ─ Combler les trous (itératif)
            Relancé après mesure de couverture pour compléter.
```

---

---

# PROMPT 0 — Découverte des workflows

---

## Ce que fait ce prompt

C'est le **point d'entrée obligatoire**. Il lit le fichier d'ordonnancement
du projet et produit une cartographie exploitable : quels workflows existent,
quels programmes ils contiennent, dans quel ordre, et surtout quels sont les
datasets d'entrée qu'il faudra fournir comme données de test.

Le livrable est un fichier `00_workflows.md` qui vous dit exactement :
- Combien de workflows tester
- Pour chacun, quels fichiers SAS sont impliqués
- Quels datasets vous devez fournir en entrée
- Par quel workflow commencer

---

### 📋 PROMPT 0 — Découverte des workflows

> Remplacez `[CHEMIN_DU_PROJET]` par le chemin absolu du projet SAS.

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
[4] reporting.sas
    lit ← LIB.PROVISIONS
    écrit → /export/rapport_provisions.xlsx
```

**Datasets d'entrée externes** (à fournir en données de test) :
| Dataset | Utilisé par | Variables clés | Description probable |
|---------|-------------|----------------|---------------------|
| LIB.POLICES | chargement.sas | num_police, date_effet, type_contrat | Portefeuille de polices |
| LIB.TABLES_MORTALITE | calcul_provisions.sas | age, sexe, qx | Tables de mortalité |
| LIB.PARAMETRES | calcul_provisions.sas | taux_technique, annee | Paramètres de calcul |

**Datasets intermédiaires** (produits par le workflow, pas à fournir) :
- WORK.DONNEES_BRUTES (chargement → nettoyage)
- WORK.DONNEES_CLEAN (nettoyage → calcul)

**Datasets de sortie** (à vérifier) :
- LIB.PROVISIONS
- /export/rapport_provisions.xlsx

**Paramètres / macro-variables** :
| Variable | Valeur (JSON) | Impact |
|----------|---------------|--------|
| &DATE_CALCUL | 31/12/2024 | Date de référence pour tous les calculs |
| &ANNEE_EXERCICE | 2024 | Filtre l'exercice comptable |

**Complexité estimée** :
- Nombre de programmes : 4
- Nombre de branches estimé : ~35
- Programmes critiques : calcul_provisions.sas (le plus complexe)

---

ÉTAPE 4 — Produis un RÉSUMÉ FINAL à la fin du document :

**Tableau récapitulatif des workflows** :

| # | Workflow | Nb programmes | Nb entrées externes | Complexité | Ordre de test recommandé |
|---|----------|---------------|---------------------|------------|--------------------------|
| 1 | Chargement + Calcul | 4 | 3 | Élevée | 2 |
| 2 | Reporting mensuel | 2 | 1 | Faible | 3 |
| 3 | Import référentiel | 1 | 2 | Faible | 1 |

**Ordre de test recommandé** :
Commence par les workflows les plus simples (moins de programmes, moins
de branches) pour valider l'approche, puis passe aux plus complexes.

**Datasets d'entrée partagés** :
Si plusieurs workflows lisent le même dataset (ex : LIB.PARAMETRES est
lu par 3 workflows différents), signale-le. On pourra créer un jeu de
données de test unique pour ce dataset, réutilisé partout.

Sauvegarde dans ./test-plan/00_workflows.md

════════════════════════════════════════════════════════════
FIN DU PROMPT 0
════════════════════════════════════════════════════════════
```

`── Fin du prompt 0 ──`

---

### Ce que vous obtenez après le prompt 0

Un fichier `00_workflows.md` qui vous dit clairement :

- « Votre projet a **3 workflows** »
- « Le workflow "Calcul provisions" exécute ces 4 programmes dans cet ordre »
- « Pour le tester, vous devez fournir les datasets LIB.POLICES, LIB.TABLES_MORTALITE et LIB.PARAMETRES »
- « Commencez par le workflow "Import référentiel" (le plus simple) »

C'est cette information qui alimente le prompt suivant.

---

---

# PROMPT 1 — Analyse + génération pour UN workflow

---

## Ce que fait ce prompt

C'est le prompt principal. Il prend UN workflow identifié au prompt 0,
lit TOUS les fichiers SAS de la chaîne d'exécution, identifie TOUTES les
branches du workflow de bout en bout, et génère les DataFrames de test
pour les **datasets d'entrée externes** uniquement.

La différence clé avec la version précédente : on ne génère pas des données
pour chaque fichier SAS séparément. On génère des données pour le **point
d'entrée du workflow**, et ces données doivent être conçues pour que,
en traversant toute la chaîne, elles activent le maximum de branches
dans TOUS les programmes.

### Pourquoi c'est mieux

Imaginons un workflow : `chargement.sas → calcul.sas → export.sas`

- `chargement.sas` ne fait qu'un import basique, 0 branches intéressantes
- `calcul.sas` a un `IF type_contrat = "VIE"` à la ligne 30
- `export.sas` a un `IF provision > 100000` à la ligne 15

Si on testait fichier par fichier, on ferait 3 jeux de données séparés.
Mais la réalité c'est qu'une seule ligne dans le dataset d'entrée POLICES
peut traverser les 3 programmes et activer des branches dans chacun.

Il faut donc raisonner au niveau du **workflow entier** :
« Cette ligne de POLICES avec type_contrat="VIE" et un gros montant va
passer par chargement (rien de spécial), activer la branche VIE dans calcul,
et activer la branche provision > 100000 dans export. »

---

### 📋 PROMPT 1 — Analyse + génération pour UN workflow

> Remplacez `[NOM_WORKFLOW]` par le nom du workflow (tiré de 00_workflows.md).
> Remplacez `[SEUIL]` par le pourcentage de couverture cible (80, 90, 100).
> Exécutez ce prompt UNE FOIS PAR WORKFLOW.

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 1
════════════════════════════════════════════════════════════

Tu es un expert SAS et Python spécialisé en génération de données de test
pour des projets actuariels.

WORKFLOW À ANALYSER : [NOM_WORKFLOW]
(Réfère-toi à ./test-plan/00_workflows.md pour la chaîne d'exécution
et les datasets d'entrée externes.)

OBJECTIF : Générer des DataFrames pandas qui, injectés aux points d'entrée
de ce workflow, couvrent [SEUIL]% des branches de TOUS les programmes
de la chaîne.

═══ SOUS-TÂCHE A : Lire tous les programmes du workflow ═══

1. Lis ./test-plan/00_workflows.md pour retrouver la chaîne d'exécution
   de ce workflow.

2. Lis CHAQUE fichier .sas de la chaîne, dans l'ordre d'exécution.
   Lis aussi les macros appelées et les fichiers %include.

3. Pour chaque programme, identifie :
   - Ce qu'il lit et ce qu'il écrit
   - Les transformations qu'il applique (calculs, filtres, jointures)

═══ SOUS-TÂCHE B : Lister TOUTES les branches du workflow ═══

Parcours CHAQUE programme de la chaîne, dans l'ordre, et liste toutes
les branches en suivant ce format :

  BRANCHE : BR_[programme]_[numéro]
  PROGRAMME : [nom du programme].sas (étape [N] du workflow)
  LIGNE : [numéro]
  CODE SAS : [la ligne de code exacte]
  CONDITION VRAI : [condition] → exemple de valeur
  CONDITION FAUX : [condition] → exemple de valeur
  IMPACT AVAL : [comment cette branche affecte les programmes suivants du workflow]

Le champ "IMPACT AVAL" est crucial. Exemple :

  BRANCHE : BR_calcul_003
  PROGRAMME : calcul.sas (étape 2)
  LIGNE : 45
  CODE SAS : IF type_contrat = "VIE" THEN flag_vie = 1;
  CONDITION VRAI : type_contrat = "VIE" → flag_vie sera 1
  CONDITION FAUX : type_contrat != "VIE" → flag_vie restera 0
  IMPACT AVAL : Dans reporting.sas (étape 3), ligne 22 :
                IF flag_vie = 1 THEN ... — cette branche aval dépend de celle-ci.

Cela permet de concevoir des données d'entrée qui activent des branches
tout au long de la chaîne, pas seulement dans le premier programme.

PATTERNS SAS CRITIQUES à repérer (pièges fréquents lors de la migration) :

- RETAIN / accumulation entre observations
- FIRST. / LAST. (traitement par groupe BY)
- MERGE avec IN= (jointures partielles)
- Missing numérique (SAS : . < 0 est VRAI ; Python : NaN < 0 est FAUX)
- Missing chaîne (SAS padde de blancs, Python non)
- Dates SAS (jours depuis 01/01/1960)
- Tri implicite (BY dans MERGE, FIRST./LAST.)
- ROUND SAS (away from zero) vs Python (banker's rounding)
- MERGE avec doublons (appariement séquentiel SAS vs cartésien Python)

Pour chaque occurrence de ces patterns, note :
  PIÈGE MIGRATION : [type] — [localisation] — [données nécessaires pour tester]

═══ SOUS-TÂCHE C : Concevoir les données de test ═══

Maintenant, conçois les DataFrames pour les datasets D'ENTRÉE EXTERNES
UNIQUEMENT (ceux identifiés dans 00_workflows.md pour ce workflow).

RAISONNEMENT À SUIVRE pour chaque ligne de données :

1. Commence par les branches du DERNIER programme de la chaîne.
   « Pour que reporting.sas passe dans la branche IF provision > 100000,
   il faut que calcul.sas produise une provision > 100000.
   Pour que calcul.sas produise ça, il faut que la police d'entrée ait
   un montant de X et un type_contrat de Y. »

2. Remonte la chaîne jusqu'aux entrées externes.
   « Donc dans le dataset LIB.POLICES, je dois avoir une ligne avec
   montant = Z et type_contrat = Y. »

3. Vérifie que cette même ligne active bien des branches dans les
   programmes intermédiaires aussi.

RÈGLES OBLIGATOIRES pour les données (éviter les problèmes de la v1) :

□ JAMAIS de dataset vide. Chaque dataset d'entrée a AU MINIMUM
  autant de lignes qu'il y a de combinaisons de branches à couvrir
  dans le premier programme qui le lit.

□ JAMAIS de valeurs génériques. Chaque valeur est choisie pour activer
  une branche précise, documentée en commentaire.

□ COHÉRENCE entre datasets liés par des jointures :
  - Si le workflow fait MERGE polices sinistres BY num_police :
    * Au moins 2 polices AVEC sinistres correspondants
    * Au moins 1 police SANS sinistre (teste le cas IN=a AND NOT IN=b)
    * Au moins 1 sinistre SANS police (teste le cas IN=b AND NOT IN=a)
  - Les clés doivent correspondre exactement (même type, même format)

□ MISSINGS testés : au moins une ligne avec missing sur chaque variable
  qui apparaît dans un IF/WHERE/CASE, UNE variable missing à la fois.

□ VALEURS LIMITES : pour chaque condition numérique (IF x > 100),
  inclure une ligne avec x = 99, une avec x = 100, une avec x = 101.

□ FIRST./LAST. : si présent, inclure des groupes de taille 1, 2, et 3+.

□ TRI respecté : les données doivent être dans l'ordre trié si le
  workflow suppose un tri (PROC SORT, BY dans MERGE).

□ DOUBLONS sur clés de jointure : si le workflow fait un MERGE BY,
  inclure au moins un cas avec doublons sur la clé dans UN des datasets
  pour vérifier le comportement SAS vs Python.

Présente les données en TABLEAUX LISIBLES :

  DATASET D'ENTRÉE : LIB.POLICES (7 observations)
  Utilisé par : chargement.sas (étape 1)
  Trié par : num_police

  | # | num_police | date_effet  | type_contrat | montant  | dt_naissance | Branches activées (toute la chaîne) |
  |---|------------|-------------|--------------|----------|--------------|--------------------------------------|
  | 1 | POL-001    | 2020-01-15  | VIE          | 150000   | 1985-03-15   | BR_charg_001V, BR_calc_003V (VIE), BR_report_002V (prov>100k) |
  | 2 | POL-002    | 2019-06-01  | IARD         | 500      | 2012-06-01   | BR_charg_001V, BR_calc_003F (pas VIE), BR_calc_005F (mineur), BR_report_002F |
  | 3 | POL-003    | 2021-11-20  | VIE          | 0        | 1990-01-01   | BR_calc_004V (montant=0) |
  | 4 | POL-004    | 2018-03-10  | PREVOYANCE   | -200     | 1978-12-05   | BR_calc_004F, BR_calc_006V (OTHERWISE) |
  | 5 | POL-005    | 2022-09-05  | VIE          | NaN      | 1980-07-20   | BR_calc_004F (missing → ELSE), PIÈGE: SAS . < 0 |
  | 6 | POL-001    | 2023-01-01  | VIE          | 80000    | 1985-03-15   | DOUBLON sur clé → teste MERGE comportement |
  | 7 | POL-006    | NaT         | IARD         | 3000     | NaT          | BR_charg_002V (date missing), PIÈGE: date SAS |

La dernière colonne "Branches activées" doit tracer les branches
activées dans TOUS les programmes du workflow, pas seulement le premier.
C'est ce qui garantit qu'on couvre la chaîne de bout en bout.

═══ SOUS-TÂCHE D : Générer le code Python ═══

Produis les fichiers suivants :

FICHIER 1 : ./test-plan/data/[NOM_WORKFLOW]_test_data.py

  ```python
  """
  Données de test pour le workflow : [NOM_WORKFLOW]
  Chaîne : chargement.sas → calcul.sas → reporting.sas
  Couverture de branches visée : [SEUIL]%
  """
  import pandas as pd
  import numpy as np


  # ════════════════════════════════════════════════════
  # DATASETS D'ENTRÉE EXTERNES
  # Ce sont les seules données à injecter. Le reste est
  # produit par l'exécution du workflow.
  # ════════════════════════════════════════════════════

  def get_input_polices() -> pd.DataFrame:
      """
      Dataset LIB.POLICES — 7 observations.
      Point d'entrée du workflow, lu par chargement.sas (étape 1).
      """
      df = pd.DataFrame({
          "num_police": [
              "POL-001",    # Ligne 1 : cas nominal VIE, majeur, gros montant
              "POL-002",    # Ligne 2 : IARD, mineur, petit montant
              "POL-003",    # Ligne 3 : VIE, montant = 0
              "POL-004",    # Ligne 4 : PREVOYANCE (OTHERWISE), montant négatif
              "POL-005",    # Ligne 5 : VIE, montant missing → piège SAS . < 0
              "POL-001",    # Ligne 6 : DOUBLON sur POL-001 → teste MERGE
              "POL-006",    # Ligne 7 : dates missing → piège conversion date SAS
          ],
          "date_effet": pd.to_datetime([
              "2020-01-15",  # date valide
              "2019-06-01",  # date valide
              "2021-11-20",  # date valide
              "2018-03-10",  # date valide
              "2022-09-05",  # date valide
              "2023-01-01",  # date valide (doublon)
              pd.NaT,        # date missing → BR_charg_002
          ]),
          # ... (toutes les colonnes avec commentaire par valeur)
      })
      # Typage strict
      df["num_police"] = df["num_police"].astype("string")
      return df

  def get_input_tables_mortalite() -> pd.DataFrame:
      """
      Dataset LIB.TABLES_MORTALITE — table de référence.
      Lu par calcul.sas (étape 2).
      Doit contenir les âges correspondant aux dates de naissance
      du dataset POLICES pour que les jointures fonctionnent.
      """
      ...

  def get_input_parametres() -> pd.DataFrame:
      """
      Dataset LIB.PARAMETRES — paramètres de calcul.
      Lu par calcul.sas (étape 2).
      """
      ...


  # ════════════════════════════════════════════════════
  # RÉSULTATS ATTENDUS EN SORTIE DU WORKFLOW
  # SOURCE : estimés par analyse du code SAS.
  # À remplacer par les vrais résultats SAS quand disponibles.
  # ════════════════════════════════════════════════════

  def get_expected_provisions() -> pd.DataFrame:
      """
      Dataset LIB.PROVISIONS — sortie finale du workflow.
      Produit par calcul.sas (étape 2), lu par reporting.sas (étape 3).
      """
      ...

  def get_expected_rapport() -> dict:
      """
      Caractéristiques attendues du rapport Excel de sortie.
      Produit par reporting.sas (étape 3).
      """
      return {
          "nb_lignes": 5,
          "colonnes_attendues": ["num_police", "provision", "statut"],
          "total_provisions": 245000.00,
      }


  # ════════════════════════════════════════════════════
  # MACRO-VARIABLES DU WORKFLOW
  # Telles que définies dans run_sas_param.json
  # ════════════════════════════════════════════════════

  WORKFLOW_PARAMS = {
      "DATE_CALCUL": "31/12/2024",
      "ANNEE_EXERCICE": "2024",
      "SEUIL_MATERIALITE": "1000",
  }
  ```

FICHIER 2 : ./test-plan/data/[NOM_WORKFLOW]_branches.md

  Documentation lisible résumant :
  - La chaîne d'exécution du workflow
  - TOUTES les branches identifiées, programme par programme
  - Le tableau des données et quelles branches chaque ligne couvre
    À TRAVERS TOUTE LA CHAÎNE (pas seulement le premier programme)
  - Le taux de couverture atteint
  - Les branches non couvertes et pourquoi
  - Les pièges de migration SAS → Python identifiés

FICHIER 3 : ./test-plan/data/[NOM_WORKFLOW]_test_data.csv (un par dataset)

  Export CSV de chaque DataFrame pour utilisation dans SAS (étape 2)
  ou pour lecture humaine. Le CSV est un COMPLÉMENT, pas un remplacement
  du fichier Python (le CSV perd les types).

═══ VÉRIFICATION FINALE ═══

Avant de terminer, relis CHAQUE programme SAS du workflow et vérifie :

□ Chaque branche identifiée est activée par au moins une ligne de données
□ Aucun dataset d'entrée n'est vide
□ Les clés de jointure sont cohérentes ENTRE les datasets
  (si POLICES a POL-001 et SINISTRES doit joindre dessus, POL-001
  existe aussi dans SINISTRES pour les cas de correspondance)
□ Les groupes pour FIRST./LAST. ont des tailles variées (1, 2, 3+)
□ Les missings sont testés sur chaque variable conditionnelle
□ Les valeurs limites sont présentes (pile sur le seuil, ±1)
□ Le champ "Branches activées" de chaque ligne trace bien les branches
  dans TOUS les programmes de la chaîne, pas seulement le premier
□ Les datasets de référence (tables de mortalité, paramètres) contiennent
  les entrées nécessaires pour que les jointures fonctionnent avec les
  données de test du dataset principal

════════════════════════════════════════════════════════════
FIN DU PROMPT 1
════════════════════════════════════════════════════════════
```

`── Fin du prompt 1 ──`

---

### Comment utiliser le prompt 1 en pratique

Après le prompt 0, vous avez un fichier `00_workflows.md` qui liste
tous les workflows avec un ordre de test recommandé.

Suivez cet ordre et lancez le prompt 1 pour chaque workflow :

```
1. Lancez PROMPT 0 → vous obtenez 00_workflows.md
   Exemple de résultat :
   "Workflow A (2 programmes, simple) → tester en premier"
   "Workflow B (5 programmes, complexe) → tester ensuite"
   "Workflow C (3 programmes, moyen) → tester en dernier"

2. Lancez PROMPT 1 avec [NOM_WORKFLOW] = "Workflow A"
   → vous obtenez workflow_a_test_data.py + workflow_a_branches.md

3. Vérifiez rapidement : les DataFrames sont-ils non vides ?
   Les branches sont-elles toutes couvertes ?

4. Lancez PROMPT 1 avec [NOM_WORKFLOW] = "Workflow B"
   → idem

5. Etc.
```

Si un dataset d'entrée est PARTAGÉ entre plusieurs workflows
(signalé dans 00_workflows.md), les données de test de ce dataset
doivent être l'UNION de ce qui est nécessaire pour chaque workflow.
Mentionnez-le à Claude dans le prompt :

> « Note : le dataset LIB.PARAMETRES est aussi utilisé par le workflow X.
> Les données de test pour ce dataset ont déjà été générées dans
> ./test-plan/data/workflow_x_test_data.py. Complète-les si nécessaire
> mais ne les recrée pas de zéro. »

---

---

# PROMPT 2 — Validation SAS (optionnel mais recommandé)

---

## Quand l'utiliser

Si vous avez accès à un environnement SAS, ce prompt crée les scripts
pour exécuter le code SAS original avec vos données de test et capturer
les vrais résultats. Ces résultats remplaceront les estimations de Claude
dans les fichiers `_test_data.py`.

**Si vous n'avez pas accès à SAS**, sautez ce prompt pour l'instant.

---

### 📋 PROMPT 2 — Scripts de validation SAS

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 2
════════════════════════════════════════════════════════════

En utilisant :
- ./test-plan/00_workflows.md (la liste des workflows)
- ./test-plan/data/*_test_data.py (les DataFrames de test générés)

Crée des scripts SAS pour valider les résultats estimés par Claude
en exécutant le vrai code SAS.

Pour CHAQUE workflow :

1. Crée ./test-plan/sas_validation/[workflow]_run.sas qui :

   a) Prépare l'environnement isolé :
      - Crée des LIBNAME temporaires pointant vers des dossiers de test
      - NE TOUCHE PAS aux données de production
      - Applique les macro-variables du workflow (tirées de run_sas_param.json)
        %LET DATE_CALCUL = 31/12/2024;
        %LET ANNEE_EXERCICE = 2024;

   b) Charge les données de test :
      - Pour chaque dataset d'entrée externe, un PROC IMPORT depuis le CSV
        correspondant (exporté par les fichiers _test_data.py)
      - Applique les formats et longueurs corrects
      - Place le dataset dans la bibliothèque attendue par le programme original

   c) Exécute la chaîne de programmes du workflow :
      - Dans l'ordre défini par l'ordonnanceur
      - Avec MPRINT MLOGIC SYMBOLGEN pour le debug
      - Avec OPTIONS NOSYNTAXCHECK NOERRORABEND pour ne pas s'arrêter en cas d'erreur

   d) Capture les résultats :
      - PROC EXPORT de chaque dataset de sortie vers CSV
      - PROC CONTENTS de chaque dataset de sortie vers CSV (métadonnées)
      - Copie du log complet dans un fichier .log

2. Crée ./test-plan/sas_validation/compare_with_estimates.py qui :
   - Lit les CSV exportés par SAS (résultats réels)
   - Lit les DataFrames expected des fichiers _test_data.py (estimations Claude)
   - Compare les deux et affiche clairement les différences :
     * Nombre de lignes différent
     * Valeurs différentes (avec tolérance float de 1e-10)
     * Colonnes manquantes ou en trop
   - Propose une mise à jour des fichiers _test_data.py avec les vraies valeurs

IMPORTANT :
Le code SAS doit être SIMPLE et LISIBLE. Pas de macros d'abstraction.
Du code procédural basique qu'un développeur SAS peut lire et modifier.

════════════════════════════════════════════════════════════
FIN DU PROMPT 2
════════════════════════════════════════════════════════════
```

`── Fin du prompt 2 ──`

---

---

# PROMPT 3 — Tests pytest (quand le code Python est migré)

---

## Quand l'utiliser

Uniquement APRÈS avoir migré un workflow (ou une partie) en Python.
Avant ça, les fichiers `_test_data.py` suffisent.

---

### 📋 PROMPT 3 — Générer les tests pytest pour un workflow migré

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 3
════════════════════════════════════════════════════════════

WORKFLOW MIGRÉ : [NOM_WORKFLOW]
MODULE(S) PYTHON : [CHEMIN DES MODULES PYTHON MIGRÉS]
DONNÉES DE TEST : ./test-plan/data/[workflow]_test_data.py
BRANCHES : ./test-plan/data/[workflow]_branches.md

Crée le fichier de test pytest ./test-plan/tests/test_[workflow].py :

1. Importe les fonctions de données depuis _test_data.py
2. Importe la ou les fonctions du code Python migré
3. Crée un test d'intégration qui exécute le workflow COMPLET :
   - Charge les datasets d'entrée
   - Applique les paramètres du workflow
   - Exécute chaque étape de la chaîne Python dans l'ordre
   - Compare la sortie finale avec le résultat attendu

4. Crée des tests unitaires par programme de la chaîne :
   - Pour chaque programme SAS migré → un test qui vérifie
     ses entrées/sorties isolément

5. Crée des tests ciblant les pièges de migration listés dans _branches.md :
   - Un test par piège identifié (missing, tri, arrondi, MERGE, etc.)

6. Utilise la fonction assert_sas_equal pour les comparaisons :

   ```python
   def assert_sas_equal(result, expected, atol=1e-10, strip_strings=True):
       """
       Compare en gérant les différences SAS vs Python :
       - Strip les chaînes (padding SAS)
       - Tolérance sur les floats
       - NaN == NaN considéré comme égal
       """
       import pandas as pd
       from pandas.testing import assert_frame_equal

       r = result.copy()
       e = expected.copy()

       if strip_strings:
           for col in r.select_dtypes(include=["string", "object"]).columns:
               r[col] = r[col].str.strip()
           for col in e.select_dtypes(include=["string", "object"]).columns:
               e[col] = e[col].str.strip()

       assert_frame_equal(
           r.reset_index(drop=True),
           e.reset_index(drop=True),
           check_exact=False,
           atol=atol,
           check_dtype=True,
       )
   ```

7. Ajoute un Makefile et pyproject.toml minimal si absents.

════════════════════════════════════════════════════════════
FIN DU PROMPT 3
════════════════════════════════════════════════════════════
```

`── Fin du prompt 3 ──`

---

---

# PROMPT 4 — Combler les trous de couverture (itératif)

---

## Quand l'utiliser

Après avoir lancé `pytest --cov --cov-branch --cov-report=term-missing`.
Relancez ce prompt autant de fois que nécessaire.

---

### 📋 PROMPT 4 — Combler les trous

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT 4
════════════════════════════════════════════════════════════

WORKFLOW : [NOM_WORKFLOW]
CODE PYTHON : [CHEMIN DES MODULES]
CODE SAS ORIGINAL : [CHEMIN DES FICHIERS SAS]
DONNÉES ACTUELLES : ./test-plan/data/[workflow]_test_data.py

Voici le rapport de couverture de pytest-cov :

--- DÉBUT DU RAPPORT ---
[COLLEZ ICI LA SORTIE DE pytest --cov --cov-branch --cov-report=term-missing]
--- FIN DU RAPPORT ---

Pour chaque ligne ou branche non couverte :

1. Lis le code Python de la ligne manquante
2. Lis le code SAS original correspondant pour comprendre le cas métier
3. Détermine quelles données d'entrée activeraient cette branche
4. AJOUTE des lignes aux DataFrames existants dans _test_data.py
   (ne recrée PAS le fichier, ajoute les lignes manquantes)
5. Ajoute le test correspondant

Pour chaque ligne ajoutée, documente :
- Quelle ligne/branche Python elle couvre
- Quel programme SAS original est concerné
- Pourquoi les données existantes ne couvraient pas ce cas

Si une branche est INATTEIGNABLE, indique-le et pourquoi.

RAPPEL : les données ajoutées doivent être cohérentes avec les données
existantes (clés de jointure, types, tri).

════════════════════════════════════════════════════════════
FIN DU PROMPT 4
════════════════════════════════════════════════════════════
```

`── Fin du prompt 4 ──`

---

---

# Arborescence des livrables

---

```
test-plan/
│
├── 00_workflows.md                              ← PROMPT 0
│   Liste de tous les workflows, chaînes d'exécution,
│   datasets d'entrée externes, ordre de test.
│
├── data/                                         ← PROMPT 1 (un jeu par workflow)
│   ├── workflow_calcul_provisions_test_data.py    ← DataFrames d'entrée + expected
│   ├── workflow_calcul_provisions_branches.md     ← Branches + couverture
│   ├── workflow_calcul_provisions_polices.csv     ← Export CSV pour SAS
│   ├── workflow_calcul_provisions_params.csv
│   ├── workflow_reporting_test_data.py
│   ├── workflow_reporting_branches.md
│   └── ...
│
├── sas_validation/                               ← PROMPT 2 (optionnel)
│   ├── workflow_calcul_provisions_run.sas         ← Script d'exécution SAS
│   ├── workflow_reporting_run.sas
│   ├── compare_with_estimates.py                  ← Comparaison estimé vs réel
│   └── output/                                    ← Résultats SAS exportés
│
├── tests/                                        ← PROMPT 3 (après migration)
│   ├── test_workflow_calcul_provisions.py
│   ├── test_workflow_reporting.py
│   └── ...
│
├── pyproject.toml
├── Makefile
└── README.md
```

---

---

# Résumé : quoi faire concrètement

---

```
1. Ouvrez Claude Code dans le dossier de votre projet SAS

2. Lancez le PROMPT 0
   → Claude lit run_sas_param.json et produit 00_workflows.md
   → Vous savez combien de workflows tester et dans quel ordre

3. Pour chaque workflow (dans l'ordre recommandé) :
   → Lancez le PROMPT 1 avec le nom du workflow
   → Vérifiez : les DataFrames ne sont pas vides ?
                 Chaque branche a une ligne de données ?
                 Les clés de jointure sont cohérentes ?

4. Si accès SAS :
   → Lancez le PROMPT 2 pour créer les scripts de validation
   → Exécutez-les dans SAS
   → Les résultats réels remplacent les estimations de Claude

5. Quand un workflow est migré en Python :
   → Lancez le PROMPT 3 pour créer les tests pytest
   → Lancez : pytest --cov --cov-branch --cov-report=term-missing
   → Si trous : lancez le PROMPT 4 avec le rapport, et recommencez
```

---

---

# Référence rapide : pièges SAS → Python

---

| # | Piège | SAS | Python | Donnée de test |
|---|-------|-----|--------|----------------|
| 1 | Missing < 0 | `. < 0` est VRAI | `NaN < 0` est FAUX | Ligne avec NaN sur chaque variable numérique conditionnelle |
| 2 | MERGE doublons | Appariement séquentiel | Produit cartésien | Doublons sur la clé BY dans les deux datasets |
| 3 | Tri NaN | Missing EN PREMIER | NaN EN DERNIER | NaN dans les clés de tri |
| 4 | Arrondi | Away from zero | Banker's (to even) | Valeurs en x.5 |
| 5 | RETAIN | État inter-lignes | Pas d'équivalent direct | NaN au milieu d'un cumul + groupes variés |
| 6 | FIRST/LAST | Rupture sur BY | groupby | Groupes de taille 1, 2, 3+ |
| 7 | Padding chaînes | `"ABC       "` | `"ABC"` | Chaîne courte dans variable longue |
| 8 | Dates epoch | Jours depuis 01/01/1960 | datetime | Dates extrêmes + NaT |
| 9 | PUT/INPUT | Conversion par format | Pas d'équivalent | Valeurs nécessitant conversion |
| 10 | LAG/DIF | Décalage global (pas par groupe) | shift() par groupe par défaut | LAG avec et sans BY group |
