# DIBBs Lambda Handler

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Pre-requisites](#pre-requisites)
- [Responsibilities](#responsibilities)
- [Cached Clients](#cached-clients)
- [S3 and Event Helpers](#s3-and-event-helpers)
- [OpenSearch Helpers](#opensearch-helpers)
- [Tests](#tests)

## Overview

This package contains shared Lambda helper utilities used by DIBBs Text-to-Code pipeline packages.

The package centralizes common Lambda support behavior, including AWS client creation, S3 file access, EventBridge S3 event parsing, persistence ID extraction, and OpenSearch query execution. It is used by Lambda packages that need consistent access to AWS resources and shared pipeline object metadata.

## Getting Started

### Pre-requisites

- Python 3.13 or higher
- Docker
- Docker Compose [optional]

## Responsibilities

This package is responsible for:

- Creating cached AWS authentication objects.
- Creating cached S3 clients.
- Creating cached OpenSearch clients.
- Reading file contents from S3.
- Writing file contents to S3.
- Checking whether S3 objects exist.
- Extracting bucket and object key data from EventBridge S3 events.
- Extracting persistence IDs from S3 object keys.
- Running OpenSearch queries and returning typed OpenSearch results.

## Cached Clients

The package caches AWS authentication, S3, and OpenSearch clients so Lambda invocations can reuse initialized clients across warm starts.

The `reset_cached_clients` helper clears cached clients and auth. This is primarily useful in tests when environment variables or mocked AWS resources need to be reset between cases.

## S3 and Event Helpers

The package includes helpers for common S3 operations:

- `create_s3_client`
- `get_file_content_from_s3`
- `put_file`
- `check_s3_object_exists`
- `get_eventbridge_data_from_s3_event`
- `get_persistence_id`

`get_persistence_id` extracts the persistence ID from an S3 object key by removing the expected pipeline prefix.

For example:

```text
TextToCodeSubmissionV2/2026/01/01/0026b704-f510-4494-8d21-11d27217d96e
```

becomes:

```text
2026/01/01/0026b704-f510-4494-8d21-11d27217d96e
```

## OpenSearch Helpers

The package includes helpers for creating an authenticated OpenSearch client and retrieving typed OpenSearch results.

OpenSearch configuration is read from environment variables and AWS credentials. The OpenSearch endpoint is normalized by removing the protocol before client creation.

## Environment Variables

The package reads these environment variables depending on which helpers are used:

```text
AWS_REGION
S3_ENDPOINT_URL
OPENSEARCH_ENDPOINT_URL
```

## Tests

Run the package tests with:

```bash
just test all packages/lambda-handler/tests
```
