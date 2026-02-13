# SSL/TLS Setup for MockFactory.io

Complete guide to enabling HTTPS for mockfactory.io.

## Overview

MockFactory now includes automatic HTTP → HTTPS redirect middleware. You need to configure SSL at the load balancer level.

## Option 1: OCI Load Balancer SSL (Recommended)

### Step 1: Obtain SSL Certificate

**Option A: Let's Encrypt (Free)**
```bash
# Install certbot
sudo apt-get update
sudo apt-get install certbot

# Get certificate
sudo certbot certonly --standalone -d mockfactory.io -d www.mockfactory.io

# Certificates will be in:
# /etc/letsencrypt/live/mockfactory.io/fullchain.pem
# /etc/letsencrypt/live/mockfactory.io/privkey.pem
```

**Option B: OCI Certificates Service**
1. Go to OCI Console → Identity & Security → Certificates
2. Create new certificate or import existing
3. Upload certificate and private key

### Step 2: Configure Load Balancer Listener

1. **Go to OCI Load Balancer**
   - Navigate to: Networking → Load Balancers
   - Select: `undateable-lb` (141.148.79.30)

2. **Add HTTPS Listener**
   - Click **Listeners**
   - Click **Create Listener**

   Configuration:
   ```
   Name: mockfactory-https
   Protocol: HTTP
   Port: 443
   Use SSL: ✓ (checked)
   ```

3. **Configure SSL Certificate**
   - Select certificate source:
     - OCI Certificates Service (if using Option B)
     - Upload Certificate Bundle (if using Let's Encrypt)

   For Let's Encrypt:
   ```
   Certificate: /etc/letsencrypt/live/mockfactory.io/fullchain.pem
   Private Key: /etc/letsencrypt/live/mockfactory.io/privkey.pem
   ```

4. **SSL Configuration**
   ```
   SSL Protocol: TLS 1.2 and 1.3
   Cipher Suite: Default (Recommended)
   Certificate Verification: None (for backend)
   ```

5. **Backend Set**
   - Select existing backend set for MockFactory
   - Or create new backend set pointing to port 8000

### Step 3: Add HTTP Listener (for redirect)

1. **Create HTTP Listener**
   ```
   Name: mockfactory-http
   Protocol: HTTP
   Port: 80
   Use SSL: ✗ (unchecked)
   ```

2. **Configure Backend**
   - Point to same backend set
   - The app middleware will handle redirect

### Step 4: Configure Routing Rules

Add hostname routing rule:
```
Hostname: mockfactory.io
Path: /*
Backend Set: mockfactory-backend-set
```

Add another for www:
```
Hostname: www.mockfactory.io
Path: /*
Backend Set: mockfactory-backend-set
```

### Step 5: Update Security Lists

Ensure security list allows:
- **Ingress**: Port 443 (HTTPS) from 0.0.0.0/0
- **Ingress**: Port 80 (HTTP) from 0.0.0.0/0
- **Egress**: Port 8000 to backend instances

## Option 2: Cloudflare Proxy (Easiest)

1. **Add Domain to Cloudflare**
   - Sign up at cloudflare.com
   - Add mockfactory.io
   - Update nameservers (if not using OCI DNS)

2. **Enable Proxy**
   - Ensure orange cloud ☁️ is enabled for:
     - `mockfactory.io` → 141.148.79.30
     - `www.mockfactory.io` → 141.148.79.30

3. **SSL Settings**
   - Go to SSL/TLS → Overview
   - Select: **Full** or **Full (Strict)**

4. **Force HTTPS**
   - Go to SSL/TLS → Edge Certificates
   - Enable **Always Use HTTPS**

5. **Configure Page Rules** (optional)
   - Create rule: `http://mockfactory.io/*`
   - Setting: **Always Use HTTPS**

## Option 3: Nginx Reverse Proxy

If you want to use Nginx in front of the app:

```nginx
# /etc/nginx/sites-available/mockfactory.io

# HTTP - Redirect to HTTPS
server {
    listen 80;
    server_name mockfactory.io www.mockfactory.io;

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS - Proxy to FastAPI
server {
    listen 443 ssl http2;
    server_name mockfactory.io www.mockfactory.io;

    ssl_certificate /etc/letsencrypt/live/mockfactory.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mockfactory.io/privkey.pem;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/mockfactory.io /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Application Middleware

MockFactory includes HTTPS redirect middleware that:
- ✅ Redirects HTTP → HTTPS for mockfactory.io
- ✅ Checks `X-Forwarded-Proto` header (load balancer)
- ✅ Returns 301 permanent redirect
- ✅ Skips redirect for localhost (development)

Located in: `app/main.py:HTTPSRedirectMiddleware`

## Testing SSL Configuration

### Test HTTPS
```bash
curl -I https://mockfactory.io/health
# Should return 200 OK
```

### Test HTTP Redirect
```bash
curl -I http://mockfactory.io/health
# Should return 301 Moved Permanently
# Location: https://mockfactory.io/health
```

### Test SSL Grade
```bash
# SSL Labs test
https://www.ssllabs.com/ssltest/analyze.html?d=mockfactory.io
```

### Verify Certificate
```bash
openssl s_client -connect mockfactory.io:443 -servername mockfactory.io
```

## Certificate Renewal (Let's Encrypt)

Let's Encrypt certificates expire after 90 days. Set up auto-renewal:

```bash
# Test renewal
sudo certbot renew --dry-run

# Set up cron job
sudo crontab -e

# Add this line (runs twice daily)
0 0,12 * * * certbot renew --quiet --deploy-hook "oci lb certificate update ..."
```

For OCI Load Balancer, you'll need to update the certificate:
```bash
# After renewal, update OCI certificate
oci lb certificate create \
  --certificate-name mockfactory-$(date +%Y%m%d) \
  --load-balancer-id <load-balancer-ocid> \
  --public-certificate-file /etc/letsencrypt/live/mockfactory.io/fullchain.pem \
  --private-key-file /etc/letsencrypt/live/mockfactory.io/privkey.pem
```

## Security Best Practices

### HTTP Strict Transport Security (HSTS)
Add to load balancer or Nginx:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

### Security Headers
Already configured in app, but good to add at load balancer:
```
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### TLS Configuration
- ✅ Use TLS 1.2 and 1.3 only
- ✅ Disable TLS 1.0 and 1.1
- ✅ Use strong cipher suites
- ✅ Enable HTTP/2

## Troubleshooting

### Certificate Not Trusted
**Issue**: Browser shows "Not Secure" or certificate error

**Solutions**:
- Verify certificate includes full chain
- Check certificate is valid (not expired)
- Ensure certificate matches domain name
- Use `fullchain.pem` not `cert.pem`

### Mixed Content Warnings
**Issue**: HTTPS page loading HTTP resources

**Solution**:
- Update all URLs to use HTTPS
- Use protocol-relative URLs: `//example.com/script.js`
- Add to HTML: `<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">`

### Redirect Loop
**Issue**: Infinite redirects between HTTP and HTTPS

**Solution**:
- Check `X-Forwarded-Proto` header is set correctly by load balancer
- Verify middleware checks both `scheme` and header
- Test with: `curl -v -H "X-Forwarded-Proto: https" http://mockfactory.io`

### Load Balancer Not Forwarding HTTPS
**Issue**: Load balancer refuses HTTPS connection

**Solution**:
- Verify listener on port 443 exists
- Check security list allows port 443
- Verify certificate is properly configured
- Check backend health check passes

## Current Status

MockFactory.io configuration:
- ✅ Domain: mockfactory.io
- ✅ DNS: 141.148.79.30 (undateable-lb)
- ✅ App has HTTPS redirect middleware
- ⏳ Need to configure SSL at load balancer
- ⏳ Need to obtain/upload SSL certificate

## Quick Start Checklist

- [ ] Obtain SSL certificate (Let's Encrypt or purchase)
- [ ] Upload certificate to OCI
- [ ] Create HTTPS listener on port 443
- [ ] Configure HTTP listener on port 80
- [ ] Test HTTP → HTTPS redirect
- [ ] Verify SSL grade
- [ ] Set up certificate auto-renewal
- [ ] Add security headers
- [ ] Enable HSTS

## Support

- **OCI Load Balancer**: https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managinglisteners.htm
- **Let's Encrypt**: https://letsencrypt.org/docs/
- **SSL Labs**: https://www.ssllabs.com/ssltest/
