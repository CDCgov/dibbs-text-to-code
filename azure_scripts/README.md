# DIBBS Text to Code Azure Scripts

## Table of Contents

- [Overview](#overview)
- [dibbs_env.yml](#dibbs_env.yml)

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
