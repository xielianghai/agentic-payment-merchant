-- Persist platform-managed JWKS URLs as absolute endpoints (dev default host/port).
UPDATE merchants
SET jwks_url = CONCAT('http://127.0.0.1:9100', jwks_url)
WHERE jwks_url LIKE '/api/v1/admin/merchants/%/trust/jwks';
