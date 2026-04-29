# Running `transform()` Locally

## Example Implementation

The below is only an example, you will likely to wish to alter is as required. Highlight any additional Python library requirements.

```
import logging
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass

from nxd.core.context import API, PgVector, SecretString
from transform import transform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


if __name__ == "__main__":
    jira_api = API(
        _inner={
            "url": _require("JIRA_URL"),
            "username": _require("JIRA_USERNAME"),
            "token": _require("JIRA_TOKEN"),
        }
    )

    pg_table = os.environ.get("PG_TABLE", "jira_embeddings")
    pg_schema = os.environ.get("PG_SCHEMA", "engineering")

    pgvector = PgVector(
        host=_require("PG_HOST"),
        port=int(os.environ.get("PG_PORT", "5432")),
        user=_require("PG_USER"),
        secret_password=SecretString(_require("PG_PASSWORD")),
        database=_require("PG_DATABASE"),
        schema=pg_schema,
        model_tables={"jira_embeddings": pg_table},
        models={},
    )

    transform(jira_api, pgvector)
```