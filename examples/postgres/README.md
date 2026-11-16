# PostgreSQL order demo

This example contains the `order_demo` and `audit` schemas, eight order-related
tables, an audit event table, and 16 hash partitions for orders. Updates to
customers, addresses, categories, and products generate audit events.

Run the commands below from this directory:

```bash
cd examples/postgres
```

You need PostgreSQL client tools (`psql`, `createdb`, `pg_dump`, and `pg_restore`)
and dbworkload for data generation. Add `-h HOST -U USER` to PostgreSQL commands
when connecting to another host or as another user. Use a `pg_dump` client whose
major version matches your PostgreSQL server.

## Create the database and tables

Skip database creation if `order_demo` already exists:

```bash
createdb order_demo
```

Apply the DDL once to create the schemas, tables, indexes, constraints, function,
and triggers:

```bash
psql -X -d order_demo -v ON_ERROR_STOP=1 -f order_demo.sql
```

The DDL intentionally fails if either schema already exists.

## Generate seed files

Skip this step if you already generated the files in `order_demo/`.

```bash
dbworkload util csv \
  --input order_demo.seed.yaml \
  --output order_demo \
  --procs 4 \
  --csv-max-rows 100000
```

The current import script matches the four-worker output above, including all
chunks and all three order-item batches. Changing the worker count, chunk size,
or dataset size can change filenames and requires updating the import script.
The actual row counts are configured in the YAML `count` fields.

The generated `.tsv` files use CSV quoting with a tab delimiter, no header, and
empty fields for SQL NULL. Ignore dbworkload's printed `IMPORT INTO` statements;
use the PostgreSQL import script below.

### Sampling

Most descriptive fields use seeded `choice` generators with pools of 32 values:
names, streets, locations, delivery notes, product descriptions and attributes,
timestamps, and transaction amounts. Address city, region, postal code, country,
and coordinates share a seed and aligned populations so they form consistent
locations. Customer names and address recipients also use matching samples.

Order items, order totals, and payments share 32 monetary profiles. Their seeds
and population order keep quantities, prices, discounts, subtotals, taxes, and
payment amounts consistent. Order, payment, and shipment dates use another set
of 32 aligned profiles to preserve event chronology. Keep the process count and
row counts equal across the related transaction tables and item batches when
generating data. Keep `sort-by` empty to preserve these relationships.

Order shipping snapshots sample historical addresses independently; they may
differ from a customer's current address. The remaining constants preserve
specific semantics: completed orders, captured payments, one default address
per customer, root categories with NULL parents, and item line numbers 1–3.

Changing the YAML affects newly generated files only. To use the revised samples,
regenerate the TSV files and import into a fresh database using the steps above;
existing database rows and backups are unaffected.

## Import the seed files

Run from this directory so the script can find its relative `order_demo/` paths:

```bash
psql -X -d order_demo -f import_order_demo.sql
```

The script requires empty order tables. It loads files through client-side
`\copy` in foreign-key dependency order, including all three order-item batches,
and resets identity sequences. Data loading runs in one transaction and stops on
the first error. It then refreshes planner statistics and prints row counts.

Generated columns are calculated by PostgreSQL. Orders are routed to their
partitions automatically. The audit table starts empty and fills when reference
rows are updated.

When the command completes, you should see the total row count per table:

```sql
       table_name       | row_count 
------------------------+-----------
 audit.audit_event      |         0
 order_demo.addresses   |     10000
 order_demo.categories  |        12
 order_demo.customers   |     10000
 order_demo.order_items |   3000000
 order_demo.orders      |   1000000
 order_demo.payments    |   1000000
 order_demo.products    |       250
 order_demo.shipments   |   1000000
```

## Back up the database

Create a compressed custom-format backup:

```bash
pg_dump -d order_demo -Fc -f order_demo.dump
```

This includes both schemas, data, partitions, indexes, constraints, functions,
triggers, and sequence values. It does not include cluster-wide roles. Choose a
different output filename to keep an earlier backup; `-f` replaces an existing file.

Optionally inspect the archive contents:

```bash
pg_restore --list order_demo.dump
```

## Restore into a new database

Create an empty database and restore the backup into it:

```bash
createdb -T template0 order_demo_restored

pg_restore \
  -d order_demo_restored \
  --no-owner --no-acl \
  --single-transaction \
  order_demo.dump

psql -X -d order_demo_restored -v ON_ERROR_STOP=1 -c 'ANALYZE;'
```

This preserves the original `order_demo` database and lets you test the backup.
The destination must be new and empty; do not apply the DDL or import seed files
before restoring. `--single-transaction` stops and rolls back the restore if an
error occurs. `--no-owner --no-acl` restores objects under the restoring user
without applying the original ownership or permissions.

To restore under another database name, replace `order_demo_restored` in these
commands. The schemas inside the database remain named `order_demo` and `audit`.

## References

- [PostgreSQL psql and client-side copy](https://www.postgresql.org/docs/current/app-psql.html#APP-PSQL-META-COMMAND-COPY)
- [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
- [PostgreSQL pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html)
