# OCI Secrets Configuration

This directory contains templates for OCI (Oracle Cloud Infrastructure) credentials needed for production deployment.

## Setup Instructions

### 1. Create the secrets directory

```bash
mkdir -p secrets
```

### 2. Copy and configure OCI config

```bash
cp secrets.template/oci_config.example secrets/oci_config
```

Edit `secrets/oci_config` and fill in your OCI credentials:
- `user`: Your OCI user OCID
- `fingerprint`: Your API key fingerprint
- `tenancy`: Your OCI tenancy OCID
- `region`: Your OCI region (e.g., us-ashburn-1)
- `key_file`: Keep as `/run/secrets/oci_key` (Docker secret mount path)

### 3. Add your OCI private key

```bash
cp ~/.oci/your_private_key.pem secrets/oci_key.pem
chmod 600 secrets/oci_key.pem
```

### 4. Verify the setup

Your secrets directory should now contain:
```
secrets/
├── oci_config          # OCI CLI configuration
└── oci_key.pem         # Your private API key
```

### 5. Git ignore

These files are already in `.gitignore` and will NOT be committed to version control.

## How It Works

When you run `docker-compose -f docker-compose.prod.yml up`:

1. Docker reads secrets from `secrets/oci_config` and `secrets/oci_key.pem`
2. Mounts them inside the container at:
   - `/run/secrets/oci_config`
   - `/run/secrets/oci_key`
3. Environment variables point to these paths:
   - `OCI_CONFIG_FILE=/run/secrets/oci_config`
   - `OCI_KEY_FILE=/run/secrets/oci_key`
4. The OCI CLI inside the container uses these credentials

## Security Notes

- **Never commit actual credentials to git**
- The `secrets/` directory is in `.gitignore`
- Use Docker secrets (not environment variables) for sensitive data
- In production, consider using OCI Vault or Kubernetes secrets instead
- Rotate keys regularly
- Use least-privilege IAM policies

## Testing OCI Access

Once configured, test OCI CLI access from inside the container:

```bash
docker-compose -f docker-compose.prod.yml exec api bash
oci os ns get  # Should return your object storage namespace
```

## Required OCI Permissions

The OCI user needs these IAM permissions for MockFactory.io:

- `objectstorage.buckets.create`
- `objectstorage.buckets.delete`
- `objectstorage.objects.create`
- `objectstorage.objects.read`
- `objectstorage.objects.delete`
- `objectstorage.objects.list`

Example IAM policy:

```
Allow group mockfactory-api to manage objects in compartment mockfactory
Allow group mockfactory-api to manage buckets in compartment mockfactory
```

## Troubleshooting

### "ConfigFileNotFound" error
- Verify `secrets/oci_config` exists
- Check `OCI_CONFIG_FILE` environment variable in docker-compose.prod.yml

### "Invalid key file" error
- Verify `secrets/oci_key.pem` exists
- Check the `key_file` path in `oci_config` matches `/run/secrets/oci_key`
- Ensure key file has correct format (begins with `-----BEGIN RSA PRIVATE KEY-----`)

### "ServiceError: NotAuthenticated"
- Verify your OCI credentials are correct
- Check fingerprint matches your key
- Ensure user OCID and tenancy OCID are correct
