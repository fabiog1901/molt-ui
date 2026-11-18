
\set ON_ERROR_STOP on
\connect postgres

DROP DATABASE IF EXISTS order_demo;
CREATE DATABASE order_demo;

\connect order_demo

BEGIN;

CREATE SCHEMA order_demo;
CREATE SCHEMA audit;
SET LOCAL search_path = order_demo, pg_catalog;

CREATE TYPE order_status AS ENUM ('pending', 'paid', 'shipped', 'completed', 'cancelled');
CREATE TYPE payment_status AS ENUM ('pending', 'captured', 'failed', 'refunded');

CREATE TABLE customers (
    customer_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id       uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    email             varchar(254) NOT NULL,
    full_name         text NOT NULL,
    date_of_birth     date,
    is_active         boolean NOT NULL DEFAULT true,
    loyalty_points    integer NOT NULL DEFAULT 0 CHECK (loyalty_points >= 0),
    preferences       jsonb NOT NULL DEFAULT '{}'::jsonb
                      CHECK (jsonb_typeof(preferences) = 'object'),
    tags              text[] NOT NULL DEFAULT '{}'::text[],
    last_login_ip     inet,
    created_at        timestamptz NOT NULL DEFAULT current_timestamp
);

CREATE UNIQUE INDEX customers_email_lower_idx ON customers (lower(email));
CREATE INDEX customers_preferences_idx ON customers USING gin (preferences);

CREATE TABLE addresses (
    address_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id       bigint NOT NULL REFERENCES customers (customer_id),
    recipient         text NOT NULL,
    street            text NOT NULL,
    city              text NOT NULL,
    region            text,
    postal_code       varchar(20) NOT NULL,
    country_code      varchar(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    coordinates       point, -- Longitude, latitude; native point, not PostGIS.
    delivery_notes    text,
    is_default        boolean NOT NULL DEFAULT false,
    UNIQUE (address_id, customer_id)
);

CREATE INDEX addresses_customer_idx ON addresses (customer_id);
CREATE UNIQUE INDEX addresses_one_default_idx ON addresses (customer_id) WHERE is_default;

CREATE TABLE categories (
    category_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_category_id bigint REFERENCES categories (category_id),
    name               text NOT NULL,
    slug               text NOT NULL UNIQUE,
    CHECK (parent_category_id IS DISTINCT FROM category_id)
);

CREATE INDEX categories_parent_idx ON categories (parent_category_id);

CREATE TABLE products (
    product_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_id       bigint NOT NULL REFERENCES categories (category_id),
    sku               varchar(64) NOT NULL UNIQUE,
    name              text NOT NULL,
    description       text NOT NULL DEFAULT '',
    price             numeric(12,2) NOT NULL CHECK (price >= 0),
    weight_kg         double precision CHECK (weight_kg > 0),
    stock_quantity    integer NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    attributes        jsonb NOT NULL DEFAULT '{}'::jsonb
                      CHECK (jsonb_typeof(attributes) = 'object'),
    tags              text[] NOT NULL DEFAULT '{}'::text[],
    available_during  daterange NOT NULL DEFAULT daterange(NULL, NULL, '[)')
                      CHECK (NOT isempty(available_during)),
    image_digest      bytea CHECK (octet_length(image_digest) = 32),
    search_document   tsvector GENERATED ALWAYS AS
                      (to_tsvector('english'::regconfig, name || ' ' || description)) STORED,
    created_at        timestamptz NOT NULL DEFAULT current_timestamp
);

CREATE INDEX products_category_idx ON products (category_id);
CREATE INDEX products_attributes_idx ON products USING gin (attributes);
CREATE INDEX products_tags_idx ON products USING gin (tags);
CREATE INDEX products_search_idx ON products USING gin (search_document);
CREATE INDEX products_availability_idx ON products USING gist (available_during);

-- Hashing the primary key distributes orders over 16 partitions regardless of date.
-- The partition key is included in every primary/unique constraint on this table.
CREATE TABLE orders (
    order_id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id          bigint NOT NULL REFERENCES customers (customer_id),
    shipping_address_id  bigint NOT NULL,
    status               order_status NOT NULL DEFAULT 'pending',
    placed_at            timestamptz NOT NULL DEFAULT current_timestamp,
    paid_at              timestamptz,
    subtotal             numeric(14,2) NOT NULL CHECK (subtotal >= 0),
    tax                  numeric(14,2) NOT NULL DEFAULT 0 CHECK (tax >= 0),
    shipping_fee         numeric(14,2) NOT NULL DEFAULT 0 CHECK (shipping_fee >= 0),
    total                numeric(14,2) GENERATED ALWAYS AS (subtotal + tax + shipping_fee) STORED,
    metadata             jsonb NOT NULL DEFAULT '{}'::jsonb
                         CHECK (jsonb_typeof(metadata) = 'object'),
    shipping_snapshot    jsonb NOT NULL CHECK (jsonb_typeof(shipping_snapshot) = 'object'),
    FOREIGN KEY (shipping_address_id, customer_id)
        REFERENCES addresses (address_id, customer_id),
    CHECK (paid_at IS NULL OR paid_at >= placed_at)
) PARTITION BY HASH (order_id);

CREATE TABLE order_demo.orders_p00 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 0);
CREATE TABLE order_demo.orders_p01 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 1);
CREATE TABLE order_demo.orders_p02 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 2);
CREATE TABLE order_demo.orders_p03 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 3);
CREATE TABLE order_demo.orders_p04 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 4);
CREATE TABLE order_demo.orders_p05 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 5);
CREATE TABLE order_demo.orders_p06 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 6);
CREATE TABLE order_demo.orders_p07 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 7);
CREATE TABLE order_demo.orders_p08 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 8);
CREATE TABLE order_demo.orders_p09 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 9);
CREATE TABLE order_demo.orders_p10 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 10);
CREATE TABLE order_demo.orders_p11 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 11);
CREATE TABLE order_demo.orders_p12 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 12);
CREATE TABLE order_demo.orders_p13 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 13);
CREATE TABLE order_demo.orders_p14 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 14);
CREATE TABLE order_demo.orders_p15 PARTITION OF order_demo.orders
    FOR VALUES WITH (MODULUS 16, REMAINDER 15);

-- Indexes declared on the parent are created on each partition.
CREATE INDEX orders_customer_placed_idx ON orders (customer_id, placed_at DESC);
CREATE INDEX orders_address_customer_idx ON orders (shipping_address_id, customer_id);
CREATE INDEX orders_open_idx ON orders (placed_at) WHERE status = 'pending';
CREATE INDEX orders_metadata_idx ON orders USING gin (metadata);

CREATE TABLE order_items (
    order_id          bigint NOT NULL REFERENCES orders (order_id),
    line_number       smallint NOT NULL CHECK (line_number > 0),
    product_id        bigint NOT NULL REFERENCES products (product_id),
    quantity          integer NOT NULL CHECK (quantity > 0),
    unit_price        numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    discount          numeric(12,2) NOT NULL DEFAULT 0 CHECK (discount >= 0),
    line_total        numeric(14,2) GENERATED ALWAYS AS (quantity * unit_price - discount) STORED,
    options           jsonb NOT NULL DEFAULT '{}'::jsonb
                      CHECK (jsonb_typeof(options) = 'object'),
    PRIMARY KEY (order_id, line_number),
    CHECK (discount <= quantity * unit_price)
);

CREATE INDEX order_items_product_idx ON order_items (product_id);

CREATE TABLE payments (
    payment_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id          bigint NOT NULL REFERENCES orders (order_id),
    status            payment_status NOT NULL DEFAULT 'pending',
    method            text NOT NULL CHECK (method IN ('card', 'bank_transfer', 'wallet')),
    amount            numeric(14,2) NOT NULL CHECK (amount > 0),
    provider_reference text UNIQUE,
    provider_response jsonb,
    created_at        timestamptz NOT NULL DEFAULT current_timestamp,
    captured_at       timestamptz,
    CHECK (captured_at IS NULL OR captured_at >= created_at)
);

CREATE INDEX payments_order_idx ON payments (order_id);

CREATE TABLE shipments (
    shipment_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id          bigint NOT NULL REFERENCES orders (order_id),
    carrier           text NOT NULL,
    tracking_number   text NOT NULL,
    shipped_at        timestamptz,
    delivered_at      timestamptz,
    delivery_window   tstzrange CHECK (NOT isempty(delivery_window)),
    estimated_transit interval CHECK (estimated_transit > interval '0 seconds'),
    package_weight_kg real CHECK (package_weight_kg > 0),
    tracking_events   jsonb NOT NULL DEFAULT '[]'::jsonb
                      CHECK (jsonb_typeof(tracking_events) = 'array'),
    UNIQUE (carrier, tracking_number),
    CHECK (delivered_at IS NULL OR (shipped_at IS NOT NULL AND delivered_at >= shipped_at))
);

CREATE INDEX shipments_order_idx ON shipments (order_id);
CREATE INDEX shipments_delivery_window_idx ON shipments USING gist (delivery_window);

-- Reference/master data update history. These tables tend to change less often
-- than orders and order_items, though stock_quantity and loyalty_points can be hot.
-- No foreign key back to the source row: history can survive a later row deletion.
CREATE TABLE audit.audit_event (
    event_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at       timestamptz NOT NULL DEFAULT clock_timestamp(),
    transaction_id    bigint NOT NULL DEFAULT txid_current(),
    session_actor     text NOT NULL DEFAULT session_user,
    effective_actor   text NOT NULL DEFAULT current_user,
    application_name  text NOT NULL DEFAULT current_setting('application_name'),
    table_schema      text NOT NULL,
    table_name        text NOT NULL,
    operation         text NOT NULL CHECK (operation = 'UPDATE'),
    row_key           jsonb NOT NULL,
    changed_columns   text[] NOT NULL CHECK (cardinality(changed_columns) > 0),
    old_row           jsonb NOT NULL,
    new_row           jsonb NOT NULL
);

CREATE INDEX audit_event_table_time_idx
    ON audit.audit_event (table_schema, table_name, occurred_at DESC);
CREATE INDEX audit_event_row_key_idx ON audit.audit_event USING gin (row_key);

CREATE FUNCTION audit.log_dimension_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
DECLARE
    before_row jsonb := to_jsonb(OLD);
    after_row  jsonb := to_jsonb(NEW);
BEGIN
    -- Compare JSONB rather than records: native point has no equality operator.
    -- This also handles SQL NULL values and generated product search_document.
    IF before_row IS NOT DISTINCT FROM after_row THEN
        RETURN NULL;
    END IF;

    INSERT INTO audit.audit_event (
        table_schema, table_name, operation, row_key,
        changed_columns, old_row, new_row
    )
    VALUES (
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP,
        jsonb_build_object(TG_ARGV[0], after_row -> TG_ARGV[0]),
        ARRAY(
            SELECT entry.key
            FROM jsonb_each(after_row) AS entry
            WHERE entry.value IS DISTINCT FROM (before_row -> entry.key)
            ORDER BY entry.key
        ),
        before_row, after_row
    );

    RETURN NULL; -- Return value is ignored for AFTER triggers.
END;
$$;

CREATE TRIGGER audit_customer_update
AFTER UPDATE ON order_demo.customers
FOR EACH ROW EXECUTE FUNCTION audit.log_dimension_update('customer_id');

CREATE TRIGGER audit_address_update
AFTER UPDATE ON order_demo.addresses
FOR EACH ROW EXECUTE FUNCTION audit.log_dimension_update('address_id');

CREATE TRIGGER audit_category_update
AFTER UPDATE ON order_demo.categories
FOR EACH ROW EXECUTE FUNCTION audit.log_dimension_update('category_id');

CREATE TRIGGER audit_product_update
AFTER UPDATE ON order_demo.products
FOR EACH ROW EXECUTE FUNCTION audit.log_dimension_update('product_id');

-- Audit inserts share the updating transaction, including rollback behavior.
-- Application roles need USAGE on audit, INSERT on audit.audit_event, and
-- USAGE on audit.audit_event_event_id_seq because the function uses invoker rights.
COMMENT ON SCHEMA audit IS 'Row update history for order_demo reference tables';
COMMENT ON TABLE audit.audit_event IS 'One event per changed reference row; rolled-back updates leave no event';

COMMENT ON SCHEMA order_demo IS 'Order transaction datatype and partitioning demonstration';
COMMENT ON COLUMN orders.subtotal IS 'Application maintains this as the sum of order item line totals';
COMMENT ON COLUMN orders.shipping_snapshot IS 'Immutable address copy captured by the application at checkout';
COMMENT ON COLUMN order_items.unit_price IS 'Price captured at checkout, independent of later catalog changes';
COMMENT ON COLUMN products.image_digest IS 'Optional SHA-256 digest (32 bytes)';

COMMIT;
