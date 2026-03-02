# Nginx Reverse Proxy Configuration

This directory contains nginx configuration for production deployment of the Cineca Agentic Platform.

## Features

- **HTTPS Termination**: TLS 1.2/1.3 with modern cipher suites
- **Security Headers**: HSTS, X-Frame-Options, CSP, etc.
- **Rate Limiting**: Configurable per-endpoint rate limits
- **Load Balancing**: Upstream health checks and failover
- **WebSocket Support**: For Streamlit UI real-time updates

## Quick Start

### Development (Self-Signed Certificate)

```bash
# Generate self-signed certificate for testing
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ops/nginx/ssl/platform.key \
  -out ops/nginx/ssl/platform.crt \
  -subj "/CN=localhost"

# Start with docker-compose
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

### Production (Let's Encrypt)

```bash
# Install certbot
apt-get install certbot python3-certbot-nginx

# Obtain certificate (interactive)
certbot --nginx -d platform.cineca.it

# Or non-interactive
certbot certonly --nginx \
  --non-interactive \
  --agree-tos \
  --email admin@cineca.it \
  -d platform.cineca.it

# Copy certificates to nginx directory
cp /etc/letsencrypt/live/platform.cineca.it/fullchain.pem ops/nginx/ssl/platform.crt
cp /etc/letsencrypt/live/platform.cineca.it/privkey.pem ops/nginx/ssl/platform.key

# Start nginx
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

### Production (Custom Certificate)

```bash
# Copy your certificates
cp /path/to/your/cert.crt ops/nginx/ssl/platform.crt
cp /path/to/your/cert.key ops/nginx/ssl/platform.key

# Ensure proper permissions
chmod 644 ops/nginx/ssl/platform.crt
chmod 600 ops/nginx/ssl/platform.key

# Start nginx
docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

## Configuration

### Rate Limiting

Default rate limits (configured in `nginx.conf`):
- API endpoints: 10 req/s per IP (burst 20)
- Admin endpoints: 10 req/s per IP (burst 10)
- Health checks: No limit

To adjust:
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=20r/s;  # Change 20r/s
```

### SSL/TLS Settings

Current configuration:
- Protocols: TLS 1.2, TLS 1.3
- Ciphers: Modern Mozilla recommendations
- HSTS: Enabled (1 year)
- Session cache: 10 minutes

To customize:
```nginx
ssl_protocols TLSv1.3;  # TLS 1.3 only
ssl_session_timeout 24h;  # Longer session cache
```

### Security Headers

Enabled by default:
- `Strict-Transport-Security`: HSTS with 1 year max-age
- `X-Frame-Options`: DENY (prevent clickjacking)
- `X-Content-Type-Options`: nosniff
- `X-XSS-Protection`: 1; mode=block
- `Referrer-Policy`: strict-origin-when-cross-origin
- `Permissions-Policy`: Restricts geolocation, microphone, camera

## Testing

### HTTPS Configuration

```bash
# Test SSL/TLS setup
curl -I https://localhost:443
openssl s_client -connect localhost:443 -servername localhost

# Test HTTP to HTTPS redirect
curl -I http://localhost:80
# Expected: 301 redirect to https://

# Test security headers
curl -I https://localhost:443/v1/health/ready
# Expected: HSTS, X-Frame-Options, etc.
```

### Rate Limiting

```bash
# Test API rate limiting
for i in {1..25}; do
  curl -s -o /dev/null -w "%{http_code}\n" https://localhost:443/v1/health/ready
  sleep 0.05  # 20 req/s
done
# Expected: First 20-30 return 200, rest return 429

# Test rate limit headers
curl -I https://localhost:443/v1/health/ready
# Expected: X-RateLimit-Limit, X-RateLimit-Remaining headers
```

### WebSocket Support

```bash
# Test Streamlit WebSocket connection
wscat -c wss://localhost:443/_stcore/stream
# Expected: WebSocket upgrade successful
```

## Monitoring

### Access Logs

```bash
# View access logs
docker-compose logs nginx

# Follow logs
docker-compose logs -f nginx
```

### Error Logs

```bash
# View error logs
docker-compose exec nginx cat /var/log/nginx/error.log

# Follow error logs
docker-compose exec nginx tail -f /var/log/nginx/error.log
```

### Metrics

Nginx metrics can be exposed via:
- Nginx stub_status module (basic stats)
- Prometheus nginx-exporter (detailed metrics)

To enable stub_status:
```nginx
location /nginx_status {
    stub_status;
    allow 127.0.0.1;
    deny all;
}
```

## Troubleshooting

### Common Issues

**Certificate errors**:
```bash
# Verify certificate
openssl x509 -in ops/nginx/ssl/platform.crt -text -noout

# Check certificate chain
openssl verify -CAfile ops/nginx/ssl/platform.crt ops/nginx/ssl/platform.crt
```

**Rate limiting too strict**:
```bash
# Temporarily disable rate limiting
# Comment out limit_req lines in nginx.conf
docker-compose restart nginx
```

**WebSocket connection fails**:
```bash
# Check proxy headers
curl -I -H "Upgrade: websocket" -H "Connection: Upgrade" https://localhost:443/

# Check nginx error log
docker-compose logs nginx | grep -i websocket
```

## Production Checklist

Before deploying to production:

- [ ] Install valid SSL/TLS certificate (not self-signed)
- [ ] Update `server_name` in nginx.conf to match domain
- [ ] Review and adjust rate limits based on expected traffic
- [ ] Configure firewall rules (allow 80, 443; deny direct access to 8000, 8501)
- [ ] Enable access log aggregation (e.g., to ELK stack)
- [ ] Set up SSL certificate auto-renewal (certbot cron job)
- [ ] Test failover by stopping backend services
- [ ] Load test with expected traffic patterns
- [ ] Configure monitoring alerts for 429 (rate limit) errors
- [ ] Review security headers with SSL Labs test

## References

- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/)
- [Nginx Rate Limiting](https://www.nginx.com/blog/rate-limiting-nginx/)
- [Nginx WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)

