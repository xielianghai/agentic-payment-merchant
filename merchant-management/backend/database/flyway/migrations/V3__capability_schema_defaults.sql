-- Backfill schema_url, config_json, and line_items_schema for existing capabilities.

UPDATE merchant_capabilities
SET schema_url = CASE capability_id
    WHEN 'dev.ucp.shopping.catalog.search' THEN 'https://ucp.dev/2026-01-23/schemas/shopping/catalog_lookup.json'
    WHEN 'dev.ucp.shopping.cart' THEN 'https://ucp.dev/2026-01-23/schemas/shopping/cart.json'
    WHEN 'dev.ucp.shopping.checkout' THEN 'https://ucp.dev/2026-01-23/schemas/shopping/checkout.json'
    WHEN 'dev.ucp.shopping.order' THEN 'https://ucp.dev/2026-01-23/schemas/shopping/order.json'
    WHEN 'dev.ucp.shopping.ap2_mandate' THEN 'https://ucp.dev/2026-01-23/schemas/shopping/ap2_mandate.json'
    ELSE schema_url
END
WHERE schema_url IS NULL OR schema_url = '';

UPDATE merchant_capabilities
SET line_items_schema = JSON_OBJECT(
    'type', 'flight',
    'fields', JSON_ARRAY('route', 'cabin', 'passenger_count')
)
WHERE (vertical = 'airline' OR descriptor = 'flight_booking')
  AND (line_items_schema IS NULL OR JSON_LENGTH(line_items_schema) = 0);

UPDATE merchant_capabilities
SET line_items_schema = JSON_OBJECT(
    'type', 'hotel',
    'fields', JSON_ARRAY('hotel_id', 'room_type', 'check_in', 'check_out', 'guest_count')
)
WHERE vertical = 'hotel'
  AND (line_items_schema IS NULL OR JSON_LENGTH(line_items_schema) = 0);

UPDATE merchant_capabilities
SET config_json = JSON_OBJECT('extends', 'dev.ucp.shopping.checkout')
WHERE capability_id = 'dev.ucp.shopping.ap2_mandate'
  AND (config_json IS NULL OR JSON_LENGTH(config_json) = 0);
