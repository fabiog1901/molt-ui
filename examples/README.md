# PostgreSQL Server to CockroachDB Migration Example

This directory contains the file to simulate a full migration from PG to CRDB.

## Setup

### Creating database objects and seeding Postgres tables

First, load the schema on PG

```bash
psql -d order_demo -f pg.order_demo.sql 
```

Then, you need to generate the CSV files using `dbworkload` given the provided YAML file.

```bash
dbworkload util csv \
  --input pg.seed.yaml \
  --output data \
  --procs 4
```

This will create a directory `data` in the current directory.

You can now import the csv files into PG

```bash
psql -d order_demo -f pg.import-data.sql 
```

At the end of the script, you should see the row count for each table

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

### DDL Review

When you review the tables, you will notice there are some complex data types that are currently not supported in CockroachDB.

We can work around by breaking down such datatypes into simpler datatypes.

```sql
ALTER TABLE order_demo.addresses
  ADD COLUMN coordinates_x DOUBLE PRECISION GENERATED ALWAYS AS (coordinates[0]) STORED,
  ADD COLUMN coordinates_y DOUBLE PRECISION GENERATED ALWAYS AS (coordinates[1]) STORED;

-- products.available_during  daterange -> two date columns
ALTER TABLE order_demo.products
  ADD COLUMN available_from DATE GENERATED ALWAYS AS (lower(available_during)) STORED,
  ADD COLUMN available_to   DATE GENERATED ALWAYS AS (upper(available_during)) STORED;

-- shipments.delivery_window  tstzrange -> two timestamptz columns
ALTER TABLE order_demo.shipments
  ADD COLUMN delivery_from TIMESTAMPTZ GENERATED ALWAYS AS (lower(delivery_window)) STORED,
  ADD COLUMN delivery_to   TIMESTAMPTZ GENERATED ALWAYS AS (upper(delivery_window)) STORED;
```

### Review CockroachDB converted schema.

Notice that there are 2 files:

- `crdb.pre-migration.sql`
- `crdb.post-migration.sql`

The pre-migration file lists only the most barebone schema:

- no secondary indexes
- no foreign keys
- no functions and triggers

We will add these back in the post-migration script.

Notice how at the end of the pre-migration script, we address the 3 unsupported datatypes by adding non-computed columns matching the PG computed column, and drop the original, unsupported column.

Molt will throw and error if it cannot find a corresponding column for the column we want to replace.

We need therefore a transformation file, `transformation.json`.

The file provides column exclusions for specific computed columns and for columns with complex datatypes.

## Test Run

Do a test run from the CLI, to confirm your setup is sound

```bash
./molt/molt fetch \
  --source='postgres://fabio:fabio@localhost:5432/order_demo' \
  --target='postgres://fabio:fabio@localhost:26257/order_demo?sslmode=require' \
  --bucket-path='s3://order-demo/' \
  --flatten-partitioned-tables \
  --table-handling none \
  --transformations-file 'transformations.json'
```
