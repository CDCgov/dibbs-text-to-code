# Build client
FROM node:22-alpine3.22 AS client-builder

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

COPY ./requirements.txt /code/requirements.txt
RUN pip install -r requirements.txt

COPY ./packages/api/src/api /code/app
COPY ./packages/api/pyproject.toml /code/pyproject.toml
COPY --from=client-builder /frontend/dist /code/dist

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
