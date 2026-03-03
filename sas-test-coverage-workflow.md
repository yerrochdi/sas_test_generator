# Workflow Claude Code — Génération de Tests et Couverture de Code SAS

## Vue d'ensemble

Ce document fournit un workflow complet de prompts à exécuter séquentiellement dans **Claude Code** pour analyser un projet SAS cloné localement et générer automatiquement des datasets de test garantissant une couverture de code maximale.

---

## Prérequis

Avant de lancer le workflow, assurez-vous que :

- Le projet SAS est cloné localement dans un dossier accessible
- Claude Code est installé et configuré
- Vous connaissez le chemin absolu vers la racine du projet

---

## Phase 1 — Cartographie du projet

### Prompt 1.1 : Découverte et inventaire

```
Tu es un expert SAS senior spécialisé en audit de code et en ingénierie de test.

Analyse le projet SAS situé dans : [CHEMIN_DU_PROJET]

Effectue les actions suivantes :
1. Parcours récursivement tous les fichiers (.sas, .egp, .sas7bdat, .sd2, .cfg, etc.)
2. Produis un inventaire structuré au format markdown avec :
   - L'arborescence complète du projet
   - Pour chaque fichier .sas : son rôle probable (programme principal, macro, include, format, autoexec, etc.)
   - Les dépendances entre fichiers (appels %include, %macro/%mend, libname, filename)
3. Identifie le ou les points d'entrée du projet (programme(s) principal/aux)
4. Liste toutes les bibliothèques (libname) et leurs chemins
5. Identifie les sources de données externes (fichiers CSV, Excel, bases de données, API)

Sauvegarde le résultat dans ./test-plan/01_inventaire_projet.md
```

### Prompt 1.2 : Extraction du graphe de dépendances

```
En te basant sur l'inventaire produit dans ./test-plan/01_inventaire_projet.md,
construis le graphe de dépendances complet du projet :

1. Crée un fichier JSON ./test-plan/02_dependances.json contenant :
   - Pour chaque programme/macro : ses entrées (datasets lus), ses sorties (datasets créés), ses appels de macros, ses %include
   - L'ordre d'exécution logique (topological sort)

2. Crée un diagramme Mermaid ./test-plan/02_dependances.mmd montrant :
   - Les flux de données entre programmes
   - Les macros et leurs invocations
   - Les datasets intermédiaires et finaux

3. Identifie les "clusters" fonctionnels : groupes de programmes qui forment une unité logique
```

---

## Phase 2 — Analyse statique du code

### Prompt 2.1 : Analyse des branches et chemins d'exécution

```
Tu es un expert en analyse statique de code SAS et en couverture de test.

Pour CHAQUE fichier .sas du projet situé dans [CHEMIN_DU_PROJET], effectue une analyse
statique exhaustive et documente :

1. **Branches conditionnelles** :
   - Tous les IF/THEN/ELSE, SELECT/WHEN/OTHERWISE
   - Les WHERE clauses dans les DATA steps et PROC SQL
   - Les conditions dans les boucles %DO %WHILE, %DO %UNTIL
   - Les %IF/%THEN/%ELSE dans les macros

2. **Chemins d'exécution** :
   - Nombre de chemins distincts par programme/macro
   - Conditions nécessaires pour activer chaque chemin (valeurs de variables, paramètres de macros)
   - Chemins nominaux vs chemins d'erreur/exception

3. **Points de complexité** :
   - Boucles imbriquées (DO, %DO)
   - RETAIN, LAG, DIF (logique dépendante de l'état)
   - Merge avec conditions (IN=)
   - FIRST./LAST. processing
   - Array processing
   - Expressions régulières (PRX functions)
   - Formats/Informats personnalisés
   - Hash objects

4. **Macros-variables et paramètres** :
   - Toutes les macro-variables (%LET, %GLOBAL, %LOCAL, &sysparm, paramètres de macros)
   - Leurs valeurs possibles et l'impact sur le flux d'exécution
   - Les valeurs par défaut vs les valeurs qui déclenchent des branches alternatives

Sauvegarde dans ./test-plan/03_analyse_branches.md avec un tableau récapitulatif par fichier.
```

### Prompt 2.2 : Analyse des structures de données requises

```
En te basant sur l'analyse des branches (./test-plan/03_analyse_branches.md)
et le graphe de dépendances (./test-plan/02_dependances.json), analyse les
structures de données :

1. Pour chaque dataset lu en entrée par le projet, documente :
   - Nom du dataset et bibliothèque
   - Liste des variables utilisées (nom, type attendu : char/num, longueur, format)
   - Contraintes implicites (NOT NULL, plages de valeurs, patterns)
   - Relations entre datasets (clés de jointure, merge BY variables)

2. Crée un "dictionnaire de données" ./test-plan/04_dictionnaire_donnees.json avec le schéma :
   ```json
   {
     "datasets": [
       {
         "name": "NOM_DATASET",
         "library": "LIBNAME",
         "used_by": ["programme1.sas", "macro_x"],
         "variables": [
           {
             "name": "VAR1",
             "type": "num|char",
             "length": 8,
             "format": "$10.",
             "constraints": "NOT NULL, > 0",
             "used_in_conditions": ["IF VAR1 > 100", "WHERE VAR1 IS NOT MISSING"],
             "boundary_values": [0, 100, null]
           }
         ],
         "relationships": [
           { "target": "AUTRE_DATASET", "join_keys": ["KEY1", "KEY2"], "type": "merge|sql_join" }
         ]
       }
     ]
   }
   ```

Sauvegarde le résultat dans ./test-plan/04_dictionnaire_donnees.json
```

---

## Phase 3 — Stratégie de couverture

### Prompt 3.1 : Matrice de couverture et scénarios de test

```
Tu es un expert en test logiciel et couverture de code SAS.

En utilisant :
- ./test-plan/03_analyse_branches.md (branches et chemins)
- ./test-plan/04_dictionnaire_donnees.json (structure des données)

Construis une stratégie de couverture complète :

1. **Matrice de couverture** (fichier ./test-plan/05_matrice_couverture.md) :
   - Ligne = chaque branche/chemin identifié dans l'analyse
   - Colonnes = ID du scénario de test qui couvre cette branche
   - Objectif : couverture de [SEUIL]% (par défaut 100%)

2. **Catalogue de scénarios de test** avec pour chaque scénario :
   - ID unique (TC_001, TC_002, ...)
   - Description fonctionnelle (ce qu'on teste)
   - Branches couvertes (références aux IDs de l'analyse)
   - Préconditions (valeurs de macro-variables, paramètres)
   - Données d'entrée nécessaires (quels datasets, quelles caractéristiques)
   - Résultat attendu (dataset de sortie, valeurs clés, messages dans le log)

3. **Priorisation** :
   - Classe les scénarios par priorité (P1 = chemin nominal, P2 = cas limites, P3 = erreurs)
   - Identifie le sous-ensemble minimal de scénarios pour atteindre le seuil demandé
   - Indique les branches non couvrables (code mort, chemins impossibles) et pourquoi

4. **Rapport de couverture prévisionnelle** :
   - Couverture des instructions (statement coverage)
   - Couverture des branches (branch coverage)
   - Couverture des conditions (condition coverage)
   - Couverture des chemins (path coverage) si faisable

Sauvegarde dans ./test-plan/05_matrice_couverture.md et ./test-plan/05_scenarios_test.json
```

---

## Phase 4 — Génération des datasets de test

### Prompt 4.1 : Génération des données

```
Tu es un expert SAS en génération de données de test.

En utilisant :
- ./test-plan/04_dictionnaire_donnees.json
- ./test-plan/05_scenarios_test.json

Génère les datasets de test sous forme de programmes SAS :

1. Crée un fichier SAS par scénario de test dans ./test-plan/datasets/ :
   - Nom : TC_XXX_create_data.sas
   - Chaque fichier crée les datasets nécessaires via DATA steps
   - Les données doivent respecter le dictionnaire (types, longueurs, formats)
   - Inclure des commentaires expliquant le but de chaque observation

2. Stratégie de génération des valeurs :
   - **Valeurs limites** : min, max, min-1, max+1 pour les numériques
   - **Valeurs spéciales** : missing (. et ""), 0, négatifs, très grands nombres
   - **Chaînes** : vide, espaces, caractères spéciaux, longueur max, troncature
   - **Dates** : limites SAS, formats variés, dates invalides
   - **Combinatoires** : pairwise testing pour les interactions entre variables
   - **Jointures** : observations avec/sans correspondance (inner, left, right, full)
   - **Tri** : données triées, non triées, doublons sur les clés BY

3. Pour chaque dataset généré, ajoute en commentaire :
   - Scénario(s) couvert(s)
   - Branches activées
   - Résultat attendu

4. Crée un fichier maître ./test-plan/datasets/00_run_all_datasets.sas qui :
   - Définit les libnames nécessaires
   - Exécute tous les TC_XXX_create_data.sas dans l'ordre
   - Vérifie que chaque dataset a été créé correctement (PROC CONTENTS + obs count)

Exemple de structure attendue pour un dataset :

   data TEST.INPUT_CLIENTS;
     length CLIENT_ID 8 NOM $50 DATE_NAISSANCE 8 MONTANT 8;
     format DATE_NAISSANCE DATE9. MONTANT COMMA12.2;

     /* TC_001 - Chemin nominal : client majeur avec montant positif */
     CLIENT_ID=1; NOM="Dupont"; DATE_NAISSANCE='15MAR1985'd; MONTANT=1500.50; output;

     /* TC_002 - Limite : client mineur (branche IF age < 18) */
     CLIENT_ID=2; NOM="Martin"; DATE_NAISSANCE='01JAN2010'd; MONTANT=500; output;

     /* TC_003 - Valeur manquante sur NOM (branche IF MISSING(NOM)) */
     CLIENT_ID=3; NOM=""; DATE_NAISSANCE='20JUL1990'd; MONTANT=0; output;

     /* TC_004 - Montant négatif (branche ELSE IF MONTANT < 0) */
     CLIENT_ID=4; NOM="Durand"; DATE_NAISSANCE='05DEC1978'd; MONTANT=-200; output;
   run;
```

### Prompt 4.2 : Génération des résultats attendus

```
En utilisant les datasets de test générés dans ./test-plan/datasets/ et le code
source du projet, détermine les résultats attendus :

1. Pour chaque scénario de test, trace manuellement l'exécution du code SAS
   avec les données de test et détermine :
   - Les datasets de sortie attendus (avec les valeurs exactes)
   - Les messages attendus dans le log (NOTES, WARNINGS, ERRORS)
   - Les fichiers de sortie attendus (rapports, exports)

2. Crée les datasets de référence dans ./test-plan/expected/ :
   - TC_XXX_expected_OUTPUT.sas : DATA steps créant les résultats attendus

3. Crée un fichier de validation ./test-plan/expected/assertions.json :
   ```json
   {
     "TC_001": {
       "output_datasets": {
         "WORK.RESULT": {
           "obs_count": 1,
           "key_values": { "CLIENT_ID": 1, "STATUT": "VALIDE", "SCORE": 85.5 }
         }
       },
       "log_checks": {
         "errors": 0,
         "warnings": 0,
         "notes_contain": ["1 observations"]
       }
     }
   }
   ```

Sauvegarde dans ./test-plan/expected/
```

---

## Phase 5 — Harnais de test et exécution

### Prompt 5.1 : Création du harnais de test

```
Crée un framework d'exécution de test SAS complet :

1. Fichier principal ./test-plan/run_tests.sas qui :
   - Accepte un paramètre &SEUIL_COUVERTURE (défaut 100)
   - Accepte un paramètre &SCENARIOS (défaut ALL, ou liste TC_001 TC_002 ...)
   - Pour chaque scénario :
     a. Initialise un environnement propre (libnames temporaires)
     b. Exécute le script de création de données de test
     c. Exécute le programme SAS cible
     d. Compare les résultats obtenus vs attendus (PROC COMPARE)
     e. Vérifie le log (0 erreurs inattendues)
     f. Enregistre le résultat PASS/FAIL

2. Macro utilitaire ./test-plan/macros/test_utils.sas contenant :
   - %ASSERT_EQUAL(ds1, ds2) : compare deux datasets
   - %ASSERT_OBS_COUNT(ds, expected) : vérifie le nombre d'observations
   - %ASSERT_VALUE(ds, where, var, expected) : vérifie une valeur précise
   - %CHECK_LOG(expected_errors, expected_warnings) : vérifie le log
   - %REPORT_RESULT(tc_id, status, details) : enregistre le résultat

3. Rapport de test ./test-plan/results/test_report.sas qui :
   - Agrège tous les résultats
   - Calcule la couverture atteinte vs le seuil
   - Produit un rapport HTML avec :
     * Résumé exécutif (nb tests, pass, fail, couverture)
     * Détail par scénario
     * Branches non couvertes
     * Recommandations

Sauvegarde dans ./test-plan/
```

### Prompt 5.2 : Validation et rapport final

```
Effectue une dernière vérification de cohérence sur l'ensemble du plan de test :

1. **Vérification de complétude** :
   - Chaque branche identifiée en Phase 2 est-elle couverte par au moins un scénario ?
   - Chaque scénario a-t-il un dataset de test ET un résultat attendu ?
   - Le harnais de test peut-il exécuter tous les scénarios ?

2. **Vérification de cohérence** :
   - Les types/formats des datasets de test correspondent au dictionnaire ?
   - Les clés de jointure sont cohérentes entre datasets liés ?
   - Les résultats attendus sont-ils réalistes par rapport au code ?

3. **Rapport final** ./test-plan/RAPPORT_FINAL.md contenant :
   - Résumé du projet analysé
   - Statistiques : nb fichiers, nb branches, nb scénarios, couverture prévisionnelle
   - Liste des fichiers générés avec leur rôle
   - Instructions d'exécution pas à pas
   - Limites et recommandations (code non testable, dépendances externes, etc.)
   - Prochaines étapes suggérées

4. Crée un script ./test-plan/QUICK_START.sh qui :
   - Vérifie les prérequis (SAS disponible, chemins valides)
   - Copie les datasets de test aux bons emplacements
   - Lance l'exécution complète
   - Ouvre le rapport de résultats
```

---

## Utilisation rapide

Pour lancer le workflow complet en une seule commande dans Claude Code, utilisez ce méta-prompt :

```
Tu es un expert SAS senior avec 15 ans d'expérience en qualité logicielle,
test automatisé et couverture de code.

Mon projet SAS se trouve dans : [CHEMIN_DU_PROJET]
Seuil de couverture cible : [SEUIL]% (défaut 100%)

Exécute séquentiellement les 5 phases du workflow de test définies dans
./sas-test-coverage-workflow.md :
1. Cartographie du projet
2. Analyse statique du code
3. Stratégie de couverture
4. Génération des datasets de test
5. Harnais de test et exécution

À chaque phase, sauvegarde les livrables dans ./test-plan/ et confirme
avant de passer à la phase suivante.

À la fin, produis le RAPPORT_FINAL.md et le QUICK_START.sh.
```

---

## Arborescence finale attendue

```
test-plan/
├── 01_inventaire_projet.md
├── 02_dependances.json
├── 02_dependances.mmd
├── 03_analyse_branches.md
├── 04_dictionnaire_donnees.json
├── 05_matrice_couverture.md
├── 05_scenarios_test.json
├── datasets/
│   ├── 00_run_all_datasets.sas
│   ├── TC_001_create_data.sas
│   ├── TC_002_create_data.sas
│   └── ...
├── expected/
│   ├── assertions.json
│   ├── TC_001_expected.sas
│   └── ...
├── macros/
│   └── test_utils.sas
├── results/
│   └── test_report.sas
├── run_tests.sas
├── RAPPORT_FINAL.md
└── QUICK_START.sh
```

---

## Conseils d'utilisation

**Ajuster le seuil** : Si 100% est irréaliste (code mort, dépendances externes inaccessibles), commencez par 80% et augmentez progressivement.

**Projets volumineux** : Pour les projets avec plus de 50 fichiers .sas, exécutez les phases 1 et 2 d'abord, puis lancez les phases 3-5 par cluster fonctionnel identifié en phase 1.

**Itérer** : Après une première exécution, analysez les branches non couvertes et relancez la phase 3 avec un focus sur ces branches spécifiques.

**Macro-variables dynamiques** : Si le projet utilise des macro-variables résolues à l'exécution (ex: dates système, paramètres d'environnement), documentez leurs valeurs typiques dans un fichier de configuration que vous passerez en contexte à Claude Code.
