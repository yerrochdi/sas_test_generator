/*************************************************************
 * Macro: classification du risque
 *************************************************************/

%macro classify_risk(var_age=age, var_income=income, out_var=risk_level);
    if &var_age < 25 then &out_var = "YOUNG_HIGH";
    else if &var_age >= 25 and &var_age < 65 then do;
        if &var_income > 80000 then &out_var = "MIDAGE_LOW";
        else &out_var = "MIDAGE_MEDIUM";
    end;
    else &out_var = "ELDER_SPECIAL";
%mend classify_risk;
