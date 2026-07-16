# DIBBs Index Initialization

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Pre-requisites](#pre-requisites)
- [Responsibilities](#responsibilities)
- [Index Behavior](#index-behavior)
- [Lambda Actions](#lambda-actions)
- [Environment Variables](#environment-variables)
- [Tests](#tests)

## Overview

This package contains the Lambda handler for initializing and maintaining the OpenSearch index used by the Text-to-Code pipeline.

The index stores LOINC code metadata and embedding vectors used for semantic search. The Lambda is intended to run during deployment or maintenance workflows to create the OpenSearch index with the expected settings and mappings.

## Getting Started

### Pre-requisites

- Python 3.14
- Docker
- Docker Compose [optional]

## Responsibilities

This package is responsible for:

- Creating the OpenSearch index when it does not already exist.
- Defining the expected LOINC index mappings.
- Configuring the vector field used for similarity search.
- Validating the existing index mapping.
- Recreating the index when required mapping fields are incorrect.
- Clearing and recreating the index for re-ingestion workflows.
- Updating OpenSearch slowlog settings for debugging and performance analysis.

## Index Behavior

The index mapping includes LOINC metadata fields and a `description_vector` field for k-nearest-neighbor search.

The `description_vector` field is configured as a `knn_vector` with:

```text
dimension: 1024
engine: faiss
method: hnsw
space_type: cosinesimil
```

The Lambda validates that the index contains the expected vector mapping. If the index exists but the `description_vector` field is not configured as a `knn_vector`, the Lambda deletes and recreates the index with the expected mapping.

## Lambda Actions

The Lambda reads an optional `action` value from the event payload.

### create_index

Creates the index if it does not exist and validates the current mapping.

This is the default action when no action is provided.

```json
{
  "action": "create_index"
}
```

### clear_index

Deletes the index if it exists, then recreates it with the expected mapping.

Use this before re-ingesting embeddings when the existing indexed data should be cleared.

```json
{
  "action": "clear_index"
}
```

### set_slowlog

Updates OpenSearch slowlog thresholds for query and fetch operations.

Use `threshold_ms` to enable slowlogs at the desired threshold. Use `0` to disable the configured slowlog thresholds.

```json
{
  "action": "set_slowlog",
  "threshold_ms": 100
}
```

## Environment Variables

The Lambda reads these environment variables:

```text
AWS_REGION
INDEX_NAME
OPENSEARCH_ENDPOINT_URL
```

## Tests

Run the package tests with:

```bash
just all unit packages/index-lambda/tests
```
