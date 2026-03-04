# Guide révisé : Générer des datasets de test à partir de code SAS

# Pour une migration SAS → Python

---

## Le problème avec la version précédente

La version précédente du workflow produisait beaucoup de documentation
(inventaires, graphes, matrices) mais les datasets générés étaient :
- Parfois **vides** (aucune observation)
- Parfois avec des **doublons incohérents**
- Parfois avec des **types incorrects**
- Et la couverture mesurée était à **0%** parce qu'il n'y a pas encore
  de code Python à instrumenter

**La nouvelle approche est radicalement différente :** on travaille
**fichier SAS par fichier SAS**, et pour chaque fichier on génère
immédiatement les données de test concrètes. Pas de phase de documentation
abstraite qui précède la génération.

---

## Le principe en une phrase

> Pour chaque programme SAS, on lit le code, on identifie chaque IF/ELSE/WHERE/MERGE,
> et on crée des lignes de données qui forcent le code à passer dans chaque branche.

C'est tout. Le reste (framework pytest, rapport de couverture) vient après.

---

## Comment ça marche concrètement

Prenons un exemple simple. Voici un DATA step SAS :

```sas
DATA WORK.RESULTAT;
  SET LIB.POLICES;

  /* Branche 1 : calcul selon l'âge */
  age = INTCK('YEAR', date_naissance, '31DEC2024'd);
  IF age >= 18 THEN DO;
    statut = "MAJEUR";
    taux = 0.05;
  END;
  ELSE DO;
    statut = "MINEUR";
    taux = 0.02;
  END;

  /* Branche 2 : calcul selon le montant */
  IF montant > 0 THEN provision = montant * taux;
  ELSE IF montant = 0 THEN provision = 0;
  ELSE provision = .;   /* montant négatif ou missing */

  /* Branche 3 : type de contrat */
  SELECT (type_contrat);
    WHEN ("VIE")  prime_nette = provision * 0.9;
    WHEN ("IARD") prime_nette = provision * 0.85;
    OTHERWISE      prime_nette = provision;
  END;
RUN;
```

Ce code a **7 branches** :
1. `age >= 18` → VRAI
2. `age >= 18` → FAUX (ELSE)
3. `montant > 0` → VRAI
4. `montant = 0` → VRAI
5. `montant < 0 ou missing` → VRAI (le ELSE final)
6. `type_contrat = "VIE"` → VRAI
7. `type_contrat = "IARD"` → VRAI
8. `type_contrat = autre chose` → OTHERWISE

Pour couvrir **toutes** les branches, il faut **au minimum** ces lignes :

| # | date_naissance | montant | type_contrat | Branches couvertes |
|---|----------------|---------|--------------|-------------------|
| 1 | 1985-03-15 | 1500 | VIE | 1, 3, 6 |
| 2 | 2012-06-01 | 500 | IARD | 2, 3, 7 |
| 3 | 1990-01-01 | 0 | VIE | 1, 4, 6 |
| 4 | 1978-12-05 | -200 | PREVOYANCE | 1, 5, 8 |
| 5 | 1980-07-20 | . (missing) | VIE | 1, 5, 6 |

5 lignes suffisent pour couvrir les 8 branches. C'est **ça** qu'on veut
que Claude génère — pas un framework, pas une matrice : des lignes de données
concrètes avec les bonnes valeurs aux bons endroits.

---

## Vocabulaire

| Terme | Ce que ça veut dire |
|-------|---------------------|
| **Branche** | Un endroit dans le code SAS où le programme "choisit" un chemin selon les données. Chaque IF, ELSE, WHERE, WHEN est une branche. |
| **Couverture de branches** | Le pourcentage de branches que nos données de test activent. Si on a 8 branches et que nos données passent dans 7 d'entre elles, la couverture est de 87.5%. |
| **DataFrame** | L'équivalent Python d'un dataset SAS. Un tableau avec des colonnes typées. |
| **Fixture pytest** | Une fonction Python qui prépare un DataFrame de test. C'est l'équivalent d'un DATA step qui crée un jeu de test. |
| **Factory** | Une fonction utilitaire qui crée une ligne de données avec des valeurs par défaut. On ne modifie que ce qui change par rapport au cas nominal. |
| **Ground truth** | Les résultats réels produits par le SAS original. C'est la référence absolue pour vérifier que le code Python fait pareil. |

---

---

# LE WORKFLOW — 3 ÉTAPES AU LIEU DE 7

---

Le nouveau workflow a **3 étapes** au lieu de 7.
Chaque étape produit un résultat concret et vérifiable.

```
ÉTAPE 1 ─ Analyser UN programme SAS et générer ses datasets de test
           (on répète cette étape pour chaque programme du projet)

ÉTAPE 2 ─ Capturer les résultats SAS de référence (si accès SAS disponible)

ÉTAPE 3 ─ Assembler le tout en suite pytest
```

**La différence clé** : on ne fait plus une analyse globale abstraite
suivie d'une génération en bloc. On travaille **programme par programme**,
et pour chaque programme, Claude lit le code ET génère les données
dans le même prompt. Cela évite qu'il perde le contexte entre les phases.

---

---

# ÉTAPE 1 — Analyser et générer (programme par programme)

---

## Comment utiliser cette étape

Vous allez exécuter le prompt ci-dessous **une fois par programme SAS**
(ou par groupe de programmes fortement liés). Ne passez pas tout le projet
d'un coup : Claude perd en qualité quand il doit traiter trop de fichiers
simultanément.

**Ordre recommandé** : commencez par les programmes les plus simples
(utilitaires, chargements) puis passez aux plus complexes (calculs actuariels).

Si votre projet a 15 programmes SAS, vous exécuterez ce prompt 15 fois
(ou moins si certains programmes vont par groupes).

---

### 📋 PROMPT 1 — Analyse + génération pour UN programme SAS

> Remplacez `[FICHIER_SAS]` par le chemin du fichier à analyser.
> Remplacez `[SEUIL]` par votre cible de couverture (80, 90, 100).
> Remplacez `[NOM_MODULE_PYTHON]` par le nom du futur module Python.

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT
════════════════════════════════════════════════════════════

Tu es un expert SAS et Python spécialisé en génération de données de test.

FICHIER À ANALYSER : [FICHIER_SAS]
(Si ce programme dépend d'autres fichiers — macros, includes — lis-les aussi.)

OBJECTIF : Générer des DataFrames pandas de test qui couvrent [SEUIL]% des
branches de ce programme SAS.

Exécute les 4 sous-tâches suivantes DANS L'ORDRE, dans une seule réponse :

─── SOUS-TÂCHE A : Lire et comprendre le code ───

1. Lis le fichier SAS en entier.
2. Identifie TOUS les datasets d'ENTRÉE (ceux qui sont lus par le programme
   via SET, MERGE, UPDATE, PROC SQL FROM, etc.).
3. Pour chaque dataset d'entrée, liste les variables utilisées dans le code
   avec leur type déduit (num/char, format si visible).

─── SOUS-TÂCHE B : Lister chaque branche ───

Parcours le code ligne par ligne et liste CHAQUE branche :

FORMAT OBLIGATOIRE pour chaque branche (utilise exactement ce format) :

   BRANCHE: BR_001
   FICHIER: [nom du fichier]
   LIGNE: [numéro de ligne]
   CODE SAS: IF age >= 18 THEN ...
   CONDITION VRAI: age >= 18  →  exemple: age = 25
   CONDITION FAUX: age < 18   →  exemple: age = 15
   IMPACT: variable "statut" prend la valeur "MAJEUR" (vrai) ou "MINEUR" (faux)

N'oublie AUCUNE branche, y compris :
- Les WHERE implicites dans les SET/MERGE
- Les conditions IN= des MERGE (présence ou absence de correspondance)
- Les FIRST./LAST. (première et dernière observation d'un groupe BY)
- Les cas de missing qui modifient le résultat des IF
  (rappel : en SAS, . < 0 est VRAI, donc IF montant > 0 est FAUX
  quand montant est missing)

─── SOUS-TÂCHE C : Concevoir les lignes de données ───

Pour couvrir toutes les branches identifiées en B, construis un tableau
de données MINIMAL. Chaque ligne du tableau doit :
- Avoir des valeurs concrètes pour TOUTES les variables (pas de "à définir")
- Indiquer en commentaire quelles branches elle active
- Être cohérente avec les autres lignes (clés de jointure valides, etc.)

RÈGLES CRITIQUES pour éviter les problèmes de la version précédente :

1. JAMAIS de dataset vide. Chaque dataset d'entrée doit avoir AU MINIMUM
   autant de lignes qu'il y a de branches qui dépendent de ses valeurs.

2. JAMAIS de valeurs "placeholder" ou génériques. Chaque valeur doit être
   choisie SPÉCIFIQUEMENT pour activer une branche précise.
   MAUVAIS : client_id = 1, 2, 3, 4 (séquentiel sans raison)
   BON : age = 25 (pour activer BR_001 VRAI), age = 15 (pour BR_001 FAUX)

3. Pour les MERGE/JOIN : les datasets doivent être COHÉRENTS entre eux.
   Si le programme fait MERGE polices sinistres BY num_police, alors :
   - Certaines lignes de polices doivent avoir une correspondance dans sinistres
     (pour tester le cas IN=a AND IN=b)
   - Certaines lignes de polices doivent NE PAS avoir de correspondance
     (pour tester le cas IN=a AND NOT IN=b)
   - Certaines lignes de sinistres doivent NE PAS avoir de correspondance
     dans polices (pour tester IN=b AND NOT IN=a)

4. Pour les FIRST./LAST. : inclure des groupes de TAILLES VARIÉES :
   - Un groupe avec 1 seule observation (FIRST = LAST = même ligne)
   - Un groupe avec 2 observations (FIRST et LAST distincts)
   - Un groupe avec 3+ observations (FIRST, milieu, LAST)

5. Pour les missings : inclure des lignes avec missing sur CHAQUE variable
   qui apparaît dans une condition IF/WHERE. Le missing doit être sur
   UNE variable à la fois pour isoler l'effet.

6. Pour les tris : si le programme dépend d'un tri (BY dans MERGE,
   FIRST./LAST.), fournir les données DANS L'ORDRE TRIÉ, comme SAS
   l'exigerait après un PROC SORT.

Présente le résultat sous forme de tableau lisible :

   DATASET : LIB.POLICES (5 observations)
   | # | num_police | age | montant | type_contrat | Branches activées |
   |---|------------|-----|---------|--------------|-------------------|
   | 1 | POL-001    | 25  | 1500    | VIE          | BR_001V, BR_003V, BR_006V |
   | 2 | POL-002    | 15  | 500     | IARD         | BR_001F, BR_003V, BR_007V |
   | ...                                                                |

   DATASET : LIB.SINISTRES (3 observations)
   | # | num_police | date_sinistre | montant_sin | Branches activées |
   |---|------------|---------------|-------------|-------------------|
   | 1 | POL-001    | 2024-03-15    | 5000        | BR_010V (correspondance) |
   | 2 | POL-005    | 2024-06-01    | 2000        | BR_010F (pas de police) |
   | ...                                                                |

─── SOUS-TÂCHE D : Générer le code Python ───

Génère le code Python qui crée ces DataFrames. Produis DEUX fichiers :

FICHIER 1 : ./test-plan/data/[NOM_MODULE_PYTHON]_test_data.py

   Ce fichier contient des fonctions qui retournent les DataFrames de test.
   PAS de fixture pytest ici, juste des fonctions pures.

   ```python
   """
   Données de test pour : [FICHIER_SAS] → [NOM_MODULE_PYTHON].py
   Couverture de branches visée : [SEUIL]%
   Généré automatiquement — voir le tableau des branches ci-dessus.
   """
   import pandas as pd
   import numpy as np

   def get_input_polices() -> pd.DataFrame:
       """
       Dataset d'entrée LIB.POLICES — 5 observations couvrant les branches
       BR_001 à BR_008.

       Chaque ligne est documentée avec les branches qu'elle active.
       """
       df = pd.DataFrame({
           "num_police": ["POL-001", "POL-002", "POL-003", "POL-004", "POL-005"],
           "date_naissance": pd.to_datetime([
               "1985-03-15",   # age=39 → BR_001 VRAI (majeur)
               "2012-06-01",   # age=12 → BR_001 FAUX (mineur)
               "1990-01-01",   # age=34 → BR_001 VRAI
               "1978-12-05",   # age=46 → BR_001 VRAI
               "1980-07-20",   # age=44 → BR_001 VRAI
           ]),
           "montant": [
               1500.0,         # > 0 → BR_003 VRAI
               500.0,          # > 0 → BR_003 VRAI
               0.0,            # = 0 → BR_004 VRAI
               -200.0,         # < 0 → BR_005 VRAI
               np.nan,         # missing → BR_005 VRAI (SAS: . < 0 donc ELSE)
           ],
           "type_contrat": [
               "VIE",          # → BR_006 VRAI
               "IARD",         # → BR_007 VRAI
               "VIE",          # → BR_006 VRAI
               "PREVOYANCE",   # → BR_008 OTHERWISE
               "VIE",          # → BR_006 VRAI
           ],
       })
       # Typage strict aligné sur SAS
       df["num_police"] = df["num_police"].astype("string")
       df["type_contrat"] = df["type_contrat"].astype("string")
       return df

   def get_expected_resultat() -> pd.DataFrame:
       """
       Résultat attendu de l'exécution SAS.
       SOURCE : estimé par analyse du code (à confirmer avec exécution SAS réelle).
       """
       df = pd.DataFrame({
           "num_police": ["POL-001", "POL-002", "POL-003", "POL-004", "POL-005"],
           "statut": ["MAJEUR", "MINEUR", "MAJEUR", "MAJEUR", "MAJEUR"],
           "taux": [0.05, 0.02, 0.05, 0.05, 0.05],
           "provision": [75.0, 10.0, 0.0, np.nan, np.nan],
           "prime_nette": [67.5, 8.5, 0.0, np.nan, np.nan],
       })
       df["num_police"] = df["num_police"].astype("string")
       df["statut"] = df["statut"].astype("string")
       return df
   ```

   IMPORTANT — Règles de qualité du code généré :
   - Chaque valeur a un COMMENTAIRE indiquant la branche qu'elle active
   - Les types sont explicitement définis (pas de type "object" par défaut)
   - Les NaN/NaT sont utilisés correctement selon le type
   - Le DataFrame n'est JAMAIS vide
   - Pas de colonnes inutiles (uniquement celles utilisées par le code SAS)

FICHIER 2 : ./test-plan/data/[NOM_MODULE_PYTHON]_branches.md

   Documentation lisible par un humain résumant :
   - La liste des branches avec leur ID
   - Le tableau des données et quelles branches chaque ligne couvre
   - Le taux de couverture atteint
   - Les branches non couvertes (s'il y en a) et pourquoi

VÉRIFICATION FINALE :
Avant de terminer, relis le code SAS une dernière fois et vérifie que :
□ Chaque branche identifiée en B est activée par au moins une ligne en C
□ Aucun dataset n'est vide
□ Les clés de jointure sont cohérentes entre datasets liés
□ Les missings sont testés sur chaque variable conditionnelle
□ Les valeurs limites sont testées (pile sur le seuil, juste en dessous, juste au-dessus)
□ Le code Python en D correspond exactement aux données du tableau en C

════════════════════════════════════════════════════════════
FIN DU PROMPT
════════════════════════════════════════════════════════════
```

`── Fin du prompt 1 ──`

---

### Comment utiliser le prompt 1 en pratique

**Projet de 1 à 5 programmes SAS :**
Exécutez le prompt 1 une fois par programme.

**Projet de 5 à 20 programmes SAS :**
Commencez par le prompt d'inventaire rapide ci-dessous pour connaître
l'ordre, puis exécutez le prompt 1 programme par programme.

**Projet de 20+ programmes SAS :**
Même chose, mais groupez les programmes par "unité fonctionnelle"
(ex : tous les programmes de chargement ensemble, tous les calculs ensemble).

---

### 📋 PROMPT OPTIONNEL — Inventaire rapide (pour les gros projets)

> Ce prompt est utile uniquement si vous avez beaucoup de fichiers SAS
> et que vous ne savez pas par lequel commencer. Sinon, sautez-le.

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT
════════════════════════════════════════════════════════════

Fais un inventaire rapide du projet SAS dans [CHEMIN_DU_PROJET].

Je veux UNIQUEMENT :

1. La liste des fichiers .sas avec pour chacun :
   - Nom du fichier
   - Nombre de lignes
   - Datasets lus (SET, MERGE, FROM)
   - Datasets écrits (DATA ..., CREATE TABLE)
   - Nombre approximatif de branches (IF, SELECT, WHERE, %IF)
   - Complexité estimée : Faible / Moyenne / Élevée

2. L'ordre dans lequel je devrais les analyser
   (les feuilles — ceux qui ne dépendent de rien — en premier)

Présente le résultat sous forme de tableau, rien d'autre.
Pas de graphe Mermaid, pas de JSON, pas de rapport détaillé.

════════════════════════════════════════════════════════════
FIN DU PROMPT
════════════════════════════════════════════════════════════
```

`── Fin du prompt optionnel ──`

---

---

# ÉTAPE 2 — Capturer les résultats SAS réels (optionnel mais recommandé)

---

## Pourquoi

Les résultats attendus générés à l'étape 1 sont **estimés par Claude**.
Sur du code simple (IF/ELSE linéaire), c'est généralement correct.
Sur du code complexe (RETAIN, LAG, MERGE avec doublons, macros dynamiques),
Claude va se tromper.

Si vous avez accès à un environnement SAS, cette étape remplace les
estimations par les **vrais résultats**.

**Si vous n'avez pas accès à SAS**, sautez cette étape pour l'instant
et revenez-y plus tard.

---

### 📋 PROMPT 2 — Créer les scripts d'exécution SAS

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT
════════════════════════════════════════════════════════════

En utilisant les fichiers de données de test générés dans ./test-plan/data/,
crée des scripts SAS qui :

1. CHARGENT les DataFrames de test comme datasets SAS d'entrée :
   Pour chaque fichier [module]_test_data.py, crée un script SAS
   ./test-plan/sas_validation/[module]_load_test_data.sas qui :
   - Lit les CSV exportés (ou recrée les données en DATA step)
   - Les place dans les bibliothèques attendues par le programme original
   - Applique les formats et longueurs corrects

2. EXÉCUTENT le programme SAS original avec ces données de test :
   Crée ./test-plan/sas_validation/[module]_run.sas qui :
   - Redirige les LIBNAME vers des dossiers temporaires
   - Charge les données de test (appelle le script du point 1)
   - Exécute le programme SAS original
   - Exporte TOUS les datasets de sortie en CSV

3. COMPARENT les résultats réels avec les estimations de Claude :
   Crée ./test-plan/sas_validation/compare_results.py qui :
   - Charge le CSV exporté par SAS (résultat réel)
   - Charge le DataFrame expected de [module]_test_data.py (estimation Claude)
   - Compare les deux et affiche les différences
   - Si des différences existent, met à jour le fichier _test_data.py
     avec les VRAIES valeurs

IMPORTANT :
Le code SAS généré doit être simple et lisible. Un développeur SAS doit
pouvoir le comprendre et le modifier facilement. Pas de macros complexes,
pas d'abstractions inutiles. Du code SAS procédural basique.

════════════════════════════════════════════════════════════
FIN DU PROMPT
════════════════════════════════════════════════════════════
```

`── Fin du prompt 2 ──`

---

---

# ÉTAPE 3 — Assembler en suite pytest (une fois la migration commencée)

---

## Quand utiliser cette étape

Cette étape n'est utile que **quand vous commencez à écrire le code Python**.
Avant ça, les fichiers `_test_data.py` de l'étape 1 suffisent : ils
contiennent vos données de test et les résultats attendus, prêts à l'emploi.

---

### 📋 PROMPT 3 — Générer les tests pytest pour un module migré

> Exécutez ce prompt APRÈS avoir migré un programme SAS en module Python.
> Remplacez `[MODULE_PYTHON]` par le chemin du module migré.

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT
════════════════════════════════════════════════════════════

Le module Python migré est : [MODULE_PYTHON]
Les données de test sont dans : ./test-plan/data/[nom]_test_data.py

Crée un fichier de test pytest ./test-plan/tests/test_[nom].py qui :

1. Importe les fonctions de données de test depuis _test_data.py
2. Importe la fonction/classe principale du module Python migré
3. Pour chaque jeu de données de test, crée UN test qui :
   - Appelle la fonction Python avec les données d'entrée
   - Compare le résultat avec le résultat attendu
   - Utilise une tolérance de 1e-10 pour les flottants (arrondis SAS vs Python)
   - Gère correctement les NaN (np.nan == np.nan est Faux en Python)
   - Applique .str.strip() sur les chaînes avant comparaison (padding SAS)

4. Ajoute un test spécifique pour chaque piège de migration détecté :
   - Missing dans les comparaisons
   - Ordre de tri des NaN
   - Arrondi (SAS vs Python)
   - MERGE vs pd.merge sur doublons
   (Regarde les branches identifiées dans [nom]_branches.md pour savoir
    quels pièges sont pertinents pour ce programme)

5. Structure du fichier de test :

   ```python
   """Tests pour [FICHIER_SAS] → [MODULE_PYTHON]."""
   import pandas as pd
   import numpy as np
   import pytest
   from pandas.testing import assert_frame_equal

   # Import des données de test
   from test_plan.data.[nom]_test_data import (
       get_input_polices,
       get_expected_resultat,
   )

   # Import du module migré
   from [package].[nom] import fonction_principale


   class TestCheminNominal:
       """Vérification du chemin principal."""

       def test_resultat_complet(self):
           """Exécute le module avec toutes les données de test
           et vérifie le résultat global."""
           input_df = get_input_polices()
           expected = get_expected_resultat()

           result = fonction_principale(input_df)

           # Strip les chaînes (padding SAS)
           for col in result.select_dtypes(include="string").columns:
               result[col] = result[col].str.strip()
               expected[col] = expected[col].str.strip()

           assert_frame_equal(
               result.reset_index(drop=True),
               expected.reset_index(drop=True),
               check_exact=False,
               atol=1e-10,
           )


   class TestBranchesIndividuelles:
       """Un test par branche pour isoler les problèmes."""

       def test_br001_age_majeur(self):
           """BR_001 VRAI : age >= 18 → statut = MAJEUR"""
           input_df = get_input_polices()
           result = fonction_principale(input_df)
           majeurs = result[result["statut"] == "MAJEUR"]
           assert len(majeurs) == 4  # lignes 1, 3, 4, 5

       def test_br001_age_mineur(self):
           """BR_001 FAUX : age < 18 → statut = MINEUR"""
           input_df = get_input_polices()
           result = fonction_principale(input_df)
           mineurs = result[result["statut"] == "MINEUR"]
           assert len(mineurs) == 1  # ligne 2

       # ... un test par branche ...
   ```

Ajoute aussi un fichier pytest.ini ou pyproject.toml minimal si absent :
   [tool.pytest.ini_options]
   testpaths = ["tests"]

Et un Makefile minimal :
   test:
   	pytest tests/ -v
   coverage:
   	pytest tests/ --cov=[PACKAGE] --cov-branch --cov-report=term-missing

════════════════════════════════════════════════════════════
FIN DU PROMPT
════════════════════════════════════════════════════════════
```

`── Fin du prompt 3 ──`

---

### 📋 PROMPT 4 — Combler les trous de couverture (itératif)

> Ce prompt se lance APRÈS avoir exécuté `make coverage` et obtenu un rapport.
> Relancez-le autant de fois que nécessaire jusqu'à atteindre le seuil.

```text
════════════════════════════════════════════════════════════
DÉBUT DU PROMPT
════════════════════════════════════════════════════════════

Voici le rapport de couverture de pytest-cov :

--- DÉBUT DU RAPPORT ---
[COLLEZ ICI LA SORTIE DE pytest --cov --cov-branch --cov-report=term-missing]
--- FIN DU RAPPORT ---

Et voici le module Python : [MODULE_PYTHON]
Et le code SAS original : [FICHIER_SAS]
Et les données de test actuelles : ./test-plan/data/[nom]_test_data.py

Pour chaque ligne ou branche manquante dans le rapport :

1. Lis la ligne Python non couverte
2. Comprends quelle condition l'activerait
3. Détermine quelles données d'entrée sont nécessaires
4. AJOUTE des lignes au DataFrame existant dans _test_data.py
   (ne recrée pas le fichier en entier, ajoute uniquement les lignes manquantes)
5. Ajoute le test correspondant dans le fichier de test

Pour chaque nouvelle ligne ajoutée, documente :
- Quelle branche / ligne elle couvre
- Pourquoi les données existantes ne la couvraient pas

Si une ligne est INATTEIGNABLE (code mort), indique-le avec un commentaire
et ne génère pas de données pour elle.

RAPPEL — Les données ajoutées doivent respecter les mêmes règles :
- Valeurs concrètes (pas de placeholder)
- Cohérentes avec les autres datasets (clés de jointure)
- Un commentaire par valeur expliquant son rôle

════════════════════════════════════════════════════════════
FIN DU PROMPT
════════════════════════════════════════════════════════════
```

`── Fin du prompt 4 ──`

---

---

# Arborescence des livrables

---

Beaucoup plus simple que la version précédente :

```
test-plan/
│
├── data/                              ← ÉTAPE 1 : un fichier par programme SAS
│   ├── module_polices_test_data.py    ← DataFrames d'entrée + résultats attendus
│   ├── module_polices_branches.md     ← Liste des branches + couverture
│   ├── module_sinistres_test_data.py
│   ├── module_sinistres_branches.md
│   └── ...
│
├── sas_validation/                    ← ÉTAPE 2 : scripts pour validation SAS
│   ├── module_polices_load_test_data.sas
│   ├── module_polices_run.sas
│   ├── compare_results.py
│   └── output/                        ← Résultats CSV exportés par SAS
│
├── tests/                             ← ÉTAPE 3 : tests pytest
│   ├── test_module_polices.py
│   ├── test_module_sinistres.py
│   └── ...
│
├── pyproject.toml                     ← Configuration pytest + coverage
├── Makefile                           ← Commandes : make test, make coverage
└── README.md                          ← Guide de démarrage
```

---

---

# Les pièges SAS → Python en un coup d'œil

---

Référence rapide des différences comportementales que les données de test
doivent couvrir. Pour chaque piège, le prompt 1 génère automatiquement
des lignes de données qui le testent.

### 1. Missing dans les comparaisons

```sas
/* SAS : . (missing) est INFÉRIEUR à tout nombre */
IF montant > 0 THEN ...    /* FAUX si montant = . (car . < 0 < tout positif) */
IF montant < 0 THEN ...    /* VRAI si montant = . (car . < 0) */
```

```python
# Python : NaN n'est ni supérieur, ni inférieur, ni égal à quoi que ce soit
montant > 0    # False si NaN ✓ (même résultat que SAS par coïncidence)
montant < 0    # False si NaN ✗ (DIFFÉRENT de SAS où . < 0 est True !)
```

**Donnée de test nécessaire** : une ligne avec `montant = NaN` pour chaque
condition WHERE/IF portant sur montant.

---

### 2. MERGE avec doublons sur la clé BY

```sas
/* SAS : appariement SÉQUENTIEL */
DATA result;
  MERGE a b; BY key;
RUN;
/* Si a a 2 lignes pour key=1 et b a 3 lignes pour key=1 :
   SAS produit 3 lignes (appariement 1-1, 2-2, puis 2-3 avec RETAIN) */
```

```python
# Python : produit CARTÉSIEN
pd.merge(a, b, on="key")
# Produit 2 × 3 = 6 lignes → DIFFÉRENT
```

**Donnée de test nécessaire** : des doublons sur la clé de jointure dans
les DEUX datasets, avec des nombres de lignes différents par clé.

---

### 3. Ordre de tri des valeurs manquantes

```sas
/* SAS : missing EN PREMIER après PROC SORT */
PROC SORT DATA=x; BY montant; RUN;
/* Résultat : ., -5, 0, 10, 100 */
```

```python
# Python : NaN EN DERNIER par défaut
df.sort_values("montant")
# Résultat : -5, 0, 10, 100, NaN

# Pour reproduire le comportement SAS :
df.sort_values("montant", na_position="first")
```

**Donnée de test nécessaire** : des NaN dans toute variable utilisée comme
clé de tri (BY dans MERGE, PROC SORT avant FIRST./LAST., etc.).

---

### 4. Arrondi

```sas
/* SAS : arrondi "away from zero" */
x = ROUND(2.5, 1);    /* → 3 */
x = ROUND(3.5, 1);    /* → 4 */
```

```python
# Python : arrondi "banker's" (toward even)
round(2.5)    # → 2 (vers le pair le plus proche)
round(3.5)    # → 4

# Pour reproduire SAS :
from decimal import Decimal, ROUND_HALF_UP
float(Decimal("2.5").quantize(Decimal("1"), rounding=ROUND_HALF_UP))  # → 3
```

**Donnée de test nécessaire** : des valeurs qui tombent pile sur x.5
pour chaque ROUND() du code SAS.

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
# Équivalent Python (attention aux NaN) :
df["cumul"] = df.groupby("groupe")["montant"].cumsum()
# MAIS : si montant contient un NaN, cumsum le propage à toute la suite
# En SAS : . + 100 = . mais la ligne suivante reprend l'accumulation normalement
# → comportement DIFFÉRENT
```

**Données de test nécessaires** :
- Un groupe sans NaN (cas nominal)
- Un groupe avec un NaN au milieu (vérifie la propagation)
- Un groupe avec NaN en première position

---

### 6. FIRST. / LAST.

```sas
DATA result;
  SET input; BY client_id date_contrat;
  IF FIRST.client_id THEN nb = 0;
  nb + 1;
  IF LAST.client_id THEN OUTPUT;
RUN;
```

**Données de test nécessaires** :
- Un client_id avec 1 seul contrat (FIRST = LAST = même ligne)
- Un client_id avec 2 contrats
- Un client_id avec 5+ contrats
- Un client_id avec des dates_contrat identiques (doublons sur la 2e clé BY)

---

### 7. Chaînes paddées

```sas
/* SAS : LENGTH nom $10 → "ABC" stocké comme "ABC       " (7 espaces) */
IF nom = "ABC" THEN ...    /* VRAI en SAS (comparaison ignore le padding) */
```

```python
# Python : "ABC       " != "ABC"
# Il faut .strip() avant de comparer
```

**Donnée de test nécessaire** : une chaîne courte dans une variable de grande
longueur, pour vérifier que le code Python fait bien le .strip().

---

---

# Résumé : quoi faire concrètement

---

```
1. Ouvrez Claude Code dans le dossier de votre projet SAS

2. Si gros projet (10+ fichiers) : lancez le PROMPT OPTIONNEL d'inventaire
   pour connaître l'ordre de traitement

3. Pour chaque programme SAS, dans l'ordre :
   → Copiez-collez le PROMPT 1 en remplaçant [FICHIER_SAS]
   → Vérifiez que les DataFrames générés ne sont pas vides
   → Vérifiez que chaque branche est couverte par au moins une ligne

4. Si vous avez accès à SAS :
   → Lancez le PROMPT 2 pour créer les scripts de validation
   → Exécutez les scripts SAS et remplacez les estimations par les vrais résultats

5. Quand un module Python est migré :
   → Lancez le PROMPT 3 pour créer les tests pytest
   → Lancez make coverage pour mesurer la couverture réelle
   → Si des trous : lancez le PROMPT 4 avec le rapport, et recommencez
```

C'est tout. Pas de framework complexe, pas de 7 phases abstraites.
Des données de test concrètes, programme par programme.
