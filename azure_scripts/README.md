# DIBBS Text to Code Azure Scripts

## Table of Contents

- [Overview](#overview)
- [dibbs_env.yml](#dibbs_env.yml)
- [Notebooks](#notebooks)

## Overview

The Azure Scripts directory is a collection of files used to run embeddings and performance tests in an Azure environment.

## dibbs_env.yml

The dibbs_env.yml file lays out the requirements for running a controlled environment in Azure ML.

### Attaching the dibbs_env.yml to your compute instance

To use the environment, you need to attach it to your compute instance one time, following these steps:

1. Upload `dibbs_env.yml` to your notebook folder within Azure ML Studio.
2. In Azure ML Studio, open a notebook and start the compute instance attached to your notebook.
3. Once the compute instance is running, click on the 3 dots to the right of your compute instance selection and choose "Open terminal" from the dropdown.
4. Once in the terminal, create the conda environment by running `conda env create -f dibbs_env.yml`
5. Activate the environment by running `conda activate dibbs_env`
6. Register the environment as a Jupyter kernel by running `python -m ipykernel install --user --name dibbs_env --display-name "DIBBs Env"`
7. Refresh your notebook environment, starting your compute instance and selecting the `DIBBs Env` kernel.

## Notebooks

### emmbedding

This was the original notebook that took the various LOINC terms (Short Name, Long Common Name, and Display Name) and generate embeddings for them.

(maybe have Brandon add some more detail here?)

### performance

This notebook is used to perform performance tests against the various embeddings to help determine which one(s) will be best suited for our work.

(maybe have Brandon add some more detail here?)

### loinc_type

It was determined that we will need to filter the various LOINC terms based upon if they are part of the 'Resulting' Labs (Observations), 'Ordered' Labs (Orders), or Both. The LOINC Lab Types were added to the extracts from LOINC and this notebook was created to update the existing embedding files, by adding a new key-value pair `loinc_types` with the proper value (`Order`, `Observation`, `Both`) for the various LOINC terms.

While running this notebook, it was discovered that there were some `codes` in the embedding files that were empty (""). This notebook was updated to re-write the embedding files with the correct `loinc_types` and to remove any records in the file where the `codes` was empty. These new files are stored in a `refined` folder within the `embeddings` folder within our Azure Blob Storage.

:warning: **We should perhaps combined the functionality of this notebook back into the embeddings notebook!** :warning:

### split-embeddings

To make the embedding files, that were already created and tested, more digestable and useable within AWS (Opensearch) we created this notebook to split out the embedding files into smaller chunks and store them into LJSON files. These are stored within the `embeddings/refined/split` folder in our Azure Blob Storage.

Only a number of embedding files were chunked up, as they were determined to be of better quality.

:warning: **We should perhaps combined the functionality of this notebook back into the embeddings notebook!** :warning:
