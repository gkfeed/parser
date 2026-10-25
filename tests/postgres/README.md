# PostgreSQL contract checks

These integration checks use the schema and `gkfeed_parser` role prepared by
[`gkfeed/infra`](https://github.com/gkfeed/infra). They do not generate the schema
from parser models or run parser migrations. Broker responses come from a local
HTTP server.

Prepare an empty PostgreSQL database on a disposable PostgreSQL instance. Apply
the external migrations from an infra checkout with its pinned dbmate:

```sh
DATABASE_URL="$PARSER_CONTRACT_DATABASE_URL" make -C /path/to/infra migrate
DATABASE_URL="$PARSER_CONTRACT_DATABASE_URL" make -C /path/to/infra status
```

Set `PARSER_TEST_POSTGRES_URL` to the owner connection URL for that database, then
run from this repository:

```sh
make lint
make test
make test-integration FILE=tests/postgres
```

The test owner must be able to create databases, clone the migrated database,
and assume `gkfeed_parser`. The source database must have no active connections.
Each test creates a uniquely named database from that template and drops its
clone during cleanup. Database ACLs are reapplied because PostgreSQL does not
copy them from a template. Application calls use `SET ROLE gkfeed_parser` through
the connection settings. Only fixture setup and fault injection use owner
permissions. Never point these checks at a production server.

The suite checks the minimum migration registry, the read-only schema check,
eligibility query count, parser permissions, timestamps, deduplication, cascade
deletion, transaction rollback and retry, and a feed deleted during broker I/O.
Missing configuration and unmet prerequisites fail explicitly. There are no
skip or xfail paths. `make test` excludes these checks via the existing
`integration` marker.
