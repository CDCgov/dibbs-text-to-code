set working-directory := '../..'

alias u := up
alias d := down

[doc("Start only the project's core services with docker compose.")]
up *ARGS:
    docker compose -f {{ absolute_path('./docker-compose.yaml') }} up demo-site api-service opensearch-node {{ ARGS }}

[doc("Stop the project's core services with docker compose.")]
down *ARGS:
    docker compose -f {{ absolute_path('./docker-compose.yaml') }} down demo-site api-service opensearch-node -v {{ ARGS }}

[doc("Remove the project's core services and their volumes with docker compose.")]
rm:
    docker compose -f {{ absolute_path('./docker-compose.yaml') }} rm demo-site api-service opensearch-node -v
