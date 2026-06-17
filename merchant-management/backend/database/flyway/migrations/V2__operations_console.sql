-- Operations console expansion: KYB, contracts, trust, certificates, transactions, reconciliation, exports

ALTER TABLE merchant_capabilities
    ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'DRAFT' AFTER version,
    ADD COLUMN descriptor VARCHAR(128) NULL AFTER status,
    ADD COLUMN vertical VARCHAR(64) NULL AFTER descriptor,
    ADD COLUMN description_en VARCHAR(512) NULL AFTER vertical,
    ADD COLUMN description_zh VARCHAR(512) NULL AFTER description_en,
    ADD COLUMN line_items_schema JSON NULL AFTER description_zh,
    ADD COLUMN registered_at TIMESTAMP NULL AFTER line_items_schema,
    ADD COLUMN validated_at TIMESTAMP NULL AFTER registered_at,
    ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER validated_at;

CREATE TABLE IF NOT EXISTS merchant_kyb_reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    legal_name VARCHAR(255) NOT NULL,
    registration_no VARCHAR(128) NOT NULL,
    country VARCHAR(64) NOT NULL DEFAULT 'SG',
    vertical VARCHAR(64) NOT NULL DEFAULT 'airline',
    contact_email VARCHAR(255) NOT NULL,
    documents_json JSON NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    reviewer VARCHAR(128) NULL,
    reject_reason VARCHAR(512) NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_kyb_merchant (merchant_id),
    CONSTRAINT fk_kyb_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS merchant_contracts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    contract_type VARCHAR(64) NOT NULL DEFAULT 'platform_agreement',
    template_version VARCHAR(32) NOT NULL DEFAULT '2026-01',
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    signed_by VARCHAR(255) NULL,
    signed_at TIMESTAMP NULL,
    summary_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_contract_merchant (merchant_id, contract_type),
    CONSTRAINT fk_contract_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS merchant_trust_keys (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    kid VARCHAR(128) NOT NULL,
    alg VARCHAR(32) NOT NULL DEFAULT 'RS256',
    public_jwk_json JSON NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'platform',
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    fingerprint VARCHAR(128) NOT NULL,
    expires_at TIMESTAMP NULL,
    last_verified_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_merchant_kid (merchant_id, kid),
    CONSTRAINT fk_trust_key_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS merchant_certificates (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    serial_no VARCHAR(128) NOT NULL,
    subject_cn VARCHAR(255) NOT NULL,
    issuer_cn VARCHAR(255) NOT NULL DEFAULT 'Agentic Payment Platform CA',
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    not_before TIMESTAMP NOT NULL,
    not_after TIMESTAMP NOT NULL,
    alert_status VARCHAR(32) NOT NULL DEFAULT 'OK',
    revoked_at TIMESTAMP NULL,
    revoke_reason VARCHAR(512) NULL,
    cert_pem TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_cert_serial (serial_no),
    INDEX idx_cert_merchant (merchant_id),
    CONSTRAINT fk_cert_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS merchant_transactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(128) NOT NULL,
    mandate_ref VARCHAR(128) NULL,
    receipt_ref VARCHAR(128) NULL,
    amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    vertical VARCHAR(64) NULL,
    descriptor VARCHAR(128) NULL,
    audit_index VARCHAR(128) NULL,
    detail_json JSON NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_merchant_order (merchant_id, order_id),
    INDEX idx_tx_merchant_status (merchant_id, status),
    INDEX idx_tx_mandate (mandate_ref),
    INDEX idx_tx_receipt (receipt_ref),
    CONSTRAINT fk_tx_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    total_items INT NOT NULL DEFAULT 0,
    matched_items INT NOT NULL DEFAULT 0,
    mismatch_items INT NOT NULL DEFAULT 0,
    mandate_verify_fail_count INT NOT NULL DEFAULT 0,
    file_summary_json JSON NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_recon_merchant (merchant_id),
    CONSTRAINT fk_recon_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

CREATE TABLE IF NOT EXISTS reconciliation_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    merchant_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(128) NOT NULL,
    mandate_ref VARCHAR(128) NULL,
    receipt_ref VARCHAR(128) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'MATCHED',
    mismatch_reason VARCHAR(512) NULL,
    detail_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_recon_item_run (run_id),
    CONSTRAINT fk_recon_item_run FOREIGN KEY (run_id) REFERENCES reconciliation_runs(id)
);

CREATE TABLE IF NOT EXISTS export_jobs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    export_type VARCHAR(64) NOT NULL DEFAULT 'dispute_bundle',
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    requested_by VARCHAR(128) NOT NULL DEFAULT 'admin',
    filters_json JSON NULL,
    artifact_summary_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    INDEX idx_export_merchant (merchant_id),
    CONSTRAINT fk_export_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(id)
);

INSERT INTO merchant_kyb_reviews (merchant_id, legal_name, registration_no, country, vertical, contact_email, documents_json, status)
VALUES (
    'heg_flight',
    'HEG Flight Pte Ltd',
    '201912345A',
    'SG',
    'airline',
    'compliance@hegflight.demo',
    JSON_OBJECT('business_license', 'uploaded', 'tax_certificate', 'uploaded'),
    'PENDING'
) ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

INSERT INTO merchant_contracts (merchant_id, contract_type, template_version, status, summary_json)
VALUES (
    'heg_flight',
    'platform_agreement',
    '2026-01',
    'PENDING',
    JSON_OBJECT('title_en', 'Agentic Payment Platform Agreement', 'title_zh', 'Agentic 支付平台服务协议')
) ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

UPDATE merchant_capabilities SET
    status = 'PUBLISHED',
    descriptor = 'flight_booking',
    vertical = 'airline',
    description_en = 'Flight catalog and checkout capability',
    description_zh = '航班目录与结账能力',
    line_items_schema = JSON_OBJECT('type', 'flight', 'fields', JSON_ARRAY('route', 'cabin', 'passenger_count')),
    registered_at = CURRENT_TIMESTAMP,
    validated_at = CURRENT_TIMESTAMP
WHERE merchant_id = 'heg_flight';

INSERT INTO merchant_transactions (merchant_id, order_id, mandate_ref, receipt_ref, amount, currency, status, vertical, descriptor, audit_index, detail_json, occurred_at)
VALUES
('heg_flight', 'ORD-2026-001', 'mdt_abc123', 'rcpt_xyz789', 1280.00, 'USD', 'COMPLETED', 'airline', 'flight_booking', 'audit-001', JSON_OBJECT('route', 'SIN-NRT'), DATE_SUB(NOW(), INTERVAL 2 DAY)),
('heg_flight', 'ORD-2026-002', 'mdt_def456', 'rcpt_uvw456', 980.50, 'USD', 'COMPLETED', 'airline', 'flight_booking', 'audit-002', JSON_OBJECT('route', 'SIN-HKG'), DATE_SUB(NOW(), INTERVAL 1 DAY)),
('heg_flight', 'ORD-2026-003', 'mdt_fail001', NULL, 450.00, 'USD', 'FAILED', 'airline', 'flight_booking', 'audit-003', JSON_OBJECT('error', 'mandate_verify_fail'), DATE_SUB(NOW(), INTERVAL 6 HOUR))
ON DUPLICATE KEY UPDATE audit_index = VALUES(audit_index);
