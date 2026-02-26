/*************************************************************
 * Main entry point — multi-file SAS project example
 *
 * This project demonstrates how %INCLUDE works with
 * the sas-data-generator tool.
 *************************************************************/

/* Include macro definitions */
%include "macros/macro_risque.sas";

/* Include initialization */
%include "includes/init.sas";

/* Run processing steps */
%include "programmes/etape1_classification.sas";
%include "programmes/etape2_aggregation.sas";
