# Guide complet : Générer des tests de couverture pour une migration SAS → Python

## À qui s'adresse ce guide ?

Ce guide est destiné aux **actuaires**, **développeurs SAS** et **équipes de migration** qui doivent transformer un projet SAS existant en code Python tout en **prouvant** que le nouveau code produit exactement les mêmes résultats que l'ancien.

Vous n'avez pas besoin d'être expert Python ou en testing pour suivre ce guide. Chaque étape est expliquée, et les prompts sont prêts à être copiés-collés dans **Claude Code** (l'outil en ligne de commande d'Anthropic).

---

## Pourquoi ce workflow ?

Quand on migre du SAS vers Python, la question critique est toujours la même :

> **« Comment prouver que le code Python fait exactement la même chose que le code SAS ? »**

La réponse passe par des **jeux de données de test** (appelés "DataFrames" en Python/pandas) qui :

1. Activent **chaque branche** du code SAS (chaque IF, chaque ELSE, chaque WHERE, chaque cas particulier)
2. Capturent les **résultats produits par le SAS original** comme référence
3. Sont rejoués sur le **code Python migré** pour vérifier que les résultats sont identiques
4. Mesurent une **couverture de code réelle**, pas simplement déclarative

Sans ce processus, vous n'avez aucune garantie. Avec lui, vous pouvez dire avec confiance : *« 95% du code migré est couvert par des tests, et chaque test est validé contre le SAS original. »*

---

## Vocabulaire pour les non-initiés

| Terme | Signification |
|---|---|
| **DataFrame** | L'équivalent Python/pandas d'un dataset SAS. Un tableau avec des lignes et des colonnes typées. |
| **pytest** | Le framework de test standard en Python. C'est l'équivalent d'exécuter vos programmes SAS de validation, mais de manière automatisée et reproductible. |
| **Fixture** | Une fonction pytest qui prépare des données de test. Pensez-y comme un DATA step qui crée un dataset de test, mais en Python. |
| **Couverture de code** | Le pourcentage de lignes et de branches du code qui sont effectivement exécutées par les tests. Si votre code a un `IF age >= 18 THEN ... ELSE ...` et que vos tests ne passent jamais dans le `ELSE`, cette branche n'est pas couverte. |
| **Couverture de branches** | Plus exigeant que la couverture de lignes : on vérifie que chaque condition (IF, WHERE, SELECT...) a été testée à `VRAI` **et** à `FAUX`. |
| **Mutation testing** | On modifie volontairement le code (ex : changer un `>` en `>=`) et on vérifie qu'au moins un test échoue. Si aucun test ne détecte la modification, c'est que les tests sont trop faibles. |
| **Ground truth** | Les résultats « vrais » produits par l'exécution du SAS original. C'est la référence absolue. |
| **Claude Code** | L'outil en ligne de commande d'Anthropic qui permet de piloter Claude directement dans un terminal, avec accès à votre système de fichiers local. |

---

## Vue d'ensemble du processus

Le workflow se décompose en **7 phases** que vous exécutez dans l'ordre. Chaque phase produit des fichiers concrets dans un dossier `test-plan/`.

```
PHASE 0 ─ Préparer la capture des résultats SAS (la "vérité")
   │
PHASE 1 ─ Cartographier le projet SAS
   │       (Qu'est-ce qu'il y a dans le projet ? Quel programme appelle quoi ?)
   │
PHASE 2 ─ Analyser le code en profondeur
   │       (Quelles branches ? Quels cas possibles ? Quels pièges ?)
   │
PHASE 3 ─ Planifier les tests
   │       (Quels scénarios faut-il pour couvrir tout le code ?)
   │
PHASE 4 ─ Générer les données de test en Python
   │       (Créer les DataFrames pandas et les résultats attendus)
   │
PHASE 5 ─ Assembler le harnais de test
   │       (Tout câbler pour que ça tourne avec une seule commande)
   │
PHASE 6 ─ Mesurer, itérer, prouver
           (Boucler jusqu'à atteindre le seuil de couverture cible)
```

---

## Avant de commencer : ce dont vous avez besoin

1. **Le projet SAS cloné sur votre machine** dans un dossier accessible (ex : `/home/moi/projet-sas/`)
2. **Claude Code installé** (voir https://docs.anthropic.com)
3. **Python 3.10+** avec les packages suivants :
   ```bash
   pip install pandas numpy pytest pytest-cov
   ```
4. **Optionnel mais fortement recommandé** : un accès à un environnement SAS pour exécuter le code original et capturer les résultats de référence. Sans cela, les résultats attendus seront estimés par Claude (fiable sur du code simple, risqué sur du code complexe).

---

## Comment utiliser les prompts

Chaque phase contient un ou plusieurs **prompts** à passer à Claude Code. Les prompts sont encadrés comme suit :

> **Début du prompt** : marqué par une bordure et le label `📋 PROMPT X.X`
>
> **Fin du prompt** : marqué par `── Fin du prompt X.X ──`

**Avant de copier-coller**, remplacez toujours les éléments entre crochets :
- `[CHEMIN_DU_PROJET]` → le chemin absolu vers votre projet SAS (ex : `/home/moi/projet-sas`)
- `[SEUIL]` → le pourcentage de couverture cible (ex : `80` pour 80%, `100` pour 100%)
- `[NOM_PACKAGE]` → le nom de votre package Python cible (ex : `calculs_actuariels`)

---

---

# PHASE 0 — Capturer la vérité SAS

---

## Pourquoi cette phase est indispensable

Claude peut lire du code SAS et en déduire ce qu'il est censé produire. Mais sur du code complexe (RETAIN imbriqués, macros dynamiques, interactions entre DATA steps), **il va se tromper**. La seule source de vérité fiable, c'est d'exécuter le SAS original avec vos données de test et de capturer les vrais résultats.

Si vous n'avez pas accès à un environnement SAS, vous pouvez sauter cette phase et y revenir plus tard. Les tests seront marqués comme « résultat estimé par Claude » pour que vous sachiez lesquels restent à confirmer.

---

### 📋 PROMPT 0.1 — Générer le harnais de capture SAS

> Copiez-collez le bloc ci-dessous dans Claude Code tel quel, après avoir remplacé `[CHEMIN_DU_PROJET]`.

```text
Tu es un expert SAS senior spécialisé en validation et qualification de code.

CONTEXTE : Nous migrons un projet SAS vers Python. Avant de commencer la
migration, nous devons pouvoir exécuter le code SAS original avec des données
de test contrôlées et capturer les résultats exacts pour les utiliser comme
référence ("ground truth") dans nos tests Python.

Projet SAS source : [CHEMIN_DU_PROJET]

TÂCHE : Crée un harnais d'exécution SAS qui permet de :

1. **Injecter des données de test** à la place des données réelles :
   - Crée un programme ./test-plan/sas_runner/setup_test_env.sas qui :
     * Redirige chaque LIBNAME du projet vers un répertoire de test temporaire
     * Permet de charger des CSV comme datasets d'entrée
       (pour chaque dataset d'entrée, un PROC IMPORT depuis un CSV)
     * Isole l'environnement (WORK temporaire, pas d'écriture sur les données réelles)
     * Applique les OPTIONS nécessaires : NOSYNTAXCHECK NOERRORABEND MPRINT MLOGIC SYMBOLGEN

2. **Capturer tous les résultats** après exécution :
   - Crée un programme ./test-plan/sas_runner/capture_results.sas qui :
     * Identifie TOUS les datasets créés pendant l'exécution (dans WORK et les autres libnames)
     * Exporte chaque dataset en CSV avec PROC EXPORT
     * Exporte les métadonnées de chaque dataset avec PROC CONTENTS → CSV
       (noms de variables, types, formats, longueurs, nombre d'observations)
     * Sauvegarde le log complet dans un fichier .log
     * Crée un fichier résumé listing tous les datasets exportés

3. **Script d'orchestration** :
   - Crée ./test-plan/sas_runner/run_scenario.sas qui enchaîne :
     a. setup_test_env.sas (préparer l'environnement)
     b. Le(s) programme(s) SAS du projet (exécution réelle)
     c. capture_results.sas (capturer les résultats)
   - Ce script accepte un paramètre &SCENARIO_ID (ex: TC_001) pour
     savoir dans quel sous-dossier lire les entrées et écrire les sorties

4. **Script Python de collecte** :
   - Crée ./test-plan/sas_runner/collect_ground_truth.py qui :
     * Lit les CSV exportés par SAS
     * Les convertit en DataFrames pandas avec les types corrects
       (en s'appuyant sur les métadonnées PROC CONTENTS)
     * Gère la conversion des dates SAS (jours depuis 01/01/1960 → datetime Python)
     * Gère la conversion des missings SAS (. → NaN, "" → None)
     * Sauvegarde chaque DataFrame en Parquet dans ./test-plan/tests/data/ground_truth/
       (le format Parquet préserve les types, contrairement au CSV)

Structure de dossiers attendue :
   ./test-plan/sas_runner/
   ├── setup_test_env.sas        # Redirection des libnames
   ├── capture_results.sas       # Export des résultats en CSV
   ├── run_scenario.sas          # Orchestration
   ├── collect_ground_truth.py   # CSV SAS → Parquet Python
   ├── input/                    # Dossier pour les CSV d'entrée par scénario
   │   ├── TC_001/
   │   │   ├── clients.csv
   │   │   └── contrats.csv
   │   └── TC_002/
   └── output/                   # Dossier pour les résultats capturés
       ├── TC_001/
       │   ├── result.csv
       │   ├── result_meta.csv
       │   └── execution.log
       └── TC_002/

IMPORTANT : Commente abondamment le code SAS généré. Les utilisateurs sont
des actuaires et développeurs SAS, pas des experts en frameworks de test.
Chaque étape doit être compréhensible.

Sauvegarde tous les fichiers dans ./test-plan/sas_runner/
```

`── Fin du prompt 0.1 ──`

---

### 📋 PROMPT 0.2 — Configurer le mode dégradé (sans accès SAS)

> Utilisez ce prompt uniquement si vous n'avez PAS accès à un environnement SAS pour le moment.

```text
Je n'ai pas accès à un environnement SAS pour l'instant. Configure le workflow
en mode dégradé :

1. Dans ./test-plan/tests/conftest.py, ajoute deux marqueurs pytest :

   - @pytest.mark.ground_truth :
     signifie que le résultat attendu provient d'une exécution SAS réelle.
     Ces tests sont fiables.

   - @pytest.mark.estimated_by_llm :
     signifie que le résultat attendu a été calculé par Claude en lisant
     le code SAS. Ces tests sont à confirmer dès qu'un environnement SAS
     sera disponible.

2. Par défaut, marque TOUS les tests générés avec @pytest.mark.estimated_by_llm

3. Crée un script ./test-plan/scripts/upgrade_to_ground_truth.py qui :
   - Prend en entrée le dossier ./test-plan/sas_runner/output/TC_XXX/
     (les résultats réels SAS quand ils seront disponibles)
   - Remplace les fixtures "estimated" par les données réelles
   - Change le marqueur de estimated_by_llm à ground_truth
   - Produit un rapport des différences trouvées entre
     les estimations de Claude et les résultats SAS réels

4. Ajoute dans le rapport final une section "Tests à confirmer" listant
   tous les tests marqués estimated_by_llm

Sauvegarde dans ./test-plan/
```

`── Fin du prompt 0.2 ──`

---

---

# PHASE 1 — Cartographier le projet SAS

---

## Ce que fait cette phase

Avant de tester quoi que ce soit, il faut comprendre le projet. Cette phase demande à Claude de parcourir tous vos fichiers SAS et de produire :

- Un **inventaire** de tout ce qui existe (programmes, macros, includes, données)
- Un **graphe de dépendances** (qui appelle quoi, quels datasets circulent d'un programme à l'autre)
- Un **ordre de migration** recommandé (par quoi commencer ?)

C'est l'équivalent de faire un audit de votre code base avant de toucher à quoi que ce soit.

---

### 📋 PROMPT 1.1 — Inventaire complet du projet

```text
Tu es un expert en migration SAS → Python et en audit de code actuariel.

Analyse le projet SAS situé dans : [CHEMIN_DU_PROJET]

Effectue un inventaire complet du projet :

1. ARBORESCENCE :
   - Parcours récursivement TOUS les fichiers
   - Classe chaque fichier par type :
     * .sas → programme principal, macro (%macro/%mend), include, autoexec, format
     * .sas7bdat → dataset SAS permanent
     * .csv, .xlsx → données externes
     * .egp → projet Enterprise Guide (note sa présence mais ne l'ouvre pas)
     * .cfg, .log → fichiers de configuration et logs

2. RÔLE DE CHAQUE PROGRAMME :
   Pour chaque fichier .sas, indique :
   - Son rôle probable (ETL/chargement, calcul, reporting, utilitaire)
   - S'il est un point d'entrée (programme principal exécuté directement)
     ou un composant (macro/include appelé par d'autres)
   - Les datasets qu'il LIT en entrée (nom de la bibliothèque et du dataset)
   - Les datasets qu'il ÉCRIT en sortie
   - Les macros qu'il DÉFINIT (%macro ... %mend)
   - Les macros qu'il APPELLE (%nom_macro)
   - Les fichiers qu'il inclut (%include)

3. BIBLIOTHÈQUES (LIBNAME) :
   - Liste toutes les déclarations LIBNAME du projet
   - Pour chacune : nom logique, chemin physique, moteur (BASE, ORACLE, XLSX...)
   - Identifie les bibliothèques qui pointent vers des données de production
     (ce sont celles qu'il faudra remplacer par des données de test)

4. SOURCES DE DONNÉES EXTERNES :
   - Fichiers CSV/Excel importés (PROC IMPORT, DATA step INFILE)
   - Connexions bases de données (LIBNAME avec moteur ORACLE, ODBC, etc.)
   - API ou fichiers distants

5. MACRO-VARIABLES GLOBALES :
   - Toutes les %LET et %GLOBAL trouvées
   - Les valeurs assignées et leur impact sur le comportement du code
   - Les macro-variables qui semblent être des paramètres de configuration
     (dates de référence, seuils, chemins, etc.)

FORMAT DU LIVRABLE :
Produis un document Markdown clair et structuré. Pour chaque programme,
utilise un bloc comme celui-ci :

   ### programme_calcul.sas
   - **Rôle** : Calcul des provisions techniques
   - **Type** : Programme principal (point d'entrée)
   - **Entrées** : LIB.POLICES, LIB.SINISTRES, LIB.TABLES_MORTALITE
   - **Sorties** : WORK.PROVISIONS, LIB.RESULTATS_PROVISIONS
   - **Macros appelées** : %CALCUL_PM, %CALCUL_PSAP, %ARRONDI_EURO
   - **Includes** : /macros/utilitaires.sas
   - **Macro-variables utilisées** : &DATE_CALCUL, &ANNEE_EXERCICE, &SEUIL_MATERIALITE

Sauvegarde dans ./test-plan/01_inventaire_projet.md
```

`── Fin du prompt 1.1 ──`

---

### 📋 PROMPT 1.2 — Graphe de dépendances et ordre de migration

```text
En te basant sur l'inventaire que tu viens de produire dans
./test-plan/01_inventaire_projet.md, construis maintenant le graphe
de dépendances du projet.

1. GRAPHE DE DÉPENDANCES (./test-plan/02_dependances.json) :
   Pour chaque programme et macro, crée une entrée JSON :
   {
     "file": "programme_calcul.sas",
     "type": "programme_principal",
     "reads": ["LIB.POLICES", "LIB.SINISTRES"],
     "writes": ["WORK.PROVISIONS", "LIB.RESULTATS"],
     "calls_macros": ["%CALCUL_PM", "%CALCUL_PSAP"],
     "includes": ["/macros/utilitaires.sas"],
     "called_by": ["main.sas"],
     "execution_order": 3
   }

   Détermine l'ordre d'exécution logique par tri topologique :
   un programme ne peut s'exécuter qu'après ceux dont il lit les sorties.

2. DIAGRAMME VISUEL (./test-plan/02_dependances.mmd) :
   Produis un diagramme Mermaid montrant :
   - Les programmes comme des boîtes
   - Les datasets comme des cylindres
   - Les flèches de dépendance (qui lit quoi, qui produit quoi)
   - Les macros comme des losanges

   Exemple de syntaxe Mermaid :
   ```mermaid
   graph LR
     A[main.sas] --> B[(LIB.POLICES)]
     B --> C[calcul_provisions.sas]
     C --> D[(WORK.PROVISIONS)]
     C -.-> E{%CALCUL_PM}
   ```

3. ORDRE DE MIGRATION RECOMMANDÉ :
   - Identifie les "feuilles" du graphe : les programmes/macros qui ne
     dépendent de rien d'autre dans le projet (ou seulement de données d'entrée).
     Ce sont les premiers à migrer et tester.
   - Puis remonte vers les programmes qui dépendent de ces feuilles, etc.
   - Identifie les "unités migrables" : des groupes de code SAS qui forment
     une fonction logique autonome (ex : "calcul des provisions mathématiques").
     Chaque unité deviendra un module Python testable indépendamment.

   Présente l'ordre sous forme de tableau :
   | Ordre | Fichier(s) SAS | Unité migrable | Module Python cible | Complexité |
   |-------|----------------|----------------|---------------------|------------|
   | 1     | utilitaires.sas | Fonctions utilitaires | utils.py | Faible |
   | 2     | chargement.sas | ETL/Import données | etl.py | Moyenne |
   | 3     | calcul_pm.sas | Provisions mathématiques | provisions.py | Élevée |

Sauvegarde dans ./test-plan/
```

`── Fin du prompt 1.2 ──`

---

---

# PHASE 2 — Analyser le code en profondeur

---

## Ce que fait cette phase

C'est le cœur analytique du workflow. Claude va lire chaque ligne de code SAS et identifier :

- Toutes les **branches** : chaque endroit où le code peut prendre des chemins différents selon les données (IF/ELSE, SELECT/WHEN, WHERE, etc.)
- Les **patterns SAS dangereux** pour la migration : les constructions SAS qui n'ont pas d'équivalent direct en Python et qui sont une source fréquente de bugs lors de la migration
- Le **dictionnaire de données** : la structure exacte de chaque dataset (variables, types, formats) et son équivalent Python

### Qu'est-ce qu'une « branche » ?

En SAS, chaque fois que le code prend une décision, c'est une branche :

```sas
/* Ceci crée 2 branches : age >= 18 (branche VRAI) et age < 18 (branche FAUX) */
IF age >= 18 THEN statut = "MAJEUR";
ELSE statut = "MINEUR";

/* Ceci crée 3 branches : une par WHEN, plus le OTHERWISE */
SELECT (type_contrat);
  WHEN ("VIE")    DO; ... END;
  WHEN ("IARD")   DO; ... END;
  OTHERWISE        DO; ... END;
END;
```

Pour couvrir tout le code, il faut des données de test qui passent dans **chaque** branche au moins une fois.

---

### 📋 PROMPT 2.1 — Analyse des branches et chemins d'exécution

```text
Tu es un expert en analyse statique de code SAS, spécialisé en code actuariel
et en assurance qualité logicielle.

Pour CHAQUE fichier .sas du projet situé dans [CHEMIN_DU_PROJET], effectue
une analyse exhaustive de toutes les branches et chemins d'exécution.

IMPORTANT : Attribue un identifiant unique à chaque branche trouvée,
au format BR_[nom_fichier]_[numéro]. Cet identifiant sera utilisé dans
toutes les phases suivantes pour tracer la couverture.

Pour chaque fichier, documente :

1. BRANCHES CONDITIONNELLES :
   Liste CHAQUE structure conditionnelle trouvée dans le code :

   a) Dans les DATA steps :
      - IF / THEN / ELSE IF / ELSE
      - SELECT / WHEN / OTHERWISE
      - WHERE (dans les SET, MERGE, UPDATE)
      - Conditions dans les boucles DO WHILE, DO UNTIL
      - Conditions implicites (ex: MERGE avec IN= crée des branches
        selon que l'observation a une correspondance ou non)

   b) Dans les PROC SQL :
      - WHERE
      - CASE / WHEN / ELSE
      - HAVING
      - Sous-requêtes conditionnelles

   c) Dans les macros :
      - %IF / %THEN / %ELSE
      - %DO %WHILE / %DO %UNTIL
      - Conditions basées sur %EVAL, %SYSEVALF

   Pour chaque branche, indique :
   - ID : BR_[fichier]_[numéro]
   - Ligne(s) du code source
   - Condition exacte (copie du code SAS)
   - Branche VRAI : ce qui se passe quand la condition est remplie
   - Branche FAUX : ce qui se passe sinon
   - Valeurs de données nécessaires pour activer chaque côté

   Exemple :
   | ID | Fichier | Ligne | Condition | Pour activer VRAI | Pour activer FAUX |
   |----|---------|-------|-----------|-------------------|-------------------|
   | BR_calc_001 | calcul.sas | 45 | IF age >= 18 | age = 20 | age = 15 |
   | BR_calc_002 | calcul.sas | 52 | WHERE montant > 0 | montant = 100 | montant = -5 |

2. PATTERNS SAS CRITIQUES POUR LA MIGRATION :
   Identifie CHAQUE occurrence des patterns suivants, car ils se comportent
   différemment en Python et sont la source n°1 de bugs de migration :

   a) RETAIN et accumulation :
      - Le RETAIN maintient une valeur d'une observation à la suivante.
        En Python, ça se traduit par shift(), cumsum(), ou expanding().
      - Documente la variable retenue, sa valeur initiale, et la logique d'accumulation.

   b) FIRST. / LAST. (traitement par rupture) :
      - SAS détecte automatiquement la première et dernière observation de chaque
        groupe après un BY. En Python, c'est groupby() + transform() ou apply().
      - Documente les variables BY, et ce que le code fait sur FIRST et LAST.

   c) MERGE avec IN= :
      - Un MERGE SAS avec IF A et IF B se comporte comme un INNER JOIN.
        Un MERGE avec seulement IF A se comporte comme un LEFT JOIN.
      - ATTENTION : si les deux datasets ont des doublons sur les clés BY,
        le MERGE SAS fait un appariement séquentiel (pas un produit cartésien
        comme pd.merge en Python). C'est le piège n°1 de la migration.

   d) Valeurs manquantes (missing) :
      - En SAS, un missing numérique (.) est INFÉRIEUR à tout nombre.
        Donc (. < 0) est VRAI en SAS mais (NaN < 0) est FAUX en Python.
      - En SAS, une chaîne missing est une chaîne vide paddée d'espaces.
        En Python, c'est None ou pd.NA.
      - Documente CHAQUE endroit où un missing pourrait affecter une condition.

   e) Dates SAS :
      - Une date SAS est un nombre entier = jours depuis le 01/01/1960.
        En Python, c'est un objet datetime.
      - Documente chaque variable date et les calculs effectués dessus.

   f) Ordre de tri :
      - Beaucoup d'opérations SAS dépendent implicitement du tri
        (MERGE BY, FIRST./LAST., PROC MEANS/SUMMARY BY).
      - En SAS, les missings sont triés EN PREMIER. En pandas, les NaN
        sont triés EN DERNIER par défaut.

   g) Array processing :
      - Les ARRAY SAS n'existent pas en Python. Ils sont généralement
        remplacés par des opérations vectorielles pandas ou des apply().

   h) Fonctions SAS spécifiques :
      - INTCK, INTNX (calculs de dates)
      - PUT/INPUT avec formats (conversions)
      - ROUND (arrondi SAS vs arrondi bancaire Python)
      - SUBSTR, SCAN, COMPRESS, TRANWRD (manipulation de chaînes)
      - LAG, DIF (décalage entre observations)

   Pour chaque occurrence, documente :
   - Le pattern trouvé et sa localisation
   - Le comportement SAS exact
   - Le piège potentiel lors de la migration Python
   - Les données de test nécessaires pour vérifier que la migration est correcte

3. RÉSUMÉ PAR FICHIER :
   À la fin, crée un tableau récapitulatif :
   | Fichier | Nb branches | Nb patterns critiques | Complexité estimée | Priorité de test |
   |---------|-------------|----------------------|--------------------|--------------------|
   | calcul.sas | 15 | 8 | Élevée | P1 |
   | reporting.sas | 3 | 1 | Faible | P3 |

Sauvegarde dans ./test-plan/03_analyse_branches.md
```

`── Fin du prompt 2.1 ──`

---

### 📋 PROMPT 2.2 — Dictionnaire de données avec mapping SAS → Python

```text
En te basant sur :
- L'inventaire ./test-plan/01_inventaire_projet.md
- L'analyse des branches ./test-plan/03_analyse_branches.md

Crée un dictionnaire de données complet qui décrit CHAQUE dataset d'entrée
du projet et son équivalent Python.

Ce dictionnaire est crucial : c'est lui qui garantit que les DataFrames de
test auront les bons types, les bons formats, et les bonnes contraintes.

Pour CHAQUE dataset d'entrée du projet, documente :

1. IDENTITÉ :
   - Nom SAS (bibliothèque.dataset)
   - Nom Python proposé (nom du DataFrame, en snake_case)
   - Programmes qui le lisent
   - Comment il est trié (clés BY utilisées en aval)

2. VARIABLES — pour chaque variable utilisée dans le code :
   - Nom SAS et nom Python proposé (snake_case)
   - Type SAS (num ou char) et longueur
   - Format SAS et informat (DATE9., COMMA12.2, $50., etc.)
   - Type pandas équivalent :
     * num sans format date → float64 (ou Int64 si entier sans missing)
     * num avec format date → datetime64[ns]
     * char → string (pd.StringDtype, pas object)
   - Peut-il être missing ? (OUI/NON)
     Si OUI : quel type de missing Python utiliser ?
     * float64 → np.nan
     * Int64 (nullable) → pd.NA
     * string → pd.NA
     * datetime64 → pd.NaT
   - Contraintes métier (plage de valeurs, format attendu, unicité, etc.)
   - Dans quelles branches (BR_xxx) cette variable est-elle utilisée ?
   - Valeurs limites à tester (frontières des conditions IF/WHERE)

3. RELATIONS ENTRE DATASETS :
   - Clés de jointure (variables BY dans les MERGE, ON dans les SQL JOIN)
   - Type de jointure (INNER, LEFT, RIGHT, FULL)
   - Cardinalité attendue (1-à-1, 1-à-N, N-à-N)
   - Attention aux doublons sur les clés

4. PIÈGES DE CONVERSION — pour chaque variable, signale les risques :
   - Dates : "SAS date = jours depuis 01/01/1960. Conversion :
     pd.to_datetime(sas_date, unit='D', origin='1960-01-01')"
   - Chaînes : "SAS padde avec des espaces à droite jusqu'à la longueur
     déclarée. Appliquer .str.strip() après import."
   - Missings : "SAS . est < tout nombre. Tester avec np.nan et vérifier
     que les conditions WHERE/IF donnent le même résultat."
   - Arrondi : "SAS ROUND(x, 0.01) arrondit 0.005 → 0.01 (away from zero).
     Python round(0.005, 2) → 0.0 (banker's rounding). Utiliser
     decimal.Decimal ou une fonction custom."

FORMAT : Produis un fichier JSON structuré.

Exemple de structure :
{
  "datasets": [
    {
      "sas_name": "PROD.POLICES",
      "python_name": "df_polices",
      "used_by": ["calcul_pm.sas", "reporting.sas"],
      "sort_keys": ["NUM_POLICE"],
      "variables": [
        {
          "sas_name": "NUM_POLICE",
          "python_name": "num_police",
          "sas_type": "char",
          "sas_length": 15,
          "sas_format": "$15.",
          "pandas_dtype": "string",
          "nullable": false,
          "constraints": "Identifiant unique, format 'POL-XXXXXXXXXX'",
          "used_in_branches": ["BR_calc_001", "BR_calc_005"],
          "boundary_values": ["POL-0000000001", "POL-9999999999", null, ""],
          "migration_warning": "Appliquer .str.strip() après chargement"
        },
        {
          "sas_name": "DATE_EFFET",
          "python_name": "date_effet",
          "sas_type": "num",
          "sas_length": 8,
          "sas_format": "DATE9.",
          "pandas_dtype": "datetime64[ns]",
          "nullable": true,
          "constraints": "Entre 01/01/2000 et aujourd'hui",
          "used_in_branches": ["BR_calc_003", "BR_calc_004"],
          "boundary_values": ["2000-01-01", "2024-12-31", null],
          "migration_warning": "Conversion : pd.to_datetime(val, unit='D', origin='1960-01-01')"
        }
      ],
      "relationships": [
        {
          "target_dataset": "PROD.SINISTRES",
          "join_keys": ["NUM_POLICE"],
          "sas_method": "MERGE POLICES SINISTRES; BY NUM_POLICE;",
          "python_method": "pd.merge(df_polices, df_sinistres, on='num_police', how='left')",
          "cardinality": "1-à-N",
          "migration_warning": "Vérifier le comportement avec doublons sur NUM_POLICE"
        }
      ]
    }
  ]
}

Sauvegarde dans ./test-plan/04_dictionnaire_donnees.json
```

`── Fin du prompt 2.2 ──`

---

---

# PHASE 3 — Planifier les tests

---

## Ce que fait cette phase

Maintenant que nous avons la liste de toutes les branches et la structure des données, il faut déterminer **quels scénarios de test** créer pour couvrir le maximum de code.

Un scénario de test, c'est une combinaison de données d'entrée qui fait emprunter au code un chemin spécifique. Par exemple :

- **Scénario TC_001** : un client de 35 ans avec un contrat vie actif → passe dans la branche `IF age >= 18` PUIS dans la branche `WHEN ("VIE")`
- **Scénario TC_002** : un client de 15 ans → passe dans la branche `ELSE` (mineur)
- **Scénario TC_003** : un client avec une date de naissance manquante → teste la gestion des missings

L'objectif est de trouver le **nombre minimal de scénarios** qui couvrent **le maximum de branches**.

---

### 📋 PROMPT 3.1 — Matrice de couverture et catalogue de scénarios

```text
Tu es un expert en stratégie de test et en couverture de code.

En utilisant :
- ./test-plan/03_analyse_branches.md (toutes les branches identifiées)
- ./test-plan/04_dictionnaire_donnees.json (structure des données)

Construis un plan de test qui atteint [SEUIL]% de couverture de branches.

1. MATRICE DE COUVERTURE (./test-plan/05_matrice_couverture.md) :

   Crée un tableau croisé où :
   - Chaque LIGNE est une branche (BR_xxx) identifiée en phase 2
   - Chaque COLONNE est un scénario de test (TC_xxx)
   - Une case contient "X" si le scénario active cette branche

   Exemple :
   | Branche | TC_001 | TC_002 | TC_003 | TC_004 | TC_005 |
   |---------|--------|--------|--------|--------|--------|
   | BR_calc_001 (age >= 18 VRAI) | X | | | X | |
   | BR_calc_001 (age >= 18 FAUX) | | X | | | X |
   | BR_calc_002 (montant > 0 VRAI) | X | X | | | |
   | BR_calc_002 (montant > 0 FAUX) | | | X | X | |
   | BR_calc_003 (date missing) | | | | | X |

   À la fin du tableau, calcule :
   - Nombre total de branches
   - Nombre de branches couvertes
   - Pourcentage de couverture atteint
   - Liste des branches NON couvertes (le cas échéant)

2. CATALOGUE DE SCÉNARIOS (./test-plan/05_scenarios_test.json) :

   Pour chaque scénario, crée une entrée JSON détaillée :

   {
     "id": "TC_001",
     "titre": "Client majeur, contrat vie actif, montant positif",
     "description": "Teste le chemin nominal complet : un client adulte avec
                     un contrat vie valide et des montants positifs. C'est le
                     cas le plus courant en production.",
     "priorite": "P1",
     "type": "nominal",
     "branches_couvertes": ["BR_calc_001_VRAI", "BR_calc_002_VRAI", "BR_sql_001_VRAI"],
     "migration_focus": "Vérifier que le calcul d'âge avec INTCK('YEAR', ...) donne
                         le même résultat que relativedelta en Python",
     "preconditions": {
       "macro_variables": {
         "DATE_CALCUL": "31/12/2024",
         "ANNEE_EXERCICE": "2024"
       },
       "description": "Paramètres standard de fin d'exercice"
     },
     "input_dataframes": {
       "df_polices": {
         "description": "1 police vie active",
         "records": [
           {
             "num_police": "POL-0000000001",
             "date_effet": "2020-01-15",
             "type_contrat": "VIE",
             "montant_prime": 1500.50,
             "date_naissance_assure": "1985-03-15"
           }
         ]
       }
     },
     "expected_output": {
       "df_provisions": {
         "description": "Provision calculée pour le contrat",
         "source": "estimated_by_llm",
         "records": [
           {
             "num_police": "POL-0000000001",
             "provision_math": 45230.75,
             "statut_calcul": "OK"
           }
         ]
       }
     }
   }

3. TYPES DE SCÉNARIOS À INCLURE :

   a) P1 — Chemins nominaux (cas courants en production) :
      - Le cas standard que tout le monde connaît
      - Les 2-3 variantes les plus fréquentes
      - Ce sont les tests les plus importants

   b) P2 — Cas limites (boundary values) :
      - Valeurs aux frontières des conditions (juste en dessous, pile dessus, juste au-dessus)
      - Exemple : si le code teste "IF age >= 18", tester avec age = 17, 18, 19
      - Datasets vides (0 observations)
      - Un seul groupe pour FIRST./LAST.
      - Jointures sans correspondance

   c) P3 — Valeurs spéciales et erreurs :
      - Missings sur chaque variable utilisée dans une condition
      - Valeurs négatives, zéro, très grandes
      - Chaînes vides, avec espaces, caractères spéciaux
      - Dates extrêmes (01/01/1960, date future)
      - Doublons sur les clés de jointure

   d) Migration — Tests ciblant les pièges SAS → Python :
      - Missing dans un tri (vérifie na_position)
      - Missing dans une comparaison (vérifie que NaN < 0 est géré)
      - MERGE avec doublons vs pd.merge
      - RETAIN vs shift/cumsum
      - Arrondi SAS vs arrondi Python

4. OPTIMISATION :
   - Essaie de couvrir plusieurs branches par scénario quand c'est possible
     (un seul jeu de données qui passe dans plusieurs chemins)
   - Identifie le sous-ensemble MINIMAL de scénarios pour atteindre [SEUIL]%
   - Si certaines branches sont inatteignables (code mort, conditions
     mutuellement exclusives avec d'autres contraintes), liste-les
     séparément avec l'explication

Sauvegarde dans ./test-plan/05_matrice_couverture.md et ./test-plan/05_scenarios_test.json
```

`── Fin du prompt 3.1 ──`

---

---

# PHASE 4 — Générer les données de test en Python

---

## Ce que fait cette phase

C'est ici que l'on passe du plan à l'action. Claude va générer du code Python concret :

- Des **fixtures pytest** : des fonctions Python qui créent les DataFrames de test
- Des **factories** : des fonctions utilitaires pour créer facilement des lignes de données avec des valeurs par défaut
- Des **tests pytest** : des fonctions qui appellent votre code Python migré avec les données de test et vérifient les résultats
- Des **fichiers de données** exportés en CSV et Parquet pour une utilisation en dehors de pytest

### Qu'est-ce qu'une fixture ?

En SAS, pour créer des données de test, vous écrivez un DATA step :

```sas
DATA TEST.CLIENTS;
  LENGTH NOM $50;
  FORMAT DT_NAISSANCE DATE9.;
  NOM = "Dupont"; DT_NAISSANCE = '15MAR1985'd; MONTANT = 1500; OUTPUT;
  NOM = "Martin"; DT_NAISSANCE = '01JAN2010'd; MONTANT = 500; OUTPUT;
RUN;
```

L'équivalent Python avec pytest s'appelle une "fixture" :

```python
@pytest.fixture
def df_clients_test():
    return pd.DataFrame({
        "nom": ["Dupont", "Martin"],
        "dt_naissance": pd.to_datetime(["1985-03-15", "2010-01-01"]),
        "montant": [1500.0, 500.0],
    })
```

C'est exactement la même chose : on crée un jeu de données en mémoire. Simplement, pytest s'occupe de le préparer automatiquement avant chaque test.

---

### 📋 PROMPT 4.1 — Génération des fixtures et factories

```text
Tu es un expert Python/pandas spécialisé en test et migration SAS.

En utilisant :
- ./test-plan/04_dictionnaire_donnees.json (structure des données)
- ./test-plan/05_scenarios_test.json (scénarios de test)

Génère le code Python pour créer tous les DataFrames de test.

1. FACTORIES (./test-plan/tests/fixtures/factory.py) :

   Pour CHAQUE dataset d'entrée du projet, crée une paire de fonctions :

   a) Une fonction "make_[dataset]" qui crée UNE LIGNE avec des valeurs
      par défaut valides. Cela permet de créer rapidement des données
      en ne spécifiant que ce qui change :

      ```python
      def make_police(
          num_police: str = "POL-0000000001",
          date_effet: str = "2020-01-15",
          type_contrat: str = "VIE",
          montant_prime: float = 1500.50,
          date_naissance_assure: str = "1985-03-15",
          **overrides,
      ) -> dict:
          """
          Crée un dictionnaire représentant une ligne du dataset POLICES.

          Les valeurs par défaut correspondent au cas nominal (client majeur,
          contrat vie actif, montant positif). Modifiez uniquement les champs
          nécessaires pour votre scénario de test.

          Exemples :
              # Cas nominal
              make_police()

              # Client mineur
              make_police(date_naissance_assure="2010-06-15")

              # Montant manquant
              make_police(montant_prime=np.nan)
          """
          record = {
              "num_police": num_police,
              "date_effet": pd.to_datetime(date_effet),
              "type_contrat": type_contrat,
              "montant_prime": montant_prime,
              "date_naissance_assure": pd.to_datetime(date_naissance_assure),
          }
          record.update(overrides)
          return record
      ```

   b) Une fonction "make_[dataset]_df" qui crée un DataFrame typé
      à partir d'une liste de dictionnaires :

      ```python
      def make_polices_df(records: list[dict]) -> pd.DataFrame:
          """
          Crée un DataFrame POLICES correctement typé.

          Les types sont alignés sur le dictionnaire de données
          (./test-plan/04_dictionnaire_donnees.json) pour reproduire
          le comportement SAS.
          """
          df = pd.DataFrame(records)
          return df.astype({
              "num_police": "string",
              "type_contrat": "string",
              "montant_prime": "float64",
          })
      ```

   IMPORTANT sur le typage :
   - Utiliser float64 pour les numériques (comme SAS qui est tout en float 8 bytes)
   - Utiliser pd.StringDtype() ("string") pour les chaînes, PAS object
   - Utiliser datetime64[ns] pour les dates
   - Pour les entiers pouvant être missing, utiliser pd.Int64Dtype() ("Int64" avec majuscule)
   - Documenter dans un commentaire la correspondance avec le type SAS

2. FIXTURES PYTEST (./test-plan/tests/conftest.py) :

   Pour CHAQUE scénario de test, crée une fixture d'entrée ET une fixture
   de résultat attendu :

   ```python
   import pytest
   import pandas as pd
   import numpy as np
   from fixtures.factory import make_police, make_polices_df

   # ──────────────────────────────────────────────
   # TC_001 — Client majeur, contrat vie, chemin nominal
   # Branches couvertes : BR_calc_001_VRAI, BR_calc_002_VRAI
   # Migration focus : calcul d'âge INTCK vs relativedelta
   # ──────────────────────────────────────────────

   @pytest.fixture
   def input_polices_tc001():
       """Données d'entrée TC_001 : 1 police vie standard."""
       return make_polices_df([
           make_police(),  # valeurs par défaut = cas nominal
       ])

   @pytest.fixture
   def expected_provisions_tc001():
       """Résultat attendu TC_001 (estimé par Claude — à confirmer avec SAS)."""
       return pd.DataFrame({
           "num_police": pd.array(["POL-0000000001"], dtype="string"),
           "provision_math": pd.array([45230.75], dtype="float64"),
           "statut_calcul": pd.array(["OK"], dtype="string"),
       })

   # ──────────────────────────────────────────────
   # TC_002 — Client mineur (branche age < 18)
   # Branches couvertes : BR_calc_001_FAUX
   # Migration focus : gestion missing dans le calcul d'âge
   # ──────────────────────────────────────────────

   @pytest.fixture
   def input_polices_tc002():
       """Données d'entrée TC_002 : 1 police pour un client mineur."""
       return make_polices_df([
           make_police(date_naissance_assure="2012-06-15"),
       ])
   ```

   Remarque : les factories permettent de ne documenter que CE QUI CHANGE
   par rapport au cas nominal. C'est beaucoup plus lisible que de
   redéfinir toutes les colonnes à chaque test.

3. VALEURS DE TEST À INCLURE SYSTÉMATIQUEMENT :

   Pour chaque variable utilisée dans une condition, génère des données
   qui testent :

   | Catégorie | Exemples | Pourquoi |
   |-----------|----------|----------|
   | Valeur nominale | age=35, montant=1500 | Le cas courant |
   | Frontière basse | age=18 (pile sur le seuil) | Teste le >= vs > |
   | Juste en dessous | age=17 | Teste l'autre branche |
   | Juste au-dessus | age=19 | Confirme le comportement |
   | Zéro | montant=0 | Souvent un cas oublié |
   | Négatif | montant=-100 | Teste les gardes |
   | Missing | montant=NaN, nom=None | Piège n°1 de migration |
   | Très grand | montant=9999999999 | Overflow potentiel |
   | Chaîne vide | nom="" | Différent de missing en SAS |
   | Espaces | nom="   " | SAS padde les chaînes |
   | Date extrême | date="1960-01-01" | Epoch SAS |
   | Date missing | date=NaT | Piège migration |

4. EXPORT EN FICHIERS (./test-plan/tests/data/) :

   Crée un script export_test_data.py qui exporte TOUS les DataFrames
   de test en :
   - Parquet (préserve les types — format recommandé)
   - CSV (lisible par tous, mais perd les types)

   Et crée un loader.py pour recharger facilement :
   ```python
   def load_input(tc_id: str, dataset: str) -> pd.DataFrame:
       """Charge un DataFrame d'entrée depuis les fichiers Parquet."""
       ...

   def load_expected(tc_id: str, dataset: str) -> pd.DataFrame:
       """Charge un DataFrame de résultat attendu."""
       ...
   ```

Sauvegarde dans ./test-plan/tests/
```

`── Fin du prompt 4.1 ──`

---

### 📋 PROMPT 4.2 — Génération des tests pytest

```text
En utilisant :
- Les fixtures générées dans ./test-plan/tests/conftest.py
- Les scénarios de ./test-plan/05_scenarios_test.json

Crée les fichiers de test pytest pour CHAQUE unité migrable identifiée
en phase 1.

1. UN FICHIER DE TEST PAR MODULE PYTHON :
   ./test-plan/tests/test_[nom_module].py

   Structure de chaque fichier :

   ```python
   """
   Tests de migration pour : calcul_provisions.sas → calcul_provisions.py

   Ce fichier vérifie que le module Python migré produit exactement les
   mêmes résultats que le code SAS original pour tous les scénarios de test.

   Scénarios couverts : TC_001 à TC_012
   Couverture de branches visée : 95%
   """

   import pandas as pd
   import numpy as np
   import pytest
   from pandas.testing import assert_frame_equal


   class TestCalculProvisions:
       """Tests pour le module calcul_provisions (ex calcul_provisions.sas)."""

       # ── Chemin nominal ──────────────────────────────

       @pytest.mark.p1
       @pytest.mark.estimated_by_llm
       def test_tc001_contrat_vie_nominal(
           self, input_polices_tc001, expected_provisions_tc001
       ):
           """
           TC_001 — Client majeur, contrat vie actif, montant positif.

           C'est le cas le plus courant en production. Si ce test échoue,
           il y a un problème fondamental dans la migration.

           Branches couvertes :
             - BR_calc_001 (age >= 18 → VRAI)
             - BR_calc_002 (montant > 0 → VRAI)
             - BR_calc_003 (type_contrat = "VIE" → VRAI)

           Piège de migration vérifié :
             Le calcul d'âge utilise INTCK('YEAR', dt_naissance, &DATE_CALCUL)
             en SAS. En Python, vérifier que relativedelta donne le même résultat
             (attention aux anniversaires non encore passés dans l'année).
           """
           from [NOM_PACKAGE].calcul_provisions import calculer_provisions

           result = calculer_provisions(input_polices_tc001)

           assert_frame_equal(
               result.reset_index(drop=True),
               expected_provisions_tc001.reset_index(drop=True),
               check_dtype=True,
               check_exact=False,
               atol=1e-10,  # tolérance pour les différences d'arrondi SAS vs Python
           )
   ```

2. CLASSE DÉDIÉE AUX PIÈGES DE MIGRATION :

   Dans chaque fichier de test, ajoute une classe spécifique :

   ```python
   class TestMigrationTraps:
       """
       Tests ciblant les différences de comportement SAS vs Python.

       Ces tests ne correspondent pas à des scénarios métier mais à des
       pièges techniques de migration. Ils vérifient que le code Python
       gère correctement les cas où SAS et Python se comportent différemment.
       """

       @pytest.mark.migration_trap
       def test_missing_dans_comparaison(self, input_polices_tc_missing):
           """
           En SAS : IF montant > 0 est FAUX quand montant = .
                    car . (missing) est inférieur à 0.
           En Python : montant > 0 est FAUX quand montant = NaN,
                       MAIS pour une raison différente (NaN != anything).

           Le résultat est le même ICI, mais attention :
           IF montant < 0 serait VRAI en SAS (. < 0) et FAUX en Python (NaN < 0).

           Ce test vérifie que le code Python gère ce cas correctement.
           """
           ...

       @pytest.mark.migration_trap
       def test_merge_avec_doublons(self, input_polices_doublons, input_sinistres_doublons):
           """
           PIÈGE CRITIQUE : Comportement du MERGE SAS avec doublons.

           En SAS :
             DATA result;
               MERGE polices sinistres; BY num_police;
             RUN;
           Si polices a 2 lignes pour "POL-001" et sinistres a 3 lignes pour "POL-001",
           SAS fait un appariement SÉQUENTIEL : ligne 1 avec ligne 1, ligne 2 avec ligne 2,
           ligne 3 reprend les valeurs de la ligne 2 de polices (RETAIN implicite).

           En Python :
             pd.merge(polices, sinistres, on="num_police")
           Fait un produit CARTÉSIEN : 2 × 3 = 6 lignes.

           Le résultat est DIFFÉRENT. Ce test vérifie que la migration
           gère correctement ce cas.
           """
           ...

       @pytest.mark.migration_trap
       def test_tri_avec_missing(self):
           """
           En SAS : PROC SORT met les missings EN PREMIER.
           En pandas : sort_values() met les NaN EN DERNIER par défaut.

           Si un MERGE BY suit le tri, les résultats seront décalés.
           Utiliser : df.sort_values(by="col", na_position="first")
           """
           ...

       @pytest.mark.migration_trap
       def test_retain_accumulation(self, input_data_retain):
           """
           En SAS :
             DATA result;
               SET input; BY groupe;
               RETAIN cumul 0;
               IF FIRST.groupe THEN cumul = 0;
               cumul = cumul + montant;
             RUN;

           En Python, l'équivalent est :
             df["cumul"] = df.groupby("groupe")["montant"].cumsum()

           Ce test vérifie que les deux approches donnent le même résultat,
           y compris avec des missings dans montant (SAS : . + 100 = .
           alors que pandas : NaN + 100 = NaN avec cumsum, ce qui "casse"
           l'accumulation pour tout le reste du groupe).
           """
           ...

       @pytest.mark.migration_trap
       def test_first_last_processing(self, input_data_groups):
           """
           En SAS :
             DATA result;
               SET input; BY client_id;
               IF FIRST.client_id THEN nb_contrats = 0;
               nb_contrats + 1;
               IF LAST.client_id THEN OUTPUT;
             RUN;

           En Python :
             df.groupby("client_id").size().reset_index(name="nb_contrats")

           Attention : FIRST./LAST. dépend du TRI. Si les données ne sont
           pas triées par client_id, FIRST./LAST. donne des résultats
           incohérents en SAS (mais silencieusement !). Le test vérifie
           aussi ce cas.
           """
           ...

       @pytest.mark.migration_trap
       def test_arrondi_sas_vs_python(self):
           """
           SAS : ROUND(2.5, 1) = 3 (arrondi "away from zero")
           Python : round(2.5) = 2 (arrondi bancaire / "to even")

           Pour reproduire le comportement SAS en Python :
             from decimal import Decimal, ROUND_HALF_UP
             float(Decimal(str(2.5)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
           """
           ...

       @pytest.mark.migration_trap
       def test_chaines_paddees(self):
           """
           En SAS, une variable CHAR(10) contenant "ABC" est stockée comme
           "ABC       " (paddée de 7 espaces). Les comparaisons SAS ignorent
           le padding : "ABC" = "ABC       " est VRAI.

           En Python, "ABC" != "ABC       ". Il faut appliquer .str.strip()
           ou s'assurer que les données sont nettoyées à l'import.
           """
           ...
   ```

3. UTILITAIRE DE COMPARAISON (./test-plan/tests/helpers/comparison.py) :

   Crée une fonction assert_sas_equal() qui encapsule toutes les subtilités :

   ```python
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

       Cette fonction est l'équivalent de PROC COMPARE en SAS :
       elle identifie les différences entre le résultat obtenu et le résultat
       attendu, en gérant les subtilités de la migration.

       Paramètres :
       - float_tolerance : tolérance pour les comparaisons de nombres décimaux
         (SAS et Python peuvent arrondir différemment)
       - check_row_order : si False, trie les deux DataFrames avant de comparer
       - sort_by : colonnes de tri si check_row_order=False
       - strip_strings : applique .strip() sur les colonnes texte
         (SAS padde les chaînes avec des espaces)
       - check_dtypes : vérifie que les types sont identiques
       """
       ...
   ```

4. MARQUEURS PYTEST :

   Ajoute dans conftest.py les marqueurs pour filtrer les tests :

   ```python
   def pytest_configure(config):
       config.addinivalue_line("markers", "p1: chemin nominal — doit TOUJOURS passer")
       config.addinivalue_line("markers", "p2: cas limites — valeurs aux frontières")
       config.addinivalue_line("markers", "p3: gestion d'erreurs et valeurs spéciales")
       config.addinivalue_line("markers", "migration_trap: piège spécifique SAS vers Python")
       config.addinivalue_line("markers", "ground_truth: résultat validé par exécution SAS")
       config.addinivalue_line("markers", "estimated_by_llm: résultat estimé par Claude")
   ```

   Cela permet d'exécuter par exemple uniquement les tests P1 :
   ```bash
   pytest -m p1          # seulement les chemins nominaux
   pytest -m migration_trap  # seulement les pièges de migration
   pytest -m ground_truth    # seulement les tests validés par SAS
   ```

Sauvegarde dans ./test-plan/tests/
```

`── Fin du prompt 4.2 ──`

---

---

# PHASE 5 — Assembler le harnais de test

---

## Ce que fait cette phase

On assemble toutes les pièces pour que le tout fonctionne avec une seule commande. C'est l'équivalent d'un script SAS « maître » qui appelle tous les sous-programmes dans l'ordre et produit un rapport consolidé.

---

### 📋 PROMPT 5.1 — Configuration et outillage

```text
Crée la configuration complète pour exécuter les tests et mesurer
la couverture de code :

1. CONFIGURATION PYTEST (./test-plan/pyproject.toml) :

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
       "ground_truth: validé par SAS",
       "estimated_by_llm: estimé par Claude — à confirmer",
   ]
   addopts = [
       "--tb=short",
       "-v",
       "--strict-markers",
   ]

   [tool.coverage.run]
   source = ["[NOM_PACKAGE]"]
   branch = true

   [tool.coverage.report]
   fail_under = [SEUIL]
   show_missing = true
   precision = 2
   exclude_lines = [
       "pragma: no cover",
       "if __name__",
       "raise NotImplementedError",
   ]

   [tool.coverage.html]
   directory = "results/htmlcov"
   ```

2. MAKEFILE (./test-plan/Makefile) avec des commandes simples :

   ```makefile
   .PHONY: help test test-p1 test-migration coverage coverage-html export-data

   help:               ## Afficher cette aide
   	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | sort | \
   	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

   test:               ## Lancer TOUS les tests
   	pytest tests/ -v

   test-p1:            ## Lancer uniquement les tests nominaux (P1)
   	pytest tests/ -v -m p1

   test-p2:            ## Lancer les tests de cas limites (P2)
   	pytest tests/ -v -m p2

   test-migration:     ## Lancer les tests de pièges SAS→Python
   	pytest tests/ -v -m migration_trap

   test-confirmed:     ## Lancer uniquement les tests validés par SAS
   	pytest tests/ -v -m ground_truth

   test-unconfirmed:   ## Lister les tests non encore validés par SAS
   	pytest tests/ -v -m estimated_by_llm --collect-only

   coverage:           ## Mesurer la couverture de code (terminal)
   	pytest tests/ --cov=[NOM_PACKAGE] --cov-branch --cov-report=term-missing

   coverage-html:      ## Mesurer la couverture avec rapport HTML
   	pytest tests/ --cov=[NOM_PACKAGE] --cov-branch \
   	  --cov-report=html:results/htmlcov \
   	  --cov-report=json:results/coverage.json \
   	  --cov-report=term-missing
   	@echo ""
   	@echo "Rapport HTML : results/htmlcov/index.html"

   export-data:        ## Exporter les DataFrames en CSV et Parquet
   	python tests/data/export_test_data.py
   ```

3. SCRIPT DE DÉMARRAGE (./test-plan/README.md) :

   Rédige un README clair avec :
   - Prérequis (Python, packages)
   - Comment installer les dépendances
   - Comment lancer les tests (les 4-5 commandes make essentielles)
   - Comment lire le rapport de couverture
   - Comment ajouter un nouveau scénario de test
   - Comment passer du mode "estimated_by_llm" au mode "ground_truth"
   - Glossaire des termes pour les non-initiés

Sauvegarde dans ./test-plan/
```

`── Fin du prompt 5.1 ──`

---

---

# PHASE 6 — Mesurer, itérer, prouver

---

## Pourquoi cette phase est cruciale

Les phases 1 à 5 produisent des tests basés sur une analyse **théorique** du code par Claude. C'est un excellent point de départ, mais ce n'est pas une preuve.

La preuve vient de **pytest-cov** : un outil qui mesure, pendant l'exécution des tests, quelles lignes et quelles branches du code Python ont effectivement été exécutées. C'est une mesure objective, pas une estimation.

Le principe est simple :

1. On lance les tests avec la mesure de couverture
2. L'outil nous dit : « les lignes 45, 67-72, et 98 n'ont jamais été exécutées »
3. On donne cette information à Claude pour qu'il génère les tests manquants
4. On recommence jusqu'à atteindre le seuil cible

C'est cette **boucle** qui garantit une couverture réelle.

---

### 📋 PROMPT 6.1 — Outil de mesure et d'analyse des trous

```text
Crée un script Python qui mesure la couverture réelle et produit un rapport
exploitable pour combler les trous.

Crée ./test-plan/scripts/measure_coverage.py :

```python
"""
Script de mesure de couverture et d'analyse des trous.

Ce script :
1. Lance pytest avec la mesure de couverture (pytest-cov)
2. Analyse le rapport JSON pour identifier les lignes/branches non couvertes
3. Produit un fichier texte formaté pour être passé à Claude Code
   afin de générer les tests manquants

Utilisation :
    python scripts/measure_coverage.py

Sortie :
    ./results/coverage.json     — rapport brut
    ./results/htmlcov/          — rapport HTML navigable
    ./results/coverage_gaps.txt — trous formatés pour Claude
"""

import json
import subprocess
import sys
from pathlib import Path

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


def run_coverage() -> bool:
    """Lance pytest avec coverage. Retourne True si tous les tests passent."""
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "tests/",
            f"--cov=[NOM_PACKAGE]",
            "--cov-branch",
            "--cov-report=json:results/coverage.json",
            "--cov-report=html:results/htmlcov",
            "--cov-report=term-missing",
        ],
        capture_output=False,
    )
    return result.returncode == 0


def analyze_gaps() -> dict:
    """Analyse le rapport de couverture et extrait les trous."""
    coverage_file = RESULTS_DIR / "coverage.json"
    if not coverage_file.exists():
        print("ERREUR : pas de rapport de couverture. Lancez d'abord les tests.")
        sys.exit(1)

    data = json.loads(coverage_file.read_text())
    totals = data["totals"]
    gaps = {}

    for filename, file_data in data["files"].items():
        summary = file_data["summary"]
        missing_lines = file_data.get("missing_lines", [])
        missing_branches = file_data.get("missing_branches", [])

        if missing_lines or missing_branches:
            gaps[filename] = {
                "covered_percent": summary["percent_covered"],
                "missing_lines": missing_lines,
                "missing_branches": [
                    f"ligne {b[0]} → {'VRAI' if b[1] else 'FAUX'} jamais testée"
                    for b in missing_branches
                ],
                "total_statements": summary["num_statements"],
                "covered_statements": summary["covered_lines"],
            }

    return gaps, totals


def format_report(gaps: dict, totals: dict) -> str:
    """Formate le rapport pour être passé à Claude."""
    lines = [
        "RAPPORT DE COUVERTURE",
        "=" * 60,
        f"Couverture globale : {totals['percent_covered']:.1f}%",
        f"Lignes couvertes : {totals['covered_lines']} / {totals['num_statements']}",
        f"Branches couvertes : {totals.get('covered_branches', '?')} / {totals.get('num_branches', '?')}",
        "",
        "FICHIERS AVEC TROUS DE COUVERTURE :",
        "-" * 60,
    ]

    for filename, data in sorted(gaps.items()):
        lines.append(f"\nFichier : {filename}")
        lines.append(f"  Couverture : {data['covered_percent']:.1f}%")
        if data["missing_lines"]:
            lines.append(f"  Lignes non couvertes : {data['missing_lines']}")
        if data["missing_branches"]:
            for branch in data["missing_branches"]:
                lines.append(f"  Branche non couverte : {branch}")

    return "\n".join(lines)


if __name__ == "__main__":
    print("Lancement des tests avec mesure de couverture...\n")
    all_passed = run_coverage()

    print("\n\nAnalyse des trous de couverture...\n")
    gaps, totals = analyze_gaps()
    report = format_report(gaps, totals)

    report_path = RESULTS_DIR / "coverage_gaps.txt"
    report_path.write_text(report)

    print(report)
    print(f"\nRapport sauvegardé dans : {report_path}")
    print(f"Rapport HTML dans : results/htmlcov/index.html")

    if not all_passed:
        print("\n⚠ ATTENTION : certains tests ont échoué.")
```

Sauvegarde dans ./test-plan/scripts/
```

`── Fin du prompt 6.1 ──`

---

### 📋 PROMPT 6.2 — Combler les trous de couverture (à relancer en boucle)

> Ce prompt est **itératif** : vous le relancez après chaque mesure de couverture en y collant le rapport mis à jour, jusqu'à atteindre votre seuil.

```text
Tu es un expert en test Python et migration SAS.

Voici le rapport de couverture réelle de mon code Python migré
(produit par pytest-cov) :

--- DÉBUT DU RAPPORT ---
[COLLEZ ICI LE CONTENU DE ./test-plan/results/coverage_gaps.txt]
--- FIN DU RAPPORT ---

Mon seuil de couverture cible est de [SEUIL]%.

Pour CHAQUE fichier Python ayant des trous de couverture :

1. Lis le fichier Python source pour voir le code des lignes non couvertes
2. Lis le fichier SAS original correspondant pour comprendre la logique métier
3. Détermine quelles données d'entrée activeraient ces lignes/branches
4. Génère :
   a) Les nouvelles fixtures (DataFrames de test) dans conftest.py
   b) Les nouveaux tests pytest dans le fichier de test correspondant
   c) Mise à jour de la matrice de couverture

5. Pour chaque nouveau test, documente :
   - Quelles lignes/branches il couvre (celles du rapport)
   - Quel est le scénario fonctionnel
   - Si c'est un piège de migration SAS → Python

6. Si une ligne/branche est INATTEIGNABLE (code mort, condition impossible),
   ajoute un commentaire "# pragma: no cover" avec l'explication et
   liste-la dans le rapport.

CONTRAINTE : Chaque nouveau test doit couvrir AU MOINS une ligne ou branche
qui n'était pas couverte. Pas de tests redondants.

Après cette génération, je relancerai :
   make coverage
pour mesurer la nouvelle couverture, et je te redonnerai le rapport
si le seuil n'est pas encore atteint.
```

`── Fin du prompt 6.2 ──`

---

### 📋 PROMPT 6.3 (optionnel) — Mutation testing

> Ce prompt est optionnel mais très utile pour les modules critiques (calculs actuariels, provisions, etc.). Il vérifie que vos tests détectent réellement les bugs, pas juste qu'ils « passent dans le code ».

```text
La couverture de code mesure si chaque ligne est exécutée, mais pas si les
tests DÉTECTENT les erreurs. Le mutation testing résout ce problème.

Le principe : on modifie volontairement le code (ex : remplacer + par -,
changer > en >=, supprimer une ligne) et on vérifie qu'au moins un test
échoue. Si AUCUN test ne détecte la modification, les tests sont trop faibles.

Configure le mutation testing pour le projet :

1. Installe mutmut :
   pip install mutmut

2. Crée la configuration dans pyproject.toml :
   [tool.mutmut]
   paths_to_mutate = "[NOM_PACKAGE]/"
   tests_dir = "tests/"

3. Crée un script ./test-plan/scripts/mutation_test.py qui :
   - Lance mutmut sur les modules les plus critiques en priorité
   - Analyse les mutants survivants (= modifications non détectées)
   - Pour chaque mutant survivant, décrit :
     * Quelle modification a été faite
     * Dans quel fichier et à quelle ligne
     * Pourquoi aucun test ne l'a détectée
     * Quel test il faudrait ajouter pour le détecter

4. Ajoute au Makefile :
   mutation:          ## Lancer le mutation testing
   	mutmut run --paths-to-mutate=[NOM_PACKAGE]/
   	mutmut results

Exemple de résultat :
   "Mutant survivant : ligne 45 de provisions.py, changé >= en >.
    Aucun test ne couvre le cas où age == 18 exactement.
    → Ajouter un test avec age = 18 (valeur frontière)."

Cela révèle les tests qui passent "par chance" sans vérifier les bonnes choses.

Sauvegarde dans ./test-plan/scripts/
```

`── Fin du prompt 6.3 ──`

---

---

# PROMPT UNIQUE — Tout lancer en une seule commande

---

Si vous préférez ne pas exécuter chaque prompt individuellement, voici un méta-prompt qui demande à Claude Code d'exécuter les 7 phases séquentiellement.

> Remplacez les valeurs entre crochets avant de lancer.

### 📋 MÉTA-PROMPT — Workflow complet

```text
Tu es un expert senior en migration SAS → Python avec 15 ans d'expérience
en actuariat, qualité logicielle et couverture de code.

CONTEXTE :
Je migre un projet SAS vers Python (pandas/numpy). J'ai besoin de générer
un plan de test complet avec des DataFrames pandas de test (fixtures pytest)
qui garantissent une couverture de branches de [SEUIL]% sur le code SAS
source. Les tests serviront à valider que le code Python migré produit des
résultats identiques au SAS original.

PARAMÈTRES :
- Projet SAS source : [CHEMIN_DU_PROJET]
- Seuil de couverture cible : [SEUIL]%
- Nom du package Python cible : [NOM_PACKAGE]
- Accès à un environnement SAS : [OUI/NON]

EXÉCUTE LES PHASES SUIVANTES DANS L'ORDRE :

PHASE 0 — CAPTURE DE LA VÉRITÉ SAS
Si accès SAS = OUI :
  Génère les scripts SAS pour exécuter le code original avec les données
  de test et capturer les résultats réels (ground truth).
Si accès SAS = NON :
  Configure le mode dégradé avec marqueurs estimated_by_llm.

PHASE 1 — CARTOGRAPHIE
Inventaire complet du projet (fichiers, rôles, dépendances).
Graphe de dépendances avec ordre de migration recommandé.

PHASE 2 — ANALYSE STATIQUE
Analyse de chaque branche conditionnelle avec ID unique (BR_xxx).
Identification de tous les patterns SAS critiques pour la migration.
Dictionnaire de données avec mapping SAS → Python.

PHASE 3 — STRATÉGIE DE COUVERTURE
Matrice branches × scénarios de test.
Catalogue de scénarios (TC_xxx) avec priorité et focus migration.

PHASE 4 — GÉNÉRATION DES DATAFRAMES
Factories Python (make_xxx) avec valeurs par défaut.
Fixtures pytest pour chaque scénario.
Tests pytest avec assert_sas_equal.
Tests spécifiques aux pièges de migration.
Export en Parquet et CSV.

PHASE 5 — HARNAIS DE TEST
pyproject.toml, Makefile, README.
Utilitaire assert_sas_equal().
Script de mesure de couverture.

À chaque phase, sauvegarde les livrables dans ./test-plan/ et affiche
un résumé de ce qui a été produit avant de passer à la phase suivante.

À la fin, produis le fichier RAPPORT_FINAL.md avec :
- Résumé du projet analysé
- Statistiques (nb fichiers, branches, scénarios, couverture prévisionnelle)
- Pièges de migration identifiés
- Instructions d'exécution
- Limites et recommandations
```

`── Fin du méta-prompt ──`

---

---

# Arborescence complète des livrables

---

Voici ce que le dossier `test-plan/` contient à la fin du workflow :

```
test-plan/
│
├── 01_inventaire_projet.md          ← Phase 1 : inventaire de tous les fichiers SAS
├── 02_dependances.json              ← Phase 1 : graphe de dépendances (JSON)
├── 02_dependances.mmd               ← Phase 1 : graphe visuel (Mermaid)
├── 03_analyse_branches.md           ← Phase 2 : toutes les branches (BR_xxx)
├── 04_dictionnaire_donnees.json     ← Phase 2 : structure des données SAS → Python
├── 05_matrice_couverture.md         ← Phase 3 : quels tests couvrent quelles branches
├── 05_scenarios_test.json           ← Phase 3 : catalogue des scénarios (TC_xxx)
│
├── pyproject.toml                   ← Phase 5 : configuration pytest + coverage
├── Makefile                         ← Phase 5 : commandes simplifiées (make test, etc.)
├── README.md                        ← Phase 5 : guide de démarrage
├── RAPPORT_FINAL.md                 ← Rapport de synthèse
│
├── sas_runner/                      ← Phase 0 : harnais d'exécution SAS
│   ├── setup_test_env.sas
│   ├── capture_results.sas
│   ├── run_scenario.sas
│   ├── collect_ground_truth.py
│   ├── input/TC_001/...
│   └── output/TC_001/...
│
├── tests/                           ← Phases 4 & 5 : code de test Python
│   ├── conftest.py                  ← Fixtures partagées + marqueurs
│   ├── fixtures/
│   │   ├── factory.py               ← Fonctions make_xxx (création de données)
│   │   ├── fixture_polices.py
│   │   └── fixture_sinistres.py
│   ├── helpers/
│   │   └── comparison.py            ← assert_sas_equal()
│   ├── data/
│   │   ├── loader.py                ← Utilitaire de chargement
│   │   ├── export_test_data.py      ← Script d'export
│   │   ├── parquet/                 ← DataFrames en Parquet (types préservés)
│   │   ├── csv/                     ← DataFrames en CSV (lisible par tous)
│   │   └── ground_truth/            ← Résultats réels du SAS (Phase 0)
│   ├── test_calcul_provisions.py    ← Tests par module
│   ├── test_chargement_donnees.py
│   └── test_migration_traps.py      ← Tests des pièges SAS → Python
│
├── scripts/                         ← Phase 6 : outillage
│   ├── measure_coverage.py          ← Mesure + analyse des trous
│   ├── mutation_test.py             ← Mutation testing (optionnel)
│   └── upgrade_to_ground_truth.py   ← Remplacement estimations → résultats réels
│
└── results/                         ← Résultats d'exécution
    ├── coverage.json
    ├── coverage_gaps.txt
    └── htmlcov/index.html           ← Rapport de couverture navigable
```

---

---

# Résumé : les 3 niveaux de confiance

---

| Niveau | Ce qu'on fait | Confiance | Quand l'utiliser |
|--------|---------------|-----------|------------------|
| **Bronze** | Phases 1 à 5 seules (sans SAS, sans mesure réelle) | Moyenne — couverture théorique, résultats estimés | Début de migration, pas d'accès SAS, débroussaillage |
| **Argent** | Phases 1 à 6 (avec mesure pytest-cov, sans SAS) | Bonne — couverture mesurée, résultats estimés | Migration en cours, code Python écrit, pas d'accès SAS |
| **Or** | Phases 0 à 6 (avec résultats SAS réels + mesure pytest-cov) | Excellente — couverture mesurée ET résultats vérifiés | Validation finale avant mise en production |

L'objectif est d'atteindre le niveau **Or** pour les modules critiques (calculs actuariels, provisions, etc.) et le niveau **Argent** minimum pour le reste.
