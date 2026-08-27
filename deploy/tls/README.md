# Dev TLS certs

`*.key` / `*.crt` / `*.pem` here are gitignored. Generate a self-signed dev
cert before `make up`:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout deploy/tls/dev.key -out deploy/tls/dev.crt \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost"
```

Production certificates are supplied externally and are **not** stored in this
repo (ARCH-031).
