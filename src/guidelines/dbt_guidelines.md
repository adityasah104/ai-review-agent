# dbt and SQL Coding Guidelines

## Model Naming Conventions
- Staging models: prefix with `stg_` (e.g. `stg_orders`, `stg_customers`)
- Intermediate models: prefix with `int_` (e.g. `int_order_items_joined`)
- Mart/final models: prefix with `mart_` (e.g. `mart_revenue`, `mart_customer_ltv`)
- Snapshot models: prefix with `scd_` (e.g. `scd_customer_status`)
- Seeds: descriptive names without prefix (e.g. `country_codes`, `product_categories`)

## SQL Style Rules
- All SQL keywords must be lowercase: `select`, `from`, `where`, `join`, `group by`
- Each clause on its own line
- Indent with 4 spaces, not tabs
- Always alias tables in joins: `from orders as o join customers as c`
- No trailing whitespace
- Files must end with a single newline

## dbt Best Practices
- Always use `{{ ref('model_name') }}` to reference other models — never hardcode schema.table
- Always use `{{ source('source_name', 'table_name') }}` for raw source tables
- Never use `SELECT *` — always explicitly list columns with aliases
- Add descriptions to all models and columns in schema.yml
- Every staging model must have a unique test on its primary key
- Every staging model must have a not_null test on its primary key

## Materialization Rules
- Staging models: `materialized: view` (lightweight, always fresh)
- Intermediate models: `materialized: ephemeral` or `view` unless performance requires table
- Mart models: `materialized: table` for final outputs consumed by BI tools
- Large fact tables (>1M rows): `materialized: incremental` with a proper `unique_key`

## Performance Rules
- Avoid `SELECT DISTINCT` unless necessary — use `GROUP BY` with aggregation instead
- Always filter early: apply `WHERE` clauses in staging models, not in marts
- Join on indexed columns — primary keys and foreign keys
- Avoid cross joins unless intentional
- Use `LIMIT` in development (via `dbt run --limit`) to avoid full table scans

## Column Conventions
- Primary key column: always named `<model_name>_id` (e.g. `order_id`, `customer_id`)
- Timestamps: use `_at` suffix (e.g. `created_at`, `updated_at`)
- Boolean columns: use `is_` or `has_` prefix (e.g. `is_active`, `has_discount`)
- Amount/money columns: use explicit currency suffix (e.g. `total_amount_usd`)
- Date columns: use `_date` suffix (e.g. `order_date`, `ship_date`)

## Testing Requirements
- `unique` test on primary key for every staging and mart model
- `not_null` test on primary key and all required foreign keys
- `accepted_values` test on status/enum columns
- `relationships` test on all foreign keys that reference another model