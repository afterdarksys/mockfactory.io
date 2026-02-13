# MockFactory.io - Ansible Automation

Ansible playbooks and roles for deploying and managing MockFactory.io infrastructure.

## Structure

```
ansible/
├── ansible.cfg           # Ansible configuration
├── inventory/
│   ├── production        # Production inventory
│   ├── staging          # Staging inventory
│   └── group_vars/      # Group variables
├── playbooks/
│   ├── deploy-api.yml   # Deploy FastAPI application
│   ├── deploy-frontend.yml
│   ├── setup-docker.yml # Setup Docker on hosts
│   └── update-services.yml
├── roles/
│   ├── docker/          # Docker installation
│   ├── postgres/        # PostgreSQL setup
│   ├── redis/           # Redis setup
│   ├── nginx/           # Nginx configuration
│   └── mockfactory-api/ # API deployment
└── library/
    └── mockfactory.py   # Custom MockFactory API module

```

## Quick Start

```bash
cd ansible/

# Test connectivity
ansible all -i inventory/production -m ping

# Deploy entire stack
ansible-playbook -i inventory/production playbooks/deploy-stack.yml

# Update API only
ansible-playbook -i inventory/production playbooks/deploy-api.yml

# Run with vault password
ansible-playbook -i inventory/production playbooks/deploy-stack.yml --ask-vault-pass
```

## Custom MockFactory Module

The `library/mockfactory.py` module allows you to manage MockFactory resources via Ansible:

```yaml
- name: Create mock VPC
  mockfactory:
    api_key: "{{ mockfactory_api_key }}"
    resource: vpc
    action: create
    params:
      cidr_block: "10.0.0.0/16"
      environment_id: "{{ environment_id }}"
```

## Inventory

Hosts are organized by role:

- **api_servers**: FastAPI backend servers
- **db_servers**: PostgreSQL database servers
- **cache_servers**: Redis cache servers
- **web_servers**: Nginx frontend servers

## Playbooks

### deploy-stack.yml
Complete stack deployment:
1. Setup Docker
2. Deploy PostgreSQL
3. Deploy Redis
4. Deploy API
5. Deploy Nginx
6. Run migrations

### deploy-api.yml
API-only deployment:
1. Pull latest code
2. Build Docker image
3. Run database migrations
4. Restart API containers
5. Health check

### update-services.yml
Rolling update with zero downtime

## Vault Encryption

Sensitive variables are encrypted with ansible-vault:

```bash
# Encrypt secrets
ansible-vault encrypt group_vars/production/vault.yml

# Edit encrypted file
ansible-vault edit group_vars/production/vault.yml

# View encrypted file
ansible-vault view group_vars/production/vault.yml
```

## Requirements

```bash
# Install Ansible
brew install ansible

# Install community collections
ansible-galaxy collection install community.docker
ansible-galaxy collection install community.postgresql
```
