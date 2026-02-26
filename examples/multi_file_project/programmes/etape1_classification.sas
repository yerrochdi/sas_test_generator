/*************************************************************
 * Etape 1: Classification des clients
 *************************************************************/

data classified;
    set customers;

    /* Use the risk macro */
    %classify_risk(var_age=age, var_income=income, out_var=risk_level);

    /* Score-based segmentation */
    if score >= 800 then segment = "PREMIUM";
    else if score >= 600 then segment = "STANDARD";
    else if score >= 400 then segment = "BASIC";
    else segment = "SUBPRIME";

    /* Flag vulnerable customers */
    if age > 70 and income < 25000 then vulnerable = 1;
    else vulnerable = 0;
run;
