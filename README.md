# sender

Logs in to Embasa's [Atendimento Virtual](https://atendimentovirtual.embasa.ba.gov.br/login?redirect=/carta-de-servico-segunda-via),
downloads the "2ª via" PDF of every bill of every matrícula of each configured
user, and emails it. Each bill (user + matrícula + referência) is recorded in
SQLite once the email is accepted, so it is never sent twice. Runs in Docker and
checks once a day.

## Setup

```sh
cp .env.example .env        # fill in the SMTP settings
docker compose build

# add as many users as needed (password is prompted)
docker compose run --rm sender add-user --cpf 123.456.789-09 --email someone@example.com

# see what would be sent, without sending or recording anything
docker compose run --rm sender run-once --dry-run

docker compose up -d        # checks on start and then every day at RUN_AT
docker compose logs -f
```

## Commands

`docker compose run --rm sender <command>`

| Command | |
| --- | --- |
| `serve` | daily loop (container default) |
| `run-once [--dry-run] [--cpf CPF]` | check now |
| `add-user --cpf CPF --email A[,B] [--password P]` | add or update a user |
| `disable-user` / `enable-user` / `remove-user --cpf CPF` | |
| `list-users`, `list-sent [--limit N]` | |

The database lives in `./data/embasa.db`. Portal passwords are stored there in
plain text (they have to be replayed to the portal), so keep that directory private.
Set `LOG_LEVEL=DEBUG` to log the portal's raw API responses.
