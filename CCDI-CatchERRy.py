#!/usr/bin/env python3

#CCDI-CatchERRy.py

##############
#
# Env. Setup
#
##############

#List of needed packages
import pandas as pd
import numpy as np
import argparse
import argcomplete
import os
import re
from datetime import date
import warnings
import uuid
import openpyxl
from openpyxl.utils.dataframe import dataframe_to_rows
import boto3
from botocore.exceptions import ClientError


parser = argparse.ArgumentParser(
                    prog='CCDI-CatchERRy.py',
                    description='This script will take a CCDI metadata manifest file and try to blindly fix the most common errors before the validation step. This is based on the CCDI-CatchERR.R script.',
                    )

parser.add_argument( '-f', '--filename', help='dataset file (.xlsx, .tsv, .csv)', required=True)
parser.add_argument( '-t', '--template', help="dataset template file, CCDI_submission_metadata_template.xlsx", required=True)
parser.add_argument( '-p', '--s3_profile', help="The s3 bucket profile associated with the access to the s3 bucket.",default='default')


argcomplete.autocomplete(parser)

args = parser.parse_args()

#pull in args as variables
file_path=args.filename
template_path=args.template
profile=args.s3_profile

print('\nThe CCDI submission template is being checked for errors.\n\n')


##############
#
# File name rework
#
##############

#Determine file ext and abs path
file_name=os.path.splitext(os.path.split(os.path.relpath(file_path))[1])[0]
file_ext=os.path.splitext(file_path)[1]
file_dir_path=os.path.split(os.path.relpath(file_path))[0]

if file_dir_path=='':
    file_dir_path="."

#obtain the date
def refresh_date():
    today=date.today()
    today=today.strftime("%Y%m%d")
    return today

todays_date=refresh_date()

#Output file name based on input file name and date/time stamped.
output_file=(file_name+
            "_CatchERR"+
            todays_date)


##############
#
# Pull Dictionary Page to create node pulls
#
##############

def read_xlsx(file_path: str, sheet: str):
    #Read in excel file
    warnings.simplefilter(action='ignore', category=UserWarning)
    return pd.read_excel(file_path, sheet, dtype=str)


#create workbook
xlsx_model=pd.ExcelFile(template_path)

#create dictionary for dfs
model_dfs= {}

#read in dfs and apply to dictionary
for sheet_name in xlsx_model.sheet_names:
    model_dfs[sheet_name]= read_xlsx(xlsx_model, sheet_name)

#pull out the non-metadata table and then remove them from the dictionary
readme_df=model_dfs["README and INSTRUCTIONS"]
dict_df=model_dfs["Dictionary"]
tavs_df=model_dfs['Terms and Value Sets']

#create a list of all properties and a list of required properties
all_properties=set(dict_df['Property'])
required_properties=set(dict_df[dict_df["Required"].notna()]["Property"])


##############
#
# Read in TaVS page to create value checks
#
##############

#Read in Terms and Value sets page to obtain the required value set names.
tavs_df=tavs_df.dropna(how='all').dropna(how='all', axis=1)


##############
#
# Read in data
#
##############

#create workbook
xlsx_data=pd.ExcelFile(file_path)

#create dictionary for dfs
meta_dfs= {}

#read in dfs and apply to dictionary
for sheet_name in xlsx_data.sheet_names:
    meta_dfs[sheet_name]= read_xlsx(xlsx_data, sheet_name)

#remove model tabs from the meta_dfs
del meta_dfs["README and INSTRUCTIONS"]
del meta_dfs["Dictionary"]
del meta_dfs['Terms and Value Sets']

#create a list of present tabs
dict_nodes=set(list(meta_dfs.keys()))


##############
#
# Go through each tab and remove completely empty tabs
#
##############

for node in dict_nodes:
    #see if the tab contain any data
    test_df=meta_dfs[node]
    test_df=test_df.drop('type', axis=1)
    test_df=test_df.dropna(how='all').dropna(how='all', axis=1)
    #if there is no data, drop the node/tab
    if test_df.empty:
        del meta_dfs[node]

#determine nodes again
dict_nodes=set(list(meta_dfs.keys()))


##############
#
# Start Log Printout
#
##############

with open(f'{file_dir_path}/{output_file}.txt', 'w') as outf:
        

##############
#
# Terms and Value sets checks
#
##############

    print("The following columns have controlled vocabulary on the 'Terms and Value Sets' page of the template file. If the values present do not match, they will noted and in some cases the values will be replaced:\n----------", file=outf)

    #For newer versions of the submission template, obtain the arrays from the Dictionary tab
    if any(dict_df['Type'].str.contains('array')):
        enum_arrays=dict_df[dict_df['Type'].str.contains('array')]["Property"].tolist()
    else:
        enum_arrays=['therapeutic_agents','treatment_type','study_data_types','morphology','primary_site','race']

    #for each tab
    for node in dict_nodes:
        print(f'\n{node}\n----------', file=outf)
        df=meta_dfs[node]
        properties=df.columns

        #for each property
        for property in properties:
            tavs_df_prop=tavs_df[tavs_df['Value Set Name']==property]
            #if the property is in the TaVs data frame
            if len(tavs_df_prop)>0:
                #if the property is not completely empty:
                if not df[property].isna().all():
                    #if the property is an enum
                    if property in enum_arrays:
                        #reorder the array to be in alphabetical order
                        for value_pos in range(0,len(df[property])):
                            value=df[property][value_pos]                
                            if ";" in value:
                                value=";".join(sorted(set(value.split(";")), key = lambda s: s.casefold()))
                                df[property][value_pos]=value

                        #obtain a list of value strings
                        unique_values=df[property].dropna().unique()

                        #pull out a complete list of all values in sub-arrays
                        for unique_value in unique_values:
                            if ";" in unique_value:
                                #find the position
                                unique_value_pos=np.where(unique_values==unique_value)[0][0]
                                #delete entry
                                unique_values=np.delete(unique_values,unique_value_pos)
                                #rework the entry and apply back to list
                                unique_value=list(set(unique_value.split(";")))
                                for value in unique_value:
                                    unique_values=np.append(unique_values,value)

                        #make sure list is unique
                        unique_values=list(set(unique_values))

                        if set(unique_values).issubset(set(tavs_df_prop['Term'])):
                            #if yes, then 
                            print(f'\tPASS: {property}, property contains all valid values.', file=outf)
                        else:
                            #if no, then
                            #for each unique value
                            for unique_value in unique_values:
                                if unique_value not in tavs_df_prop['Term'].values:
                                    print(f'\tERROR: {property} property contains a value that is not recognized: {unique_value}', file=outf)
                                    #fix if lower cases match
                                    if (tavs_df_prop['Term'].str.lower().values==unique_value.lower()).any():
                                        new_value=tavs_df_prop[(tavs_df_prop['Term'].str.lower().values==unique_value.lower())]['Term'].values[0]
                                        df[property]=df[property].apply(lambda x: re.sub(rf'\b{unique_value}\b', new_value, x))
                                        print(f'\t\tThe value in {property} was changed: {unique_value} ---> {new_value}', file=outf)    

                    #if the property is not an enum
                    else:
                        unique_values=df[property].dropna().unique()
                        #as long as there are unique values
                        if len(unique_values)>0:
                            #are all the values found in the TaVs terms
                            if set(unique_values).issubset(set(tavs_df_prop['Term'])):
                                #if yes, then 
                                print(f'\tPASS: {property}, property contains all valid values.', file=outf)
                            else:
                                #if no, then
                                #for each unique value, check it against the TaVs data frame
                                for unique_value in unique_values:
                                    if unique_value not in tavs_df_prop['Term'].values:
                                        print(f'\tERROR: {property} property contains a value that is not recognized: {unique_value}', file=outf)
                                        #fix if lower cases match
                                        if (tavs_df_prop['Term'].str.lower().values==unique_value.lower()).any():
                                            new_value=tavs_df_prop[(tavs_df_prop['Term'].str.lower().values==unique_value.lower())]['Term'].values[0]
                                            df[property]=df[property].replace(unique_value,new_value)
                                            print(f'\t\tThe value in {property} was changed: {unique_value} ---> {new_value}', file=outf)



##############
#
# Check and replace for non-UTF-8 characters
#
##############

    print("\nCertain characters (®, ™, ©) do not handle being transformed into certain file types, due to this, the following characters were changed.\n----------", file=outf)

    non_utf_8_array=['®','™','©']

    non_utf_8_array='|'.join(non_utf_8_array)

    #for each node
    for node in dict_nodes:
        df=meta_dfs[node]
        #for each column
        for col in df.columns:
            #check for any of the values in the array
            if df[col].str.contains(non_utf_8_array).any():
                #only if they have an issue, then print out the node.
                print(f'\n{node}\n----------', file=outf)
                rows = np.where(df[col].str.contains(non_utf_8_array))[0]
                for i in range(0,len(rows)):
                    print(f'\tWARNING: The property, {col}, contained a non-UTF-8 character on row: {rows[i]+1}\n', file=outf)
                df=df.applymap(lambda x: x.replace('®', '(R)').replace('™', '(TM)').replace('©', '(C)') if isinstance(x,str) else x)
                meta_dfs[node]=df


##############
#
# ACL pattern check
#
##############

    print("\nThe value for ACL will be check to determine it follows the required structure, ['.*'].\n----------", file=outf)

    #check each node to find the acl property (it has been in study and study_admin)
    for node in dict_nodes:
        if "acl" in meta_dfs[node].columns:
            df=meta_dfs[node]
            acl_value=df['acl']

    #if there is more than one value
    if len(acl_value)>1:
        print(f"\tERROR: There is more than one ACL associated with this study and workbook. Please only submit one ACL and corresponding data to a workbook.\n", file=outf)
    #if there is only one value
    elif len(acl_value)==1:
        acl_value=acl_value[0]
        #if it is NA
        if pd.isna(acl_value):
            print(f"\tERROR: Please submit an ACL value to the 'acl' property in the {node} node.\n", file=outf)
        #if it is not NA
        elif not pd.isna(acl_value):
            acl_test=acl_value.startswith("['") and acl_value.endswith("']")
            #if it is properly formed
            if acl_test:
                print(f"\tThe ACL found in the {node} node, matches the required structure: {acl_value}", file=outf)
            #otherwise fix it
            else:
                acl_fix=f"['{acl_value}']"
                df['acl']=acl_fix
                print(f"\tThe ACL found in the {node} node, does not match the required structure, it will be changed:", file=outf)
                print(f"\t\t{acl_value} ---> {acl_fix}", file=outf)
    #catch-all, something is very wrong
    else:
        print(f"\tERROR: Something is wrong with the ACL value submitted in the {node} node.\n", file=outf)


##############
#
# Fix URL paths
#
##############

    print("\nCheck the following url columns (file_url_in_cds), to make sure the full file url is present and fix entries that are not:\n----------\n\nWARNING: If you are seeing a large number of 'ERROR: There is an unresolvable issue...', it is likely there are two or more buckets and this is the script trying and failing at checks against the other bucket for the file.", file=outf)

    #check each node
    for node in dict_nodes:
        #for a column called file_url_in_cds
        if "file_url_in_cds" in meta_dfs[node].columns:
            df=meta_dfs[node]
            print (f"{node}\n----------", file=outf)


            #discover all possible base bucket urls in the file node
            
            node_all_urls=df['file_url_in_cds'].dropna()
            node_urls= pd.DataFrame(node_all_urls)

            node_urls['bucket'] = node_urls['file_url_in_cds'].apply(lambda x: x.split('/')[2])

            node_urls = node_urls['bucket'].unique().tolist()

            #for each possible bucket based on the base urls in file_url_in_cds
            #go through and see if the values for the url can be filled in based on file_name and size
            if len(node_urls)>0:
                for node_url in node_urls:
                    #create a blank list for bad url_locations
                    bad_url_locs=[]
                    
                    #pull bucket metadata

                    #Get s3 session setup
                    session = boto3.Session(profile_name=profile)
                    s3_client = session.client('s3')

                    #initialize file metadata from bucket
                    s3_file_path=[]
                    s3_file_name=[]
                    s3_file_size=[]
                    
                    #try and see if the bucket exists, if it does, obtain the metadata from it
                    try:
                        s3_client.head_bucket(Bucket=node_url)

                        #create a paginator to itterate through each 1000 objs
                        paginator = s3_client.get_paginator('list_objects_v2')
                        response_iterator = paginator.paginate(Bucket=node_url)

                        #pull out each response and obtain file name and size
                        for response in response_iterator:
                            if 'Contents' in response:
                                for obj in response['Contents']:
                                    s3_file_path.append('s3://'+node_url+'/'+obj['Key'])
                                    s3_file_name.append(os.path.basename(obj['Key']))
                                    s3_file_size.append(obj['Size'])

                    except ClientError as e:
                        if e.response['Error']['Code']=='404':
                            print(f'\tThe following bucket either does not exist or you do not have read access for it: {node_url}', file=outf)

                #create a metadata data frame from the bucket
                df_bucket=pd.DataFrame({'file_path':s3_file_path, 'file_name':s3_file_name , 'file_size':s3_file_size})

                #find bad url locs based on the full file path and whether it can be found in the url bucket manifest.
                bad_url_locs = df['file_url_in_cds'].isin(df_bucket['file_path'])

                #Go through each bad location and determine if the correct url location can be determined on file_name and file_size.
                for loc in range(len(bad_url_locs)):
                    #if the value is bad then fix
                    if not bad_url_locs[loc]:
                        file_name_find=df['file_name'][loc]
                        file_size_find=df['file_size'][loc]

                        #filter the bucket df to see if there is exactly one file value that matches both name and file size
                        filtered_df=df_bucket[df_bucket['file_name']==file_name_find]
                        filtered_df=filtered_df[filtered_df['file_size']==int(file_size_find)]

                        if len(filtered_df)==1:
                            #output of url change

                            print(f"\tWARNING: The file location for the file, {file_name_find}, has been changed:", file=outf)
                            print(f"\t\t{df['file_url_in_cds'][loc]} ---> {filtered_df['file_path'].values[0]}", file=outf)

                            df['file_url_in_cds'][loc]=filtered_df['file_path'].values[0]
                        
                        else:
                            print(f"\tERROR: There is an unresolvable issue with the file url for file: {file_name_find}", file=outf)

                #write back to the meta_dfs list
                meta_dfs[node]=df

            else:
                print("ERROR: There is not a bucket associated with this node's files.", file=outf)


##############
#
# Assign guids to files
#
##############

    print("The file based nodes will now have a guid assigned to each unique file.\n")

    #check each node
    for node in dict_nodes:
        # if file_url_in_cds exists in the node
        if "file_url_in_cds" in meta_dfs[node].columns:
            df = meta_dfs[node]
            #identify posistions without guids
            no_guids=df['dcf_indexd_guid'].isna()
            if no_guids.any():
                #apply guids to files that don't have guids
                new_guids = df[no_guids].groupby(['file_url_in_cds', 'md5sum'])\
                            .apply(lambda x: "dg.4DFC/" + str(uuid.uuid4()))\
                            .reset_index()\
                            .rename(columns={0: 'dcf_indexd_guid'})
                # merge the new UUIDs back into the original dataframe but not via merge as it replaces one version over another
                for row in range(0,len(new_guids)):
                    fuic_value=new_guids.loc[row].file_url_in_cds
                    md5_value=new_guids.loc[row].md5sum
                    dig_value=new_guids.loc[row].dcf_indexd_guid

                    #locate the row position via file_url and md5sum values and then apply the guid
                    df.loc[(df['file_url_in_cds']==fuic_value) & (df['md5sum']==md5_value), 'dcf_indexd_guid']=dig_value


##############
#
# Write out
#
##############

print("\nWriting out the CatchERR file.\n")

template_workbook = openpyxl.load_workbook(template_path)

#for each sheet df
for sheet_name, df in meta_dfs.items():
    #select workbook tab
    ws=template_workbook[sheet_name]
    #remove any data that might be in the template
    ws.delete_rows(2, ws.max_row)

    #write the data
    for row in dataframe_to_rows(df, index=False, header=False):
        ws.append(row)

#save out template
template_workbook.save(f'{file_dir_path}/{output_file}.xlsx')

print(f"\n\nProcess Complete.\n\nThe output file can be found here: {file_dir_path}/{output_file}\n\n")
