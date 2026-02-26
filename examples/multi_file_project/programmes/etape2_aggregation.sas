/*************************************************************
 * Etape 2: Aggregation par segment
 *************************************************************/

proc sql;
    create table summary as
    select
        segment,
        count(*) as nb_clients,
        mean(income) as revenu_moyen,
        case
            when mean(score) >= 700 then "BON"
            when mean(score) >= 500 then "MOYEN"
            else "RISQUE"
        end as qualite_portefeuille
    from classified
    where age > 0
    group by segment;
quit;
