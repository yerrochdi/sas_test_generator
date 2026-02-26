/*************************************************************
 * Initialization: formats and options
 *************************************************************/

options mprint mlogic symbolgen;

proc format;
    value risk_fmt
        1 = "LOW"
        2 = "MEDIUM"
        3 = "HIGH"
        4 = "VERY HIGH";
run;
