USE defaultdb;

DROP DATABASE IF EXISTS order_demo;

CREATE DATABASE order_demo;

USE order_demo;

CREATE SCHEMA order_demo;

CREATE SCHEMA audit;

SET search_path = order_demo, pg_catalog;

CREATE TYPE order_status AS ENUM (
	'pending',
	'paid',
	'shipped',
	'completed',
	'cancelled'
);

CREATE TYPE payment_status AS ENUM ('pending', 'captured', 'failed', 'refunded');

CREATE SEQUENCE IF NOT EXISTS customers_customer_id_seq;

CREATE TABLE customers (
	customer_id INT8 DEFAULT nextval('customers_customer_id_seq') NOT NULL PRIMARY KEY,
	external_id UUID DEFAULT gen_random_uuid() NOT NULL,
	email VARCHAR(254) NOT NULL,
	full_name STRING NOT NULL,
	date_of_birth DATE,
	is_active BOOL DEFAULT true NOT NULL,
	loyalty_points INT8 DEFAULT 0 NOT NULL CHECK (loyalty_points >= 0),
	preferences JSONB DEFAULT '{}' :: JSONB NOT NULL CHECK (jsonb_typeof(preferences) = 'object'),
	tags STRING [] DEFAULT '{}' :: STRING [] NOT NULL,
	last_login_ip INET,
	created_at TIMESTAMPTZ DEFAULT current_timestamp() NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS addresses_address_id_seq;

CREATE TABLE addresses (
	address_id INT8 DEFAULT nextval('addresses_address_id_seq') NOT NULL PRIMARY KEY,
	customer_id INT8 NOT NULL,
	recipient STRING NOT NULL,
	street STRING NOT NULL,
	city STRING NOT NULL,
	region STRING,
	postal_code VARCHAR(20) NOT NULL,
	country_code VARCHAR(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
	coordinates STRING,
	delivery_notes STRING,
	is_default BOOL DEFAULT false NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS categories_category_id_seq;

CREATE TABLE categories (
	category_id INT8 DEFAULT nextval('categories_category_id_seq') NOT NULL PRIMARY KEY,
	parent_category_id INT8,
	name STRING NOT NULL,
	slug STRING NOT NULL,
	CHECK (
		parent_category_id IS DISTINCT
		FROM
			category_id
	)
);

CREATE SEQUENCE IF NOT EXISTS products_product_id_seq;

CREATE TABLE products (
	product_id INT8 DEFAULT nextval('products_product_id_seq') NOT NULL PRIMARY KEY,
	category_id INT8 NOT NULL,
	sku VARCHAR(64) NOT NULL,
	name STRING NOT NULL,
	description STRING DEFAULT '' NOT NULL,
	price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
	weight_kg FLOAT8 CHECK (weight_kg > 0),
	stock_quantity INT8 DEFAULT 0 NOT NULL CHECK (stock_quantity >= 0),
	attributes JSONB DEFAULT '{}' :: JSONB NOT NULL CHECK (jsonb_typeof(attributes) = 'object'),
	tags STRING [] DEFAULT '{}' :: STRING [] NOT NULL,
	available_during STRING DEFAULT '(,)' NOT NULL CHECK (available_during != 'empty'),
	image_digest BYTES CHECK (octet_length(image_digest) = 32),
	search_document TSVECTOR AS (
		to_tsvector('english', name || ' ' || description)
	) STORED,
	created_at TIMESTAMPTZ DEFAULT current_timestamp() NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS orders_order_id_seq;

CREATE TABLE orders (
	order_id INT8 DEFAULT nextval('orders_order_id_seq') NOT NULL,
	customer_id INT8 NOT NULL,
	shipping_address_id INT8 NOT NULL,
	status order_status DEFAULT 'pending' NOT NULL,
	placed_at TIMESTAMPTZ DEFAULT current_timestamp() NOT NULL,
	paid_at TIMESTAMPTZ,
	subtotal DECIMAL(14, 2) NOT NULL CHECK (subtotal >= 0),
	tax DECIMAL(14, 2) DEFAULT 0 NOT NULL CHECK (tax >= 0),
	shipping_fee DECIMAL(14, 2) DEFAULT 0 NOT NULL CHECK (shipping_fee >= 0),
	total DECIMAL(14, 2) AS (subtotal + tax + shipping_fee) STORED,
	metadata JSONB DEFAULT '{}' :: JSONB NOT NULL CHECK (jsonb_typeof(metadata) = 'object'),
	shipping_snapshot JSONB NOT NULL CHECK (jsonb_typeof(shipping_snapshot) = 'object'),
	CHECK (
		paid_at IS NULL
		OR paid_at >= placed_at
	),
	PRIMARY KEY (order_id)
);

CREATE TABLE order_items (
	order_id INT8 NOT NULL,
	line_number INT2 NOT NULL CHECK (line_number > 0),
	product_id INT8 NOT NULL,
	quantity INT4 NOT NULL CHECK (quantity > 0),
	unit_price DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0),
	discount DECIMAL(12, 2) DEFAULT 0 NOT NULL CHECK (discount >= 0),
	line_total DECIMAL(14, 2) AS (quantity * unit_price - discount) STORED,
	options JSONB DEFAULT '{}' :: JSONB NOT NULL CHECK (jsonb_typeof(options) = 'object'),
	PRIMARY KEY (order_id, line_number),
	CHECK (discount <= quantity * unit_price)
);

CREATE TABLE payments (
	payment_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
	order_id INT8 NOT NULL,
	status payment_status DEFAULT 'pending' NOT NULL,
	method STRING NOT NULL CHECK (method IN ('card', 'bank_transfer', 'wallet')),
	amount DECIMAL(14, 2) NOT NULL CHECK (amount > 0),
	provider_reference STRING,
	provider_response JSONB,
	created_at TIMESTAMPTZ DEFAULT current_timestamp() NOT NULL,
	captured_at TIMESTAMPTZ,
	CHECK (
		captured_at IS NULL
		OR captured_at >= created_at
	)
);

CREATE SEQUENCE IF NOT EXISTS shipments_shipment_id_seq;

CREATE TABLE shipments (
	shipment_id INT8 DEFAULT nextval('shipments_shipment_id_seq') NOT NULL PRIMARY KEY,
	order_id INT8 NOT NULL,
	carrier STRING NOT NULL,
	tracking_number STRING NOT NULL,
	shipped_at TIMESTAMPTZ,
	delivered_at TIMESTAMPTZ,
	delivery_window STRING CHECK (delivery_window != 'empty'),
	estimated_transit INTERVAL CHECK (estimated_transit > '0 seconds' :: INTERVAL),
	package_weight_kg FLOAT4 CHECK (package_weight_kg > 0),
	tracking_events JSONB DEFAULT '[]' :: JSONB NOT NULL CHECK (jsonb_typeof(tracking_events) = 'array'),
	CHECK (
		delivered_at IS NULL
		OR (
			shipped_at IS NOT NULL
			AND delivered_at >= shipped_at
		)
	)
);

CREATE SEQUENCE IF NOT EXISTS audit.audit_event_event_id_seq;

CREATE TABLE audit.audit_event (
	event_id INT8 DEFAULT nextval('audit.audit_event_event_id_seq') NOT NULL PRIMARY KEY,
	occurred_at TIMESTAMPTZ DEFAULT clock_timestamp() NOT NULL,
	transaction_id INT8 NOT NULL,
	session_actor STRING DEFAULT session_user() NOT NULL,
	effective_actor STRING DEFAULT current_user() NOT NULL,
	application_name STRING DEFAULT current_setting('application_name') NOT NULL,
	table_schema STRING NOT NULL,
	table_name STRING NOT NULL,
	operation STRING NOT NULL CHECK (operation = 'UPDATE'),
	row_key JSONB NOT NULL,
	changed_columns STRING [] NOT NULL CHECK (cardinality(changed_columns) > 0),
	old_row JSONB NOT NULL,
	new_row JSONB NOT NULL
);



-- address datatypes that cannot be migrated

ALTER TABLE order_demo.addresses
  DROP COLUMN coordinates,
  ADD COLUMN coordinates_x FLOAT8,
  ADD COLUMN coordinates_y FLOAT8;

ALTER TABLE order_demo.products
  DROP COLUMN available_during,
  ADD COLUMN available_from DATE,
  ADD COLUMN available_to   DATE,
  ADD CONSTRAINT products_available_range_chk
    CHECK (available_to IS NULL OR available_to > available_from);

ALTER TABLE order_demo.shipments
  DROP COLUMN delivery_window,
  ADD COLUMN delivery_from TIMESTAMPTZ,
  ADD COLUMN delivery_to   TIMESTAMPTZ,
  ADD CONSTRAINT shipments_delivery_window_chk
    CHECK (delivery_to IS NULL OR delivery_to > delivery_from);
