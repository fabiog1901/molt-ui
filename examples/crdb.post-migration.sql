SET search_path = order_demo, pg_catalog;

-- Apply once after migrating data into order_demo-slim.sql.
-- Run with psql -v ON_ERROR_STOP=1, or cockroach sql (stops on errors).
-- Unique constraints/indexes and foreign keys validate the already-loaded rows.
-- Statements run separately: if one fails, earlier completed changes remain.

-- 1. Restore the six unique constraints and their backing secondary indexes.
ALTER TABLE order_demo.customers
  ADD CONSTRAINT customers_external_id_key UNIQUE (external_id);

ALTER TABLE order_demo.addresses
  ADD CONSTRAINT addresses_address_id_customer_id_key UNIQUE (address_id, customer_id);

ALTER TABLE order_demo.categories
  ADD CONSTRAINT categories_slug_key UNIQUE (slug);

ALTER TABLE order_demo.products
  ADD CONSTRAINT products_sku_key UNIQUE (sku);

ALTER TABLE order_demo.payments
  ADD CONSTRAINT payments_provider_reference_key UNIQUE (provider_reference);

ALTER TABLE order_demo.shipments
  ADD CONSTRAINT shipments_carrier_tracking_number_key UNIQUE (carrier, tracking_number);

-- 2. Build the 20 explicitly defined secondary indexes before adding FKs.
-- Referencing-column indexes are available before FK creation, avoiding redundant
-- automatic FK indexes. Range columns are strings: these are text lookup indexes.
CREATE UNIQUE INDEX customers_email_lower_idx ON order_demo.customers (lower(email));

CREATE INVERTED INDEX customers_preferences_idx ON order_demo.customers (preferences);

CREATE INDEX addresses_customer_idx ON order_demo.addresses (customer_id);

CREATE UNIQUE INDEX addresses_one_default_idx ON order_demo.addresses (customer_id) WHERE is_default;

CREATE INDEX categories_parent_idx ON order_demo.categories (parent_category_id);

CREATE INDEX products_category_idx ON order_demo.products (category_id);

CREATE INVERTED INDEX products_attributes_idx ON order_demo.products (attributes);

CREATE INVERTED INDEX products_tags_idx ON order_demo.products (tags);

CREATE INVERTED INDEX products_search_idx ON order_demo.products (search_document);

CREATE INDEX products_availability_idx ON order_demo.products (available_from, available_to);

CREATE INDEX orders_customer_placed_idx ON order_demo.orders (customer_id, placed_at DESC);

CREATE INDEX orders_address_customer_idx ON order_demo.orders (shipping_address_id, customer_id);

CREATE INDEX orders_open_idx ON order_demo.orders (placed_at) WHERE status = 'pending';

CREATE INVERTED INDEX orders_metadata_idx ON order_demo.orders (metadata);

CREATE INDEX order_items_product_idx ON order_demo.order_items (product_id);

CREATE INDEX payments_order_idx ON order_demo.payments (order_id);

CREATE INDEX shipments_order_idx ON order_demo.shipments (order_id);

CREATE INDEX shipments_delivery_window_idx ON order_demo.shipments (delivery_from, delivery_to);

CREATE INDEX audit_event_table_time_idx ON audit.audit_event (
	table_schema,
	table_name,
	occurred_at DESC
);

CREATE INVERTED INDEX audit_event_row_key_idx ON audit.audit_event (row_key);

-- 3. Restore all nine foreign keys, validating existing references.
ALTER TABLE order_demo.addresses
  ADD CONSTRAINT addresses_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES order_demo.customers (customer_id);

ALTER TABLE order_demo.categories
  ADD CONSTRAINT categories_parent_category_id_fkey
  FOREIGN KEY (parent_category_id) REFERENCES order_demo.categories (category_id);

ALTER TABLE order_demo.products
  ADD CONSTRAINT products_category_id_fkey
  FOREIGN KEY (category_id) REFERENCES order_demo.categories (category_id);

ALTER TABLE order_demo.orders
  ADD CONSTRAINT orders_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES order_demo.customers (customer_id);

ALTER TABLE order_demo.orders
  ADD CONSTRAINT orders_shipping_address_id_customer_id_fkey
  FOREIGN KEY (shipping_address_id, customer_id)
  REFERENCES order_demo.addresses (address_id, customer_id);

ALTER TABLE order_demo.order_items
  ADD CONSTRAINT order_items_order_id_fkey
  FOREIGN KEY (order_id) REFERENCES order_demo.orders (order_id);

ALTER TABLE order_demo.order_items
  ADD CONSTRAINT order_items_product_id_fkey
  FOREIGN KEY (product_id) REFERENCES order_demo.products (product_id);

ALTER TABLE order_demo.payments
  ADD CONSTRAINT payments_order_id_fkey
  FOREIGN KEY (order_id) REFERENCES order_demo.orders (order_id);

ALTER TABLE order_demo.shipments
  ADD CONSTRAINT shipments_order_id_fkey
  FOREIGN KEY (order_id) REFERENCES order_demo.orders (order_id);

-- 4. Install the audit function and its four UPDATE triggers after bulk loading.
-- Imported audit history is retained. New audit events begin with subsequent
-- updates; their PostgreSQL transaction_id is NULL and transaction_started_at
-- records the CockroachDB transaction start time.
CREATE FUNCTION audit.log_dimension_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER AS
$$
DECLARE key_column text := CASE
	TG_TABLE_NAME
	WHEN 'customers' THEN 'customer_id'
	WHEN 'addresses' THEN 'address_id'
	WHEN 'categories' THEN 'category_id'
	WHEN 'products' THEN 'product_id'
END;

before_row jsonb := pg_catalog.to_jsonb(OLD);

after_row jsonb := pg_catalog.to_jsonb(NEW);

BEGIN -- Compare JSONB snapshots to detect actual row changes.
-- This also handles SQL NULL values and generated product search_document.
IF before_row IS NOT DISTINCT
FROM
	after_row THEN RETURN NULL;

END IF;

INSERT INTO
	audit.audit_event (
		table_schema,
		table_name,
		operation,
		row_key,
		changed_columns,
		old_row,
		new_row
	)
VALUES
	(
		TG_TABLE_SCHEMA,
		TG_TABLE_NAME,
		TG_OP,
		pg_catalog.jsonb_build_object(key_column, after_row -> key_column),
		ARRAY(
			SELECT
				entry.key
			FROM
				pg_catalog.jsonb_each(after_row) AS entry
			WHERE
				entry.value IS DISTINCT
			FROM
				(before_row -> entry.key)
			ORDER BY
				entry.key
		),
		before_row,
		after_row
	);

RETURN NULL;

-- Return value is ignored for AFTER triggers.
END;

$$;

CREATE TRIGGER audit_customer_update
AFTER
UPDATE
	ON order_demo.customers FOR EACH ROW EXECUTE FUNCTION audit.log_dimension_update();

CREATE TRIGGER audit_address_update
AFTER
UPDATE
	ON order_demo.addresses FOR EACH ROW EXECUTE FUNCTION audit.log_dimension_update();

CREATE TRIGGER audit_category_update
AFTER
UPDATE
	ON order_demo.categories FOR EACH ROW EXECUTE FUNCTION audit.log_dimension_update();

CREATE TRIGGER audit_product_update
AFTER
UPDATE
	ON order_demo.products FOR EACH ROW EXECUTE FUNCTION audit.log_dimension_update();

-- 5. Restore schema, table and column documentation.
COMMENT ON SCHEMA audit IS 'Row update history for order_demo reference tables';

COMMENT ON TABLE audit.audit_event IS 'One event per changed reference row; rolled-back updates leave no event';

COMMENT ON SCHEMA order_demo IS 'Order transaction datatype and partitioning demonstration';

COMMENT ON COLUMN order_demo.orders.subtotal IS 'Application maintains this as the sum of order item line totals';

COMMENT ON COLUMN order_demo.orders.shipping_snapshot IS 'Immutable address copy captured by the application at checkout';

COMMENT ON COLUMN order_demo.order_items.unit_price IS 'Price captured at checkout, independent of later catalog changes';

COMMENT ON COLUMN order_demo.products.image_digest IS 'Optional SHA-256 digest (32 bytes)';
