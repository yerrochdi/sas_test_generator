---

### Workflow : workflow_01

**Source** : run_sas_param.json → `$.workflow_01`

**Chaîne d'exécution** :
[1] `inf/01_Alim/02_Pgm_Pilotes/F0_200_IMPORT_REFS_SINAPPS.sas`  
↓ lit fichiers Excel (`&ChemDonn./REF_DSIATN.xlsx` onglets `STATUTS`, `CONTROLES`; `&ChemDonn./MAPPING_SINAPPS.xlsx` onglet `MAPPING`)  
↓ écrit → `ATNREF.REF_STATUTS`, `ATNREF.REF_CONTROLES`, `ATNREF.MAPPING_SINAPPS`

[2] `inf/01_Alim/02_Pgm_Pilotes/F0_300_RECUP_INFOS_SINAPPS.sas`  
↓ lit ← `ATNREF.MAPPING_SINAPPS`  
↓ exécute dynamiquement (via `call execute`) :
- `%F0_310_VERIF_PRESENCE_SINAPPS(Table_A_Recup=...,Table_Temp=...)`
- `%F0_320_CREA_VUE_SINAPPS(Table_Temp=...)`
- `%F0_330_LANCEMENT_RG_CALC` → `%F0_331/%F0_332/%F0_333_RGxx/%F0_339`
- `%F0_340_CREA_TABLE_FINALE_SINAPPS` → `%F0_341/%F0_342`
- `%F0_999_SUIVI_CONTROLES` (appelé par les macros de contrôle)

↓ écrit principalement → `ATNDTM.ATN_SUIVOMT_DARVA`, `ATNDTM.SOLLICITATIONS`, `ATNDTM.ATN_DARVA_DGL`, `ATNDTM.ATN_DARVA_PJD`, `ATNDTM.SUIVI_CONTROLES_SINAPPS`  
↓ écrit aussi (snapshot technique) → `ATNVUE.*` (copie de `ATNTMP.*`)  
↓ export conditionnel anomalies → `&DATAproj_K./05_Reportings/&DHTRAIT_TEXTE._ano_sinapps.xlsx`

**Analyse par programme de la chaîne** :

1) `F0_200_IMPORT_REFS_SINAPPS.sas`
- **Lit** : fichiers externes Excel via `%MG_Lect_Fic_Excel`.
- **Écrit** : `ATNREF.REF_STATUTS`, `ATNREF.REF_CONTROLES`, `ATNREF.MAPPING_SINAPPS`.
- **Macros appelées** : `%MG_Lect_Fic_Excel`.
- **%include** : aucun dans ce fichier.

2) `F0_300_RECUP_INFOS_SINAPPS.sas`
- **Lit** : `ATNREF.MAPPING_SINAPPS`, `ATNDTM.SUIVI_CONTROLES_SINAPPS` (pour comptage/export anomalies), tables `ATNTMP.*` et `ATNREF.VARIABLES_*` via macros.
- **Écrit** :
  - temporaires : `WORK.VUES_SINAPPS`, `WORK.TABLES_DTM`, `ATNTMP.*`, `ATNREF.VARIABLES_*`, `ATNVUE.*` ;
  - datamarts finaux : `ATNDTM.ATN_SUIVOMT_DARVA`, `ATNDTM.SOLLICITATIONS`, `ATNDTM.ATN_DARVA_DGL`, `ATNDTM.ATN_DARVA_PJD` ;
  - suivi : `ATNDTM.SUIVI_CONTROLES_SINAPPS` ;
  - fichier : `..._ano_sinapps.xlsx` (si anomalies).
- **Macros appelées (directes)** : `%F0_310_VERIF_PRESENCE_SINAPPS`, `%F0_320_CREA_VUE_SINAPPS`, `%F0_330_LANCEMENT_RG_CALC`, `%F0_340_CREA_TABLE_FINALE_SINAPPS`, `%MG_Envoi_mail`.
- **Macros appelées (indirectes)** : `%F0_321_MAJ_LONGUEURS`, `%F0_331_CALC_VERIF_PRESENCE`, `%F0_332_CALC_VERIF_GO_RG`, `%F0_333_RG01/RG02/RG03/RG04/RG07/RG08/RG09/RG10/RG11/RG13/RG14`, `%F0_339_AJOUT_LISTE_VAR_CALC`, `%F0_341_CONVERSION_VAR`, `%F0_342_SELECT_LIGNES`, `%F0_999_SUIVI_CONTROLES`, `%MG_Crea_Flag_Tech`.
- **%include** : aucun dans ce fichier (chargement macros supposé via autoexec global).

**Flux de données (inter-programmes du workflow)** :
- `ATNREF.MAPPING_SINAPPS` : produit par [1] puis lu par [2] (pivot du workflow).
- Dans [2], les vues SINAPPS sont chargées en `WORK.<Table_Temp>` puis normalisées en `ATNTMP.<Table_Temp>` et enrichies par RG.
- `ATNTMP.*` (enrichies) alimentent ensuite la construction des datamarts `ATNDTM.*`.

**Datasets d'entrée externes** (à fournir en données de test) :

| Dataset / Source | Utilisé par | Variables clés | Description probable |
|---------|-------------|----------------|---------------------|
| `&ChemDonn./REF_DSIATN.xlsx` (onglets `STATUTS`, `CONTROLES`) | `F0_200_IMPORT_REFS_SINAPPS.sas` | IDs de statuts / IDs de contrôles | Référentiels applicatifs |
| `&ChemDonn./MAPPING_SINAPPS.xlsx` (onglet `MAPPING`) | `F0_200_IMPORT_REFS_SINAPPS.sas` puis tout `F0_300` | `TABLE_A_RECUP`, `TABLE_TEMP`, `TABLE_DATAMART`, `VARIABLE_TEMP`, `RG`, `TYPE_RG`, `CALC_*` | Paramétrage de mapping et de calcul |
| `SINAPPS.<TABLE_A_RECUP>` (liste dynamique issue de `ATNREF.MAPPING_SINAPPS`) | `%F0_310_VERIF_PRESENCE_SINAPPS` | variable selon vue ; clés fréquemment `_ID`, `prestations_darva_idx`, `conclusions_id`, etc. | Sources métiers DARVA SINAPPS |
| `Param_MV.csv` | `Autoexec.sas` (`%MG_Lect_Fic_Param`) | paires nom/valeur par environnement | Paramétrage macro-variables (mails, chemins, etc.) |

**Datasets intermédiaires** (produits par le workflow, pas à fournir) :
- `ATNREF.MAPPING_SINAPPS` (étape 1 → étape 2)
- `WORK.VUES_SINAPPS`, `WORK.TABLES_DTM`, `WORK.<tables techniques RG>`
- `ATNREF.VARIABLES_<TABLE_TEMP>`
- `ATNTMP.<TABLE_TEMP>` (tables tampon issues de SINAPPS + enrichissements RG)
- `ATNVUE.<TABLE_TEMP>` (snapshot avant calcul)
- Exemples de tables tampon enrichies : `ATNTMP.MISSION_DARVA`, `ATNTMP.DEST_IND`, `ATNTMP.MESURES`, `ATNTMP.SOLL_DARVA`, `ATNTMP.ACTEURS`, `ATNTMP.DOMMAGES_ET_BIENS`, `ATNTMP.CONTRATS_GTIE`

**Datasets de sortie** (à vérifier) :
- `ATNDTM.ATN_SUIVOMT_DARVA`
- `ATNDTM.SOLLICITATIONS`
- `ATNDTM.ATN_DARVA_DGL`
- `ATNDTM.ATN_DARVA_PJD`
- `ATNDTM.SUIVI_CONTROLES_SINAPPS`
- `&DATAproj_K./05_Reportings/&DHTRAIT_TEXTE._ano_sinapps.xlsx` (sortie conditionnelle si anomalies)

**Paramètres / macro-variables** :

| Variable | Valeur (JSON) | Impact |
|----------|---------------|--------|
| *(run_sas_param.json)* | Aucune macro-variable explicite | Ce JSON ne porte que l’ordre et les scripts (`workflow_01`) |
| `&env` | `%sysget(env)` (souvent alimenté par Control-M: `%%G_ENV`) | Sélection de l’environnement (DEV/REC/PROD) |
| `&reprise` | `%sysget(reprise)` (Control-M: `%REPRISE%`) | Active le mode reprise |
| `&date_rep` | `%sysget(date_rep)` (Control-M: `%DATE_REP%`) | Date de traitement forcée si reprise |
| `&DTTRAIT` | `today()` ou `&date_rep` si reprise | Date de référence de traitement |
| `&DHTRAIT`, `&DHTRAIT_TEXTE` | dérivées de `&DTTRAIT` + heure | horodatage contrôles et nommage export anomalies |
| `&AAAA_ALIM`, `&MM_ALIM`, `&MMAA_ALIM`, `&DEBUT_DTSITU`, `&FIN_DTSITU` | calculées dans `Autoexec.sas` | fenêtrage temporel / bibliothèques périodées |
| `&ChemDonn`, `&DATAproj_K`, `&MailAthena`, `&MailAdmin`, `&srvfiles`, `&chemin_autoexec_global` | issues de l’autoexec global + `Param_MV.csv` | chemins, libs, notification mail, config globale |

**Fichiers %include de configuration** :
- `inf/01_Alim/01_Autoexec/Autoexec.sas` inclut :
  - `I:\SASConfig\chem_autoexec_global.sas`
  - `&chemin_autoexec_global.\_PGLOBAL\inf\01_Alim\01_Autoexec\Autoexec_Alim_Global.sas`

**Complexité estimée** :
- Nombre de programmes (chaîne JSON) : 2
- Nombre de programmes/macros effectivement exécutés : ~18 à 22 (selon RG présentes dans le mapping)
- Nombre de branches estimé : ~70+ (if/else RG + exécution dynamique par mapping)
- Programmes critiques : `F0_300_RECUP_INFOS_SINAPPS.sas`, `F0_340_CREA_TABLE_FINALE_SINAPPS.sas`

---

## Résumé final

**Tableau récapitulatif des workflows** :

| # | Workflow | Nb programmes | Nb entrées externes | Complexité | Ordre de test recommandé |
|---|----------|---------------|---------------------|------------|--------------------------|
| 1 | `workflow_01` (Import refs + Récup/Calcul SINAPPS) | 2 (pilotes) / ~20 effectifs | 4 familles | Élevée | 1 |

**Ordre de test recommandé** :
Avec un seul workflow, l’ordre recommandé est :
1. Valider `F0_200_IMPORT_REFS_SINAPPS.sas` (qualité mapping/référentiels),
2. puis `F0_300_RECUP_INFOS_SINAPPS.sas` sur un sous-ensemble de vues SINAPPS,
3. enfin exécuter en volumétrie complète + contrôle des sorties `ATNDTM.*` et du fichier anomalies.

**Datasets d'entrée partagés** :
- Sans objet entre workflows (un seul workflow dans `run_sas_param.json`).
- Point d’attention interne : `ATNREF.MAPPING_SINAPPS` est partagé par plusieurs sous-étapes/macros du même workflow (`F0_300`, `F0_310`, `F0_330`, `F0_341`, `F0_342`).
