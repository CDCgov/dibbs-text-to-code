# Build client
FROM node:25-alpine3.22 AS client-builder

WORKDIR /src

# install git to capture hash
RUN apk add --no-cache git
COPY .git .git

# Copy workspace root package files first
COPY package*.json ./

# Copy frontend workspace package files
COPY ./frontend/package*.json ./frontend/
RUN npm ci

# Copy the entire frontend directory
COPY ./frontend ./frontend/

# Build from the frontend workspace
WORKDIR /src/frontend
RUN npm run build

# Package production app
FROM python:3.14-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get upgrade -y

RUN pip install --upgrade pip  --break-system-packages

WORKDIR /code

COPY ./packages/api/src/api /code/app
COPY ./packages/api/pyproject.toml /code/pyproject.toml

# Create a requirements.txt from the pyproject.toml
RUN uv pip compile /code/pyproject.toml -o /code/requirements.txt
RUN pip install -r requirements.txt

COPY --from=client-builder /src/frontend/dist /code/dist

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
