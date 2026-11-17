-- Load the existing dbworkload TSV shards into PostgreSQL.
-- Run from examples/postgres after applying order_demo.sql:
--   psql -X -d order_demo -f import_order_demo.sql
-- Matches the current 4-worker TSV files in order_demo/, including all chunks.
-- Regenerating with a different worker count or chunk size changes filenames.
-- TSV uses CSV quoting, tab delimiters, no header and empty fields for NULL.
\set ON_ERROR_STOP on

BEGIN;
SET LOCAL TIME ZONE 'UTC';

-- Keep the seed import exclusive and refuse to append to existing data.
LOCK TABLE order_demo.customers, order_demo.addresses, order_demo.categories, order_demo.products, order_demo.orders, order_demo.order_items, order_demo.payments, order_demo.shipments IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT FROM order_demo.customers)
       OR EXISTS (SELECT FROM order_demo.addresses)
       OR EXISTS (SELECT FROM order_demo.categories)
       OR EXISTS (SELECT FROM order_demo.products)
       OR EXISTS (SELECT FROM order_demo.orders)
       OR EXISTS (SELECT FROM order_demo.order_items)
       OR EXISTS (SELECT FROM order_demo.payments)
       OR EXISTS (SELECT FROM order_demo.shipments) THEN
        RAISE EXCEPTION 'Seed import requires empty order_demo tables';
    END IF;
END;
$$;

\echo Loading order_demo.customers
\copy order_demo.customers (customer_id, external_id, email, full_name, date_of_birth, is_active, loyalty_points, preferences, tags, last_login_ip, created_at) FROM 'order_demo/order_demo__customers.0_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.customers (customer_id, external_id, email, full_name, date_of_birth, is_active, loyalty_points, preferences, tags, last_login_ip, created_at) FROM 'order_demo/order_demo__customers.0_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.customers (customer_id, external_id, email, full_name, date_of_birth, is_active, loyalty_points, preferences, tags, last_login_ip, created_at) FROM 'order_demo/order_demo__customers.0_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.customers (customer_id, external_id, email, full_name, date_of_birth, is_active, loyalty_points, preferences, tags, last_login_ip, created_at) FROM 'order_demo/order_demo__customers.0_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')

\echo Loading order_demo.addresses
\copy order_demo.addresses (address_id, customer_id, recipient, street, city, region, postal_code, country_code, coordinates, delivery_notes, is_default) FROM 'order_demo/order_demo__addresses.0_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.addresses (address_id, customer_id, recipient, street, city, region, postal_code, country_code, coordinates, delivery_notes, is_default) FROM 'order_demo/order_demo__addresses.0_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.addresses (address_id, customer_id, recipient, street, city, region, postal_code, country_code, coordinates, delivery_notes, is_default) FROM 'order_demo/order_demo__addresses.0_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.addresses (address_id, customer_id, recipient, street, city, region, postal_code, country_code, coordinates, delivery_notes, is_default) FROM 'order_demo/order_demo__addresses.0_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')

\echo Loading order_demo.categories
\copy order_demo.categories (category_id, parent_category_id, name, slug) FROM 'order_demo/order_demo__categories.0_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.categories (category_id, parent_category_id, name, slug) FROM 'order_demo/order_demo__categories.0_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.categories (category_id, parent_category_id, name, slug) FROM 'order_demo/order_demo__categories.0_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.categories (category_id, parent_category_id, name, slug) FROM 'order_demo/order_demo__categories.0_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')

\echo Loading order_demo.products
\copy order_demo.products (product_id, category_id, sku, name, description, price, weight_kg, stock_quantity, attributes, tags, available_during, image_digest, created_at) FROM 'order_demo/order_demo__products.0_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.products (product_id, category_id, sku, name, description, price, weight_kg, stock_quantity, attributes, tags, available_during, image_digest, created_at) FROM 'order_demo/order_demo__products.0_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.products (product_id, category_id, sku, name, description, price, weight_kg, stock_quantity, attributes, tags, available_during, image_digest, created_at) FROM 'order_demo/order_demo__products.0_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.products (product_id, category_id, sku, name, description, price, weight_kg, stock_quantity, attributes, tags, available_during, image_digest, created_at) FROM 'order_demo/order_demo__products.0_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')

\echo Loading order_demo.orders
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_0_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_0_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_1_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_1_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_2_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_2_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_3_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.orders (order_id, customer_id, shipping_address_id, status, placed_at, paid_at, subtotal, tax, shipping_fee, metadata, shipping_snapshot) FROM 'order_demo/order_demo__orders.0_3_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')

\echo Loading order_demo.order_items
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_0_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_0_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_1_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_1_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_2_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_2_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_3_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.0_3_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_0_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_0_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_1_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_1_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_2_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_2_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_3_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.1_3_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_0_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_0_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_1_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_1_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_2_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_2_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_3_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.order_items (order_id, line_number, product_id, quantity, unit_price, discount, options) FROM 'order_demo/order_demo__order_items.2_3_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')

\echo Loading order_demo.payments
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_0_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_0_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_1_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_1_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_2_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_2_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_3_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.payments (payment_id, order_id, status, method, amount, provider_reference, provider_response, created_at, captured_at) FROM 'order_demo/order_demo__payments.0_3_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')

\echo Loading order_demo.shipments
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_0_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_0_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_0_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_1_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_1_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_1_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_2_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_2_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_2_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_3_0.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_3_1.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')
\copy order_demo.shipments (shipment_id, order_id, carrier, tracking_number, shipped_at, delivered_at, delivery_window, estimated_transit, package_weight_kg, tracking_events) FROM 'order_demo/order_demo__shipments.0_3_2.tsv' WITH (FORMAT csv, DELIMITER E'\t', NULL '', ENCODING 'UTF8')

\echo Loading audit.audit_event sample history
-- Synthetic UPDATE history: ten events for each reference table (40 total).
-- Use existing rows for complete, correctly typed snapshots. Only the snapshots
-- differ; these INSERTs do not change the reference rows or invoke their triggers.
-- This block can also be run separately against an already populated demo.
INSERT INTO audit.audit_event (
    occurred_at, application_name, table_schema, table_name, operation,
    row_key, changed_columns, old_row, new_row
)
SELECT current_timestamp - row_number() OVER (ORDER BY c.customer_id) * interval '1 minute',
       'order-demo-seed', 'order_demo', 'customers', 'UPDATE',
       jsonb_build_object('customer_id', c.customer_id), ARRAY['full_name'],
       to_jsonb(c) || jsonb_build_object('full_name', 'Previous ' || c.full_name),
       to_jsonb(c)
FROM (SELECT * FROM order_demo.customers ORDER BY customer_id LIMIT 10) AS c;

INSERT INTO audit.audit_event (
    occurred_at, application_name, table_schema, table_name, operation,
    row_key, changed_columns, old_row, new_row
)
SELECT current_timestamp - (10 + row_number() OVER (ORDER BY a.address_id)) * interval '1 minute',
       'order-demo-seed', 'order_demo', 'addresses', 'UPDATE',
       jsonb_build_object('address_id', a.address_id), ARRAY['delivery_notes'],
       to_jsonb(a) || jsonb_build_object('delivery_notes', 'Previous: ' || coalesce(a.delivery_notes, '')),
       to_jsonb(a)
FROM (SELECT * FROM order_demo.addresses ORDER BY address_id LIMIT 10) AS a;

INSERT INTO audit.audit_event (
    occurred_at, application_name, table_schema, table_name, operation,
    row_key, changed_columns, old_row, new_row
)
SELECT current_timestamp - (20 + row_number() OVER (ORDER BY c.category_id)) * interval '1 minute',
       'order-demo-seed', 'order_demo', 'categories', 'UPDATE',
       jsonb_build_object('category_id', c.category_id), ARRAY['name'],
       to_jsonb(c) || jsonb_build_object('name', 'Previous ' || c.name),
       to_jsonb(c)
FROM (SELECT * FROM order_demo.categories ORDER BY category_id LIMIT 10) AS c;

INSERT INTO audit.audit_event (
    occurred_at, application_name, table_schema, table_name, operation,
    row_key, changed_columns, old_row, new_row
)
SELECT current_timestamp - (30 + row_number() OVER (ORDER BY p.product_id)) * interval '1 minute',
       'order-demo-seed', 'order_demo', 'products', 'UPDATE',
       jsonb_build_object('product_id', p.product_id), ARRAY['price'],
       to_jsonb(p) || jsonb_build_object('price', p.price + 1.00),
       to_jsonb(p)
FROM (SELECT * FROM order_demo.products ORDER BY product_id LIMIT 10) AS p;

-- COPY supplies identity values without advancing their sequences.
-- Audit INSERTs use generated IDs, so their sequence advances automatically.
SELECT setval(pg_get_serial_sequence('order_demo.customers', 'customer_id'), max(customer_id), true) FROM order_demo.customers;
SELECT setval(pg_get_serial_sequence('order_demo.addresses', 'address_id'), max(address_id), true) FROM order_demo.addresses;
SELECT setval(pg_get_serial_sequence('order_demo.categories', 'category_id'), max(category_id), true) FROM order_demo.categories;
SELECT setval(pg_get_serial_sequence('order_demo.products', 'product_id'), max(product_id), true) FROM order_demo.products;
SELECT setval(pg_get_serial_sequence('order_demo.orders', 'order_id'), max(order_id), true) FROM order_demo.orders;
SELECT setval(pg_get_serial_sequence('order_demo.shipments', 'shipment_id'), max(shipment_id), true) FROM order_demo.shipments;

COMMIT;

-- Refresh planner statistics, including statistics on the partitioned parent.
ANALYZE order_demo.customers;
ANALYZE order_demo.addresses;
ANALYZE order_demo.categories;
ANALYZE order_demo.products;
ANALYZE order_demo.orders;
ANALYZE order_demo.order_items;
ANALYZE order_demo.payments;
ANALYZE order_demo.shipments;
ANALYZE audit.audit_event;

-- Exact row counts; orders includes all 16 partitions.
SELECT 'order_demo.customers' AS table_name, count(*) AS row_count FROM order_demo.customers
UNION ALL
SELECT 'order_demo.addresses' AS table_name, count(*) AS row_count FROM order_demo.addresses
UNION ALL
SELECT 'order_demo.categories' AS table_name, count(*) AS row_count FROM order_demo.categories
UNION ALL
SELECT 'order_demo.products' AS table_name, count(*) AS row_count FROM order_demo.products
UNION ALL
SELECT 'order_demo.orders' AS table_name, count(*) AS row_count FROM order_demo.orders
UNION ALL
SELECT 'order_demo.order_items' AS table_name, count(*) AS row_count FROM order_demo.order_items
UNION ALL
SELECT 'order_demo.payments' AS table_name, count(*) AS row_count FROM order_demo.payments
UNION ALL
SELECT 'order_demo.shipments' AS table_name, count(*) AS row_count FROM order_demo.shipments
UNION ALL
SELECT 'audit.audit_event' AS table_name, count(*) AS row_count FROM audit.audit_event
ORDER BY table_name;
