-- Merchant Management Platform initial schema

CREATE TABLE IF NOT EXISTS merchants (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    display_name_en VARCHAR(255) NOT NULL,
    display_name_zh VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    protocols JSON NOT NULL,
    backend_base_url VARCHAR(512) NOT NULL,
    a2a_endpoint VARCHAR(512) NULL,
    ucp_profile_url VARCHAR(512) NULL,
    mcp_server_path VARCHAR(512) NULL,
    capabilities_json JSON NOT NULL,
    jwks_url VARCHAR(512) NULL,
    signing_api_url VARCHAR(512) NULL,
    onboarded_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_merchants_status (status)
);

CREATE TABLE IF NOT EXISTS onboarding_tasks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    step VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    detail_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_onboarding_merchant (merchant_id),
    CONSTRAINT fk_onboarding_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS merchant_capabilities (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    capability_id VARCHAR(128) NOT NULL,
    version VARCHAR(32) NOT NULL,
    schema_url VARCHAR(512) NULL,
    config_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_merchant_capability (merchant_id, capability_id),
    CONSTRAINT fk_capability_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS operation_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NULL,
    action VARCHAR(128) NOT NULL,
    actor VARCHAR(128) NOT NULL DEFAULT 'system',
    detail_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_logs_merchant (merchant_id),
    INDEX idx_logs_action (action)
);

-- Seed HEG Flight merchant template (inactive until onboarded)
INSERT INTO merchants (
    id, name, display_name_en, display_name_zh, status, protocols,
    backend_base_url, a2a_endpoint, ucp_profile_url, mcp_server_path,
    capabilities_json, jwks_url
) VALUES (
    'heg_flight',
    'HEG Flight Mock',
    'Singapore Airlines (HEG Flight)',
    '新加坡航空 (HEG Flight)',
    'PENDING',
    JSON_ARRAY('A2A', 'AP2', 'UCP'),
    'http://127.0.0.1:9000',
    'http://127.0.0.1:9000/a2a/heg_merchant_agent',
    'http://127.0.0.1:8200/.well-known/ucp',
    '/Users/ouyang/AI-coding/payment/heg_flight_mock/mcp/server.py',
    JSON_OBJECT(
        'catalog', true,
        'cart', true,
        'checkout', true,
        'order', true,
        'ap2_mandate', true
    ),
    'http://127.0.0.1:9000/.well-known/jwks.json'
) ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

INSERT INTO merchant_capabilities (merchant_id, capability_id, version, schema_url) VALUES
('heg_flight', 'dev.ucp.shopping.catalog.search', '2026-01-23', 'https://ucp.dev/2026-01-23/schemas/shopping/catalog_lookup.json'),
('heg_flight', 'dev.ucp.shopping.cart', '2026-01-23', 'https://ucp.dev/2026-01-23/schemas/shopping/cart.json'),
('heg_flight', 'dev.ucp.shopping.checkout', '2026-01-23', 'https://ucp.dev/2026-01-23/schemas/shopping/checkout.json'),
('heg_flight', 'dev.ucp.shopping.order', '2026-01-23', 'https://ucp.dev/2026-01-23/schemas/shopping/order.json'),
('heg_flight', 'dev.ucp.shopping.ap2_mandate', '2026-01-23', 'https://ucp.dev/2026-01-23/schemas/shopping/ap2_mandate.json')
ON DUPLICATE KEY UPDATE version = VALUES(version);
