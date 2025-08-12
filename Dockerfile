FROM public.ecr.aws/lambda/python:3.12

LABEL org.opencontainers.image.source=https://github.com/CDCgov/dibbs-text-to-code
LABEL org.opencontainers.image.licenses=Apache-2.0

# Set the environment variable to prod by default
ARG ENVIRONMENT=prod
ENV ENVIRONMENT=${ENVIRONMENT}

# Initialize the dibbs_text_to_code directory
RUN mkdir -p "${LAMBDA_TASK_ROOT}/src/dibbs_text_to_code"

# Install build tools for compiling C++ extensions
RUN microdnf install -y gcc-c++ make && microdnf clean all

# Copy over just the pyproject.toml file and install the dependencies doing this
# before copying the rest of the code allows for caching of the dependencies
COPY ./pyproject.toml ${LAMBDA_TASK_ROOT}/pyproject.toml
RUN pip install --no-cache-dir "$(printf '%s' ".[${ENVIRONMENT}]")"
# Improve Lambda startup time by validating SpaCy models upfront,
# which preloads necessary libraries during build
RUN python -m spacy validate

# Copy over the rest of the code
COPY ./src ${LAMBDA_TASK_ROOT}/src
COPY README.md ${LAMBDA_TASK_ROOT}/README.md

ENV PYTHONPATH="${LAMBDA_TASK_ROOT}/src"

CMD [ "dibbs_text_to_code.main.handler" ]
