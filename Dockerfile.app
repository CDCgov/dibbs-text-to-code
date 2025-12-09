# Build client
FROM node:22-alpine3.22 AS client-builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /src

# install git to capture hash
RUN apk add --no-cache git
COPY .git .git

COPY ./frontend/package*.json ./
RUN npm install

COPY ./frontend ./

RUN npm run build

# Package production app
FROM python:3.12-slim

RUN apt-get update && \
    apt-get upgrade -y

RUN pip install --upgrade pip  --break-system-packages

WORKDIR /code

COPY ./packages/api/src/api /code/app
COPY ./packages/api/pyproject.toml /code/pyproject.toml

# Create a requirements.txt from the pyproject.toml
RUN uv pip compile /code/pyproject.toml -o /code/requirements.txt
RUN pip install -r requirements.txt

COPY --from=client-builder /frontend/dist /code/dist

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
