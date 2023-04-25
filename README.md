# ChildhoodCancerDataInitiative-CatchERRy
This script will take a CCDI metadata manifest file and try to blindly fix the most common errors before the validation step. 

This is a refactoring of the [CCDI-CatchERR](https://github.com/CBIIT/ChildhoodCancerDataInitiative-CatchERR) code into python.

To run the script on a CCDI template, run the following command in a terminal where python is installed for help.

```
python CCDI-CatchERRy.py -h
```

```
usage: CCDI-CatchERRy.py [-h] -f FILENAME -t TEMPLATE

This script will take a CCDI metadata manifest file and try to blindly fix the most common errors before the validation step. This is based on the CCDI-CatchERR.R script.

optional arguments:
  -h, --help            show this help message and exit
  -f FILENAME, --filename FILENAME
                        dataset file (.xlsx, .tsv, .csv)
  -t TEMPLATE, --template TEMPLATE
                        dataset template file, CCDI_submission_metadata_template.xlsx
```

An example to run this script:

```
python CCDI-CatchERRy.py -f example_files/b_problematic_CCDI_Submission_Template_v1.1.2_EampleR.xlsx -t example_files/a_good_CCDI_Submission_Template_v1.1.2_EampleR.xlsx 
```
Since the submission templates are a template with data, you can use them as both the file input and template input in this instance.

```
The CCDI submission template is being checked for errors.


The file based nodes will now have a guid assigned to each unique file.


Writing out the CatchERR file.


Process Complete.

The output file can be found here: example_files/b_problematic_CCDI_Submission_Template_v1.1.2_EampleR_CatchERR20230425
```
