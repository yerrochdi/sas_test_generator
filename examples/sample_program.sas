/*************************************************************
 * Sample SAS Program — Rich branching for coverage testing
 *
 * Input dataset: WORK.CUSTOMERS
 *   Columns: customer_id (num), age (num), income (num),
 *            status (char), score (num)
 *
 * Output datasets:
 *   WORK.CLASSIFIED  — customers with risk classification
 *   WORK.SUMMARY     — aggregated summary via PROC SQL
 *************************************************************/

/* --------------------------------------------------------- */
/* DATA STEP: Classify customers into risk categories        */
/* --------------------------------------------------------- */
data classified;
    set customers;

    length risk_category $20 segment $10 flag $5;

    /* Branch 1: Age-based classification */
    if age < 25 then do;
        risk_category = "YOUNG_HIGH_RISK";
        age_group = 1;
    end;
    else if age >= 25 and age < 45 then do;
        risk_category = "MIDAGE_MEDIUM";
        age_group = 2;
    end;
    else if age >= 45 and age < 65 then do;
        risk_category = "SENIOR_LOW";
        age_group = 3;
    end;
    else do;
        risk_category = "ELDER_SPECIAL";
        age_group = 4;
    end;

    /* Branch 2: Income tiers */
    if income > 100000 then
        income_tier = "HIGH";
    else if income > 50000 then
        income_tier = "MEDIUM";
    else
        income_tier = "LOW";

    /* Branch 3: Score-based segment using SELECT */
    select;
        when (score >= 800) segment = "PREMIUM";
        when (score >= 600) segment = "STANDARD";
        when (score >= 400) segment = "BASIC";
        otherwise           segment = "SUBPRIME";
    end;

    /* Branch 4: Status check */
    if status = "ACTIVE" then
        flag = "OK";
    else if status = "SUSPENDED" then
        flag = "WARN";
    else
        flag = "BLOCK";

    /* Branch 5: Combined condition */
    if age > 60 and income < 30000 then
        vulnerable = 1;
    else
        vulnerable = 0;
run;

/* --------------------------------------------------------- */
/* PROC SQL: Create summary with CASE/WHEN branches          */
/* --------------------------------------------------------- */
proc sql;
    create table summary as
    select
        risk_category,
        count(*) as n_customers,
        mean(income) as avg_income,
        case
            when mean(score) >= 700 then "GOOD_PORTFOLIO"
            when mean(score) >= 500 then "MIXED_PORTFOLIO"
            else "RISKY_PORTFOLIO"
        end as portfolio_quality,
        case
            when count(*) >= 10 then "LARGE_SEGMENT"
            when count(*) >= 5  then "MEDIUM_SEGMENT"
            else "SMALL_SEGMENT"
        end as segment_size
    from classified
    where age > 0 and income >= 0
    group by risk_category;
quit;
