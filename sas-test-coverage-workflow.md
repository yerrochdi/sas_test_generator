Historique étape par étape

Harnais SAS de référence
Mise en place de l’exécution isolée SAS + capture outputs + conversion ground truth.
Livrables: setup_test_env.sas, capture_results.sas, run_scenario.sas, collect_ground_truth.py.
Mode dégradé sans SAS
Ajout de la stratégie duale estimated_by_llm vs ground_truth avec promotion automatique.
Livrables: conftest.py, upgrade_to_ground_truth.py.
Inventaire projet SAS
Scan complet du périmètre et synthèse de structure/macro-flux.
Livrable: 01_inventaire_projet.md.
Dépendances + ordre de migration
Graphe dépendances (JSON + Mermaid) et plan d’ordre de migration.
Livrables: 02_dependances.json, 02_dependances.mmd, 02_ordre_migration_recommande.md.
Analyse exhaustive des branches
Catalogage des branches BR_* et patterns critiques SAS→Python.
Livrable: 03_analyse_branches.md.
Dictionnaire de données
Génération JSON des datasets/variables/types/relations (base de factory pandas).
Livrable: 04_dictionnaire_donnees.json.
Plan de test couverture
Matrice BR x TC + catalogue scénarios test.
Livrables: 05_matrice_couverture.md, 05_scenarios_test.json.
Factories + fixtures + export/loader
Génération DataFrames typés pour tous les datasets + fixtures TC + export CSV/Parquet + loader.
Livrables: factory.py, scenario_data.py, export_test_data.py, loader.py.
Tests pytest par unité migrable
Création d’un fichier de test par module cible + classe migration traps partagée.
Exemples: test_pipeline_sinapps.py, migration_traps.py, comparison.py.
Configuration exécution/couverture
Ajout configuration pytest/coverage, commandes Makefile et guide d’exécution.
Livrables: pyproject.toml, Makefile, README.md.
Script de mesure des trous
Création du script qui lance pytest-cov, analyse les gaps et produit un rapport actionnable.
Livrable: measure_coverage.py.
Stabilisation des tests migration_trap
Correction du cas missing qui échouait partout + fixtures dédiées.
Fichiers mis à jour: migration_traps.py, conftest.py, 05_matrice_couverture.md.
Constat actuel
Les tests tournent, mais la couverture métier reste non exploitable: package cible non importé, donc 0 donnée instrumentée.
Diagnostic visible dans coverage_gaps.txt et coverage_run.log.
Si tu veux, prochaine étape immédiate: je reconfigure automatiquement la cible coverage/imports vers le vrai package Python migré pour obtenir un coverage.json réel et ensuite combler les trous ligne par ligne.

GPT-5.3-Codex • 1x
