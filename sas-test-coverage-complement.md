# Compléments au workflow — Garantir une couverture réelle

Ces phases s'ajoutent au workflow principal pour transformer la couverture
"théorique" en couverture **mesurée et vérifiée**.

---

## Phase 0 — Capturer la vérité SAS (AVANT la migration)

> C'est la phase la plus importante. Sans elle, les "expected outputs"
> sont des suppositions de Claude, pas des faits.

### Prompt 0.1 : Générer un harnais d'exécution SAS

```
Tu es un expert SAS. En utilisant l'inventaire du projet dans [CHEMIN_DU_PROJET] :

1. Crée un programme SAS ./test-plan/sas_runner/run_and_capture.sas qui :
   - Prend en entrée un répertoire de datasets de test (CSV ou SAS7BDAT)
   - Exécute le code SAS original avec ces données d'entrée
   - Capture TOUS les datasets de sortie et les exporte en CSV
     (PROC EXPORT ou DATA step avec PUT)
   - Capture le log complet dans un fichier .log
   - Exporte les métadonnées de chaque dataset (PROC CONTENTS → CSV)

2. Le script doit :
   - Rediriger les libnames pour pointer vers les données de test
   - Isoler l'exécution (WORK temporaire, pas d'effets de bord)
   - Gérer les erreurs gracieusement (OPTIONS NOSYNTAXCHECK NOERRORABEND)

3. Crée ./test-plan/sas_runner/export_results.sas :
   ```sas
   /* Pour chaque dataset de sortie, exporter en CSV avec types explicites */
   proc export data=WORK.RESULT
     outfile="./results/TC_001_result.csv"
     dbms=csv replace;
   run;

   /* Exporter aussi les métadonnées pour vérifier les types */
   proc contents data=WORK.RESULT out=WORK._META noprint; run;
   proc export data=WORK._META
     outfile="./results/TC_001_result_meta.csv"
     dbms=csv replace;
   run;
   ```

4. Crée un script Python ./test-plan/sas_runner/collect_ground_truth.py qui :
   - Lit les CSV exportés par SAS
   - Les convertit en DataFrames pandas avec les types corrects
   - Les sauvegarde en Parquet dans ./test-plan/tests/data/ground_truth/
   - Ce sont ces Parquet qui servent de "expected" dans les tests,
     PAS les résultats tracés manuellement par Claude

L'idée : on fait tourner le SAS original UNE FOIS avec chaque jeu de données
de test, et on capture les vrais résultats. Ces résultats deviennent
la source de vérité pour pytest.
```

### Prompt 0.2 : Workflow avec/sans accès SAS

```
Selon la disponibilité d'un environnement SAS :

**CAS A — Accès SAS disponible** (recommandé) :
1. Claude génère les DataFrames de test (Phase 4 du workflow principal)
2. On les exporte en CSV/SAS7BDAT
3. On exécute le code SAS original avec ces données → résultats réels
4. On importe les résultats réels comme "expected" dans pytest
→ Couverture VÉRIFIÉE par exécution réelle

**CAS B — Pas d'accès SAS** (dégradé) :
1. Claude génère les DataFrames de test
2. Claude trace manuellement les résultats attendus
3. On marque ces tests comme "expected_by_llm" (non vérifié)
4. Dès qu'un environnement SAS est disponible, on lance la vérification
→ Couverture THÉORIQUE, à confirmer

Crée dans ./test-plan/tests/conftest.py un marqueur :

   ```python
   import pytest

   def pytest_configure(config):
       config.addinivalue_line(
           "markers",
           "ground_truth: expected vient d'une exécution SAS réelle"
       )
       config.addinivalue_line(
           "markers",
           "expected_by_llm: expected tracé par Claude, non vérifié par SAS"
       )
   ```

Ainsi on sait toujours quels tests sont fiables et lesquels sont à confirmer.
```

---

## Phase 6 — Mesure réelle de la couverture et boucle de rétroaction

### Prompt 6.1 : Mesurer la couverture Python réelle

```
Configure la mesure de couverture réelle sur le code Python migré :

1. Ajoute au pyproject.toml :
   ```toml
   [tool.coverage.run]
   source = ["mon_projet"]
   branch = true          # Couverture de branches, pas juste de lignes

   [tool.coverage.report]
   fail_under = [SEUIL]
   show_missing = true
   exclude_lines = [
       "pragma: no cover",
       "if __name__",
       "raise NotImplementedError",
   ]

   [tool.coverage.html]
   directory = "./test-plan/results/htmlcov"
   ```

2. Crée ./test-plan/scripts/measure_coverage.py :

   ```python
   """
   Mesure la couverture réelle et identifie les trous.
   Produit un rapport JSON exploitable par Claude pour générer
   des tests complémentaires.
   """
   import json
   import subprocess
   from pathlib import Path

   def run_coverage():
       """Lance pytest avec coverage et retourne le rapport."""
       subprocess.run([
           "pytest", "tests/",
           "--cov=mon_projet",
           "--cov-branch",
           "--cov-report=json:results/coverage.json",
           "--cov-report=html:results/htmlcov",
           "--cov-report=term-missing",
       ], check=True)

   def extract_gaps(coverage_json: Path) -> dict:
       """Extrait les lignes et branches non couvertes."""
       data = json.loads(coverage_json.read_text())
       gaps = {}
       for filename, file_data in data["files"].items():
           missing = file_data.get("missing_lines", [])
           missing_branches = file_data.get("missing_branches", [])
           if missing or missing_branches:
               gaps[filename] = {
                   "missing_lines": missing,
                   "missing_branches": missing_branches,
                   "covered_percent": file_data["summary"]["percent_covered"],
               }
       return gaps

   def format_for_claude(gaps: dict) -> str:
       """Formate les trous de couverture pour que Claude génère
       les tests manquants."""
       prompt_parts = []
       for filename, data in gaps.items():
           prompt_parts.append(
               f"Fichier: {filename}\n"
               f"  Couverture: {data['covered_percent']:.1f}%\n"
               f"  Lignes manquantes: {data['missing_lines']}\n"
               f"  Branches manquantes: {data['missing_branches']}\n"
           )
       return "\n".join(prompt_parts)

   if __name__ == "__main__":
       run_coverage()
       gaps = extract_gaps(Path("results/coverage.json"))
       report = format_for_claude(gaps)
       Path("results/coverage_gaps.txt").write_text(report)
       print(f"\n{'='*60}")
       print(f"TROUS DE COUVERTURE ({len(gaps)} fichiers)")
       print(f"{'='*60}")
       print(report)
   ```

3. Ajoute au Makefile :
   ```makefile
   coverage:          ## Mesurer la couverture réelle
   	python scripts/measure_coverage.py

   coverage-html:     ## Ouvrir le rapport HTML
   	open results/htmlcov/index.html
   ```
```

### Prompt 6.2 : Boucle de rétroaction — combler les trous

```
C'est le prompt le plus important pour garantir la couverture.
Il doit être relancé ITÉRATIVEMENT jusqu'à atteindre le seuil.

Voici le rapport de couverture réelle de mon code Python migré :

[COLLER ICI LE CONTENU DE ./test-plan/results/coverage_gaps.txt]

Pour chaque fichier Python listé avec une couverture insuffisante :

1. Lis le fichier Python ET le fichier SAS source correspondant
2. Identifie les lignes/branches non couvertes
3. Détermine quelles données d'entrée activeraient ces branches
4. Génère les DataFrames de test manquants (nouvelles fixtures)
5. Génère les tests pytest correspondants
6. Ajoute-les aux fichiers existants dans ./test-plan/tests/

Contraintes :
- Chaque nouveau test doit couvrir AU MOINS une branche manquante
- Documente quelle branche/ligne chaque test cible
- Si une branche est inatteignable (code mort), marque-la avec
  "# pragma: no cover" et justifie dans le rapport

Après génération, je relancerai `make coverage` pour vérifier.
Objectif : [SEUIL]% de couverture de branches.
```

### Prompt 6.3 : Tests de mutation (optionnel mais puissant)

```
Pour vérifier que les tests détectent réellement les bugs, applique
du mutation testing :

1. Installe et configure mutmut :
   ```toml
   [tool.mutmut]
   paths_to_mutate = "mon_projet/"
   tests_dir = "tests/"
   ```

2. Crée ./test-plan/scripts/mutation_test.py qui :
   - Lance mutmut sur le code Python migré
   - Identifie les mutants survivants (= modifications du code
     que les tests ne détectent pas)
   - Pour chaque mutant survivant, décrit la mutation et suggère
     un test qui l'aurait attrapé

3. Un mutant survivant signifie :
   "Si quelqu'un introduisait ce bug dans le code migré,
   aucun test ne le détecterait."
   → C'est un trou dans la qualité des tests, pas dans la couverture

Exemple : si changer `>` en `>=` sur une ligne ne fait échouer aucun test,
il manque un test de valeur limite.
```

---

## Résumé : la chaîne complète de confiance

```
Phase 0 : Capturer la vérité SAS
   │  Exécuter le SAS original → résultats de référence réels
   ▼
Phases 1-3 : Analyser et planifier
   │  Inventaire, branches, scénarios
   ▼
Phase 4 : Générer les DataFrames de test
   │  Fixtures pytest, factories, exports Parquet
   ▼
Phase 5 : Harnais de test
   │  Config pytest, assert_sas_equal(), rapport
   ▼
Phase 6 : Mesurer et itérer          ◄── BOUCLE
   │  pytest-cov → trous → nouveaux tests → re-mesurer
   │  Répéter jusqu'à [SEUIL]%
   ▼
Phase 6.3 (optionnel) : Mutation testing
   │  Vérifier que les tests attrapent les vrais bugs
   ▼
✅ Couverture MESURÉE et VÉRIFIÉE
```

Sans la Phase 0 et la Phase 6, on a une couverture "sur papier".
Avec elles, on a une couverture mesurée par des outils réels (pytest-cov)
et validée contre les résultats du SAS original.
