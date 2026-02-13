# MockFactory Plugin Marketplace - Implementation Plan

Complete technical roadmap for plugin marketplace integration into mocklib and website.

## Part 1: MockLib SDK Enhancements

### 1.1 Plugin SDK (New Package)

Create `mocklib-plugin-sdk` for plugin developers in all languages:

**Python Plugin SDK** (`mocklib-plugin-sdk-python/`):

```python
# mocklib_plugin_sdk/__init__.py

from .sdk import PluginSDK, Plugin, Request, Response
from .storage import Storage
from .webhooks import Webhooks
from .decorators import endpoint, requires_auth

__all__ = [
    "PluginSDK",
    "Plugin",
    "Request",
    "Response",
    "Storage",
    "Webhooks",
    "endpoint",
    "requires_auth",
]
```

```python
# mocklib_plugin_sdk/sdk.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import uuid
from datetime import datetime

class Request:
    """Incoming API request to plugin"""
    def __init__(self, method: str, path: str, headers: Dict, body: Any, user_id: str):
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body
        self.user_id = user_id

    def json(self) -> Dict:
        """Parse body as JSON"""
        return self.body if isinstance(self.body, dict) else {}

    def get_header(self, key: str, default: str = None) -> str:
        return self.headers.get(key, default)

class Response:
    """Plugin response"""
    def __init__(self, status_code: int, body: Any, headers: Dict = None):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}

class Plugin(ABC):
    """Base class for all plugins"""

    @abstractmethod
    def initialize(self, sdk: 'PluginSDK') -> None:
        """Called once when plugin loads"""
        pass

    @abstractmethod
    def handle_request(self, request: Request) -> Response:
        """Handle incoming API request"""
        pass

    def health(self) -> bool:
        """Health check - return True if healthy"""
        return True

    def cleanup(self) -> None:
        """Called when plugin unloads"""
        pass

class PluginSDK:
    """SDK provided to plugins by MockFactory"""

    def __init__(self, plugin_name: str, user_id: str, api_url: str, api_key: str):
        self.plugin_name = plugin_name
        self.user_id = user_id
        self.api_url = api_url
        self.api_key = api_key

        # Initialize services
        self.storage = Storage(self)
        self.webhooks = Webhooks(self)
        self.metrics = Metrics(self)
        self.logger = Logger(plugin_name)

    def generate_id(self, prefix: str = "") -> str:
        """Generate unique ID with optional prefix"""
        return f"{prefix}{uuid.uuid4().hex[:24]}"

    def now(self) -> datetime:
        """Current timestamp"""
        return datetime.utcnow()

    def random_string(self, length: int = 32) -> str:
        """Generate random string"""
        import random
        import string
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
```

```python
# mocklib_plugin_sdk/storage.py

class Storage:
    """Key-value storage for plugin state"""

    def __init__(self, sdk):
        self.sdk = sdk
        self._http_client = None

    def put(self, collection: str, key: str, value: Dict) -> None:
        """Store a value"""
        response = requests.post(
            f"{self.sdk.api_url}/plugin-storage/{self.sdk.plugin_name}/{collection}",
            headers={"Authorization": f"Bearer {self.sdk.api_key}"},
            json={"key": key, "value": value}
        )
        response.raise_for_status()

    def get(self, collection: str, key: str) -> Optional[Dict]:
        """Retrieve a value"""
        response = requests.get(
            f"{self.sdk.api_url}/plugin-storage/{self.sdk.plugin_name}/{collection}/{key}",
            headers={"Authorization": f"Bearer {self.sdk.api_key}"}
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def query(self, collection: str, filters: Dict = None, limit: int = 100) -> List[Dict]:
        """Query collection"""
        response = requests.post(
            f"{self.sdk.api_url}/plugin-storage/{self.sdk.plugin_name}/{collection}/query",
            headers={"Authorization": f"Bearer {self.sdk.api_key}"},
            json={"filters": filters or {}, "limit": limit}
        )
        response.raise_for_status()
        return response.json()["results"]

    def delete(self, collection: str, key: str) -> None:
        """Delete a value"""
        response = requests.delete(
            f"{self.sdk.api_url}/plugin-storage/{self.sdk.plugin_name}/{collection}/{key}",
            headers={"Authorization": f"Bearer {self.sdk.api_key}"}
        )
        response.raise_for_status()
```

```python
# mocklib_plugin_sdk/decorators.py

from functools import wraps

def endpoint(method: str, path: str):
    """Decorator to mark endpoint handlers"""
    def decorator(func):
        func._endpoint = True
        func._method = method
        func._path = path
        return func
    return decorator

def requires_auth(func):
    """Decorator to require authentication"""
    @wraps(func)
    def wrapper(self, request: Request):
        auth = request.get_header("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return Response(401, {"error": "Unauthorized"})
        return func(self, request)
    return wrapper
```

**Example Stripe Plugin Using SDK**:

```python
# plugin.py - Stripe plugin example

from mocklib_plugin_sdk import Plugin, PluginSDK, Request, Response, endpoint

class StripePlugin(Plugin):
    def initialize(self, sdk: PluginSDK):
        self.sdk = sdk
        self.sdk.logger.info("Stripe plugin initialized")

    def handle_request(self, request: Request) -> Response:
        # Route based on path
        if request.path.startswith("/customers"):
            return self._handle_customers(request)
        elif request.path.startswith("/charges"):
            return self._handle_charges(request)
        else:
            return Response(404, {"error": "Not found"})

    def _handle_customers(self, request: Request) -> Response:
        if request.method == "POST":
            return self._create_customer(request)
        elif request.method == "GET":
            return self._get_customer(request)
        else:
            return Response(405, {"error": "Method not allowed"})

    def _create_customer(self, request: Request) -> Response:
        data = request.json()

        # Generate customer ID
        customer_id = self.sdk.generate_id("cus_")

        # Create customer object
        customer = {
            "id": customer_id,
            "email": data.get("email"),
            "name": data.get("name"),
            "created": int(self.sdk.now().timestamp()),
        }

        # Store in plugin storage
        self.sdk.storage.put("customers", customer_id, customer)

        # Track metric
        self.sdk.metrics.counter("customers_created")

        # Send webhook
        self.sdk.webhooks.send("customer.created", customer)

        return Response(200, customer)

    def _get_customer(self, request: Request) -> Response:
        # Extract customer ID from path: /customers/cus_xxx
        customer_id = request.path.split("/")[-1]

        customer = self.sdk.storage.get("customers", customer_id)
        if not customer:
            return Response(404, {"error": "Customer not found"})

        return Response(200, customer)

# Entry point
def create_plugin(sdk: PluginSDK) -> Plugin:
    return StripePlugin()
```

### 1.2 MockLib Client Enhancements

Add plugin support to all existing SDKs:

**Python SDK** (`mocklib/client.py`):

```python
class MockFactory:
    def __init__(self, api_key: str = None, api_url: str = "https://api.mockfactory.io/v1"):
        # Existing initialization...

        # Plugin support
        self.plugins = PluginManager(self)

    def __getattr__(self, name):
        """Dynamic plugin access: mf.stripe, mf.twilio, etc."""
        return self.plugins.get(name)

class PluginManager:
    """Manages installed plugins"""

    def __init__(self, client):
        self.client = client
        self._cache = {}

    def get(self, plugin_name: str):
        """Get plugin client"""
        if plugin_name not in self._cache:
            self._cache[plugin_name] = PluginClient(self.client, plugin_name)
        return self._cache[plugin_name]

    def install(self, plugin_name: str, version: str = "latest") -> Dict:
        """Install a plugin"""
        return self.client.post("/plugins/install", {
            "plugin": plugin_name,
            "version": version
        })

    def uninstall(self, plugin_name: str) -> Dict:
        """Uninstall a plugin"""
        return self.client.post("/plugins/uninstall", {
            "plugin": plugin_name
        })

    def list_installed(self) -> List[Dict]:
        """List installed plugins"""
        return self.client.get("/plugins/installed")

    def list_available(self, category: str = None) -> List[Dict]:
        """Browse marketplace"""
        params = {}
        if category:
            params["category"] = category
        return self.client.get("/marketplace/plugins", params=params)

class PluginClient:
    """Dynamic client for a specific plugin"""

    def __init__(self, client, plugin_name):
        self.client = client
        self.plugin_name = plugin_name
        self.base_path = f"/plugins/{plugin_name}/v1"

    def __getattr__(self, name):
        """Dynamic resource access: mf.stripe.customers, mf.stripe.charges"""
        return PluginResource(self.client, self.base_path, name)

class PluginResource:
    """Dynamic resource client for plugin endpoints"""

    def __init__(self, client, base_path, resource_name):
        self.client = client
        self.base_path = base_path
        self.resource_name = resource_name

    def create(self, **kwargs):
        """POST /{resource}"""
        return self.client.post(f"{self.base_path}/{self.resource_name}", kwargs)

    def get(self, id: str):
        """GET /{resource}/{id}"""
        return self.client.get(f"{self.base_path}/{self.resource_name}/{id}")

    def list(self, **params):
        """GET /{resource}"""
        return self.client.get(f"{self.base_path}/{self.resource_name}", params=params)

    def update(self, id: str, **kwargs):
        """PUT /{resource}/{id}"""
        return self.client.put(f"{self.base_path}/{self.resource_name}/{id}", kwargs)

    def delete(self, id: str):
        """DELETE /{resource}/{id}"""
        return self.client.delete(f"{self.base_path}/{self.resource_name}/{id}")
```

**Usage Example**:

```python
from mocklib import MockFactory

mf = MockFactory(api_key="mf_...")

# Browse marketplace
plugins = mf.plugins.list_available(category="payments")
print(f"Found {len(plugins)} payment plugins")

# Install Stripe plugin
mf.plugins.install("stripe", version="1.2.0")

# Use Stripe plugin (dynamic!)
customer = mf.stripe.customers.create(
    email="customer@example.com",
    name="John Doe"
)

charge = mf.stripe.charges.create(
    amount=2000,
    currency="usd",
    customer=customer["id"]
)

print(f"Charge created: {charge['id']}")
```

### 1.3 CLI Enhancements

Add plugin commands to `mocklib-cli`:

```bash
# Plugin management
mocklib plugin list                      # List installed plugins
mocklib plugin search stripe             # Search marketplace
mocklib plugin install stripe            # Install plugin
mocklib plugin uninstall stripe          # Uninstall plugin
mocklib plugin info stripe               # Show plugin details

# Plugin development
mocklib plugin init --name my-plugin --language python
mocklib plugin test                      # Run plugin tests
mocklib plugin validate                  # Validate manifest
mocklib plugin publish                   # Publish to marketplace
mocklib plugin logs                      # View plugin logs

# Marketplace browsing
mocklib marketplace browse               # Browse all plugins
mocklib marketplace search payments      # Search by keyword
mocklib marketplace trending             # Trending plugins
```

**CLI Implementation** (`mocklib-cli/plugin.go`):

```go
package main

import "fmt"

func pluginList() error {
    resp, err := makeRequest("GET", "/plugins/installed", nil)
    if err != nil {
        return err
    }

    plugins := resp["plugins"].([]interface{})

    fmt.Println("Installed Plugins:")
    fmt.Println("==================")
    for _, p := range plugins {
        plugin := p.(map[string]interface{})
        fmt.Printf("  %s@%s - %s\n",
            plugin["name"],
            plugin["version"],
            plugin["description"],
        )
    }

    return nil
}

func pluginInstall(pluginName, version string) error {
    if version == "" {
        version = "latest"
    }

    reqBody := map[string]interface{}{
        "plugin":  pluginName,
        "version": version,
    }

    resp, err := makeRequest("POST", "/plugins/install", reqBody)
    if err != nil {
        return err
    }

    fmt.Printf("✓ Installed %s@%s\n", pluginName, resp["version"])
    fmt.Printf("  API: /plugins/%s/v1\n", pluginName)

    return nil
}

func pluginSearch(query string) error {
    resp, err := makeRequest("GET", "/marketplace/plugins", map[string]interface{}{
        "q": query,
    })
    if err != nil {
        return err
    }

    plugins := resp["plugins"].([]interface{})

    fmt.Printf("Found %d plugins:\n\n", len(plugins))

    for _, p := range plugins {
        plugin := p.(map[string]interface{})
        fmt.Printf("%s - %s\n", plugin["name"], plugin["display_name"])
        fmt.Printf("  %s\n", plugin["description"])
        fmt.Printf("  Price: $%.3f/call | Rating: ★%.1f | Users: %d\n",
            plugin["price_per_call"],
            plugin["rating"],
            int(plugin["user_count"].(float64)),
        )
        fmt.Println()
    }

    return nil
}
```

## Part 2: Website Enhancements

### 2.1 Database Schema

Add tables for plugin marketplace:

```sql
-- app/migrations/xxx_create_plugin_tables.sql

-- Plugin registry
CREATE TABLE plugins (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    tags TEXT[],

    -- Author info
    author_id BIGINT REFERENCES users(id),
    author_name VARCHAR(255),
    author_email VARCHAR(255),

    -- Pricing
    pricing_tier VARCHAR(50) DEFAULT 'standard',
    per_call_price_cents INT DEFAULT 100, -- $0.001
    free_tier_calls INT DEFAULT 1000,
    revenue_share DECIMAL(3,2) DEFAULT 0.70,

    -- API info
    base_path VARCHAR(500),
    api_version VARCHAR(50) DEFAULT 'v1',

    -- Runtime
    language VARCHAR(50),
    runtime_version VARCHAR(50),
    memory_limit_mb INT DEFAULT 128,
    timeout_seconds INT DEFAULT 10,

    -- Status
    status VARCHAR(50) DEFAULT 'draft', -- draft, pending_review, active, suspended
    verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMPTZ,

    -- Stats
    install_count INT DEFAULT 0,
    rating_avg DECIMAL(3,2) DEFAULT 0.0,
    rating_count INT DEFAULT 0,
    api_call_count BIGINT DEFAULT 0,

    -- Timestamps
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_plugins_status ON plugins(status);
CREATE INDEX idx_plugins_category ON plugins(category);
CREATE INDEX idx_plugins_author ON plugins(author_id);

-- Plugin versions
CREATE TABLE plugin_versions (
    id BIGSERIAL PRIMARY KEY,
    plugin_id BIGINT REFERENCES plugins(id),
    version VARCHAR(50) NOT NULL,

    -- Manifest
    manifest JSONB,

    -- Storage
    binary_url VARCHAR(500),
    checksum VARCHAR(64),
    size_bytes BIGINT,

    -- Status
    status VARCHAR(50) DEFAULT 'active',

    -- Timestamps
    published_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(plugin_id, version)
);

-- User plugin installations
CREATE TABLE user_plugins (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    plugin_id BIGINT REFERENCES plugins(id),
    plugin_version_id BIGINT REFERENCES plugin_versions(id),

    status VARCHAR(50) DEFAULT 'active',
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,

    UNIQUE(user_id, plugin_id)
);

CREATE INDEX idx_user_plugins_user ON user_plugins(user_id);

-- Plugin API calls (for metering)
CREATE TABLE plugin_api_calls (
    id BIGSERIAL PRIMARY KEY,
    plugin_id BIGINT REFERENCES plugins(id),
    plugin_version_id BIGINT REFERENCES plugin_versions(id),
    user_id BIGINT REFERENCES users(id),

    -- Request info
    method VARCHAR(10),
    endpoint VARCHAR(500),
    status_code INT,
    latency_ms INT,

    -- Billing
    billable BOOLEAN DEFAULT TRUE,
    amount_cents INT,

    -- Timestamp
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_plugin_calls_billing
ON plugin_api_calls(plugin_id, timestamp, billable)
WHERE billable = TRUE;

-- Plugin payouts
CREATE TABLE plugin_payouts (
    id BIGSERIAL PRIMARY KEY,
    plugin_id BIGINT REFERENCES plugins(id),
    author_id BIGINT REFERENCES users(id),

    -- Period
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,

    -- Stats
    api_call_count BIGINT,
    revenue_cents BIGINT,
    payout_cents BIGINT,

    -- Payment
    stripe_transfer_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    paid_at TIMESTAMPTZ,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Plugin reviews
CREATE TABLE plugin_reviews (
    id BIGSERIAL PRIMARY KEY,
    plugin_id BIGINT REFERENCES plugins(id),
    user_id BIGINT REFERENCES users(id),

    rating INT CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,

    helpful_count INT DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(plugin_id, user_id)
);

CREATE INDEX idx_reviews_plugin ON plugin_reviews(plugin_id);
```

### 2.2 API Endpoints

Add plugin marketplace API routes:

```python
# app/api/plugins.py

from flask import Blueprint, request, jsonify
from app.models import Plugin, PluginVersion, UserPlugin, PluginAPICall
from app.auth import require_auth

bp = Blueprint('plugins', __name__)

@bp.route('/marketplace/plugins', methods=['GET'])
def list_marketplace_plugins():
    """Browse marketplace"""
    category = request.args.get('category')
    search = request.args.get('q')
    sort = request.args.get('sort', 'popular')

    query = Plugin.query.filter_by(status='active')

    if category:
        query = query.filter_by(category=category)

    if search:
        query = query.filter(Plugin.name.ilike(f'%{search}%'))

    # Sort
    if sort == 'popular':
        query = query.order_by(Plugin.install_count.desc())
    elif sort == 'rating':
        query = query.order_by(Plugin.rating_avg.desc())
    elif sort == 'newest':
        query = query.order_by(Plugin.published_at.desc())

    plugins = query.limit(50).all()

    return jsonify({
        'plugins': [p.to_marketplace_dict() for p in plugins]
    })

@bp.route('/marketplace/plugins/<plugin_name>', methods=['GET'])
def get_plugin_details(plugin_name):
    """Get plugin details"""
    plugin = Plugin.query.filter_by(name=plugin_name).first_or_404()

    # Get versions
    versions = PluginVersion.query.filter_by(plugin_id=plugin.id).all()

    # Get reviews
    reviews = plugin.reviews.order_by(PluginReview.helpful_count.desc()).limit(10).all()

    return jsonify({
        'plugin': plugin.to_dict(),
        'versions': [v.to_dict() for v in versions],
        'reviews': [r.to_dict() for r in reviews],
    })

@bp.route('/plugins/install', methods=['POST'])
@require_auth
def install_plugin(current_user):
    """Install a plugin"""
    data = request.json
    plugin_name = data.get('plugin')
    version = data.get('version', 'latest')

    plugin = Plugin.query.filter_by(name=plugin_name).first_or_404()

    # Get version
    if version == 'latest':
        plugin_version = plugin.latest_version
    else:
        plugin_version = PluginVersion.query.filter_by(
            plugin_id=plugin.id,
            version=version
        ).first_or_404()

    # Check if already installed
    existing = UserPlugin.query.filter_by(
        user_id=current_user.id,
        plugin_id=plugin.id
    ).first()

    if existing:
        # Update version
        existing.plugin_version_id = plugin_version.id
        existing.status = 'active'
    else:
        # Create new installation
        user_plugin = UserPlugin(
            user_id=current_user.id,
            plugin_id=plugin.id,
            plugin_version_id=plugin_version.id
        )
        db.session.add(user_plugin)

        # Increment install count
        plugin.install_count += 1

    db.session.commit()

    return jsonify({
        'success': True,
        'plugin': plugin.name,
        'version': plugin_version.version,
        'base_path': f'/plugins/{plugin.name}/{plugin.api_version}'
    })

@bp.route('/plugins/installed', methods=['GET'])
@require_auth
def list_installed_plugins(current_user):
    """List user's installed plugins"""
    user_plugins = UserPlugin.query.filter_by(
        user_id=current_user.id,
        status='active'
    ).all()

    return jsonify({
        'plugins': [up.to_dict() for up in user_plugins]
    })

@bp.route('/plugins/<plugin_name>/v1/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@require_auth
def proxy_to_plugin(current_user, plugin_name, endpoint):
    """Proxy API call to plugin"""

    # Get plugin
    plugin = Plugin.query.filter_by(name=plugin_name).first_or_404()

    # Check user has it installed
    user_plugin = UserPlugin.query.filter_by(
        user_id=current_user.id,
        plugin_id=plugin.id,
        status='active'
    ).first()

    if not user_plugin:
        return jsonify({'error': 'Plugin not installed'}), 403

    # Meter the call (for billing)
    call = PluginAPICall(
        plugin_id=plugin.id,
        plugin_version_id=user_plugin.plugin_version_id,
        user_id=current_user.id,
        method=request.method,
        endpoint=f'/{endpoint}',
        amount_cents=plugin.per_call_price_cents
    )

    # Forward to plugin (implementation depends on plugin runtime)
    try:
        result = plugin_runtime.execute(
            plugin=plugin,
            method=request.method,
            path=f'/{endpoint}',
            headers=dict(request.headers),
            body=request.get_json() if request.is_json else request.data,
            user_id=current_user.id
        )

        call.status_code = result.status_code
        call.latency_ms = result.latency_ms

    except Exception as e:
        call.status_code = 500
        call.billable = False  # Don't charge for errors
        db.session.add(call)
        db.session.commit()
        raise

    db.session.add(call)
    db.session.commit()

    # Update last used
    user_plugin.last_used_at = datetime.utcnow()
    db.session.commit()

    return jsonify(result.body), result.status_code
```

### 2.3 Developer Dashboard

Create developer dashboard for plugin creators:

**Frontend** (`frontend/src/pages/DeveloperDashboard.tsx`):

```typescript
import React, { useState, useEffect } from 'react';
import { Line, Bar } from 'recharts';

export function DeveloperDashboard() {
  const [stats, setStats] = useState(null);
  const [plugins, setPlugins] = useState([]);

  useEffect(() => {
    fetchDeveloperStats();
  }, []);

  return (
    <div className="developer-dashboard">
      <h1>Developer Dashboard</h1>

      {/* Revenue Overview */}
      <div className="revenue-cards">
        <Card>
          <h3>Current Period Revenue</h3>
          <div className="big-number">${stats?.current_revenue}</div>
          <div className="change">+{stats?.revenue_change}% vs last period</div>
        </Card>

        <Card>
          <h3>Next Payout</h3>
          <div className="big-number">${stats?.next_payout}</div>
          <div className="date">Feb 15, 2026</div>
        </Card>

        <Card>
          <h3>Total API Calls</h3>
          <div className="big-number">{stats?.api_calls}</div>
          <div className="change">+{stats?.calls_change}% vs last period</div>
        </Card>
      </div>

      {/* Revenue Chart */}
      <Card>
        <h3>Revenue Trend</h3>
        <LineChart data={stats?.revenue_trend} />
      </Card>

      {/* Plugins Table */}
      <Card>
        <h3>Your Plugins</h3>
        <table>
          <thead>
            <tr>
              <th>Plugin</th>
              <th>Installs</th>
              <th>API Calls</th>
              <th>Revenue (30d)</th>
              <th>Rating</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {plugins.map(plugin => (
              <tr key={plugin.id}>
                <td>{plugin.display_name}</td>
                <td>{plugin.install_count}</td>
                <td>{plugin.api_call_count_30d}</td>
                <td>${plugin.revenue_30d}</td>
                <td>★{plugin.rating_avg} ({plugin.rating_count})</td>
                <td><Badge status={plugin.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Publish New Plugin */}
      <Button onClick={() => router.push('/developer/plugins/new')}>
        Publish New Plugin
      </Button>
    </div>
  );
}
```

### 2.4 Marketplace UI

Create marketplace browse/search interface:

**Frontend** (`frontend/src/pages/Marketplace.tsx`):

```typescript
export function Marketplace() {
  const [plugins, setPlugins] = useState([]);
  const [category, setCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  return (
    <div className="marketplace">
      <header>
        <h1>Plugin Marketplace</h1>
        <p>Extend MockFactory with community plugins</p>
      </header>

      {/* Search & Filters */}
      <div className="filters">
        <SearchBar
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search plugins..."
        />

        <CategoryFilter
          categories={['All', 'Payments', 'Communication', 'Monitoring', 'Storage']}
          selected={category}
          onChange={setCategory}
        />

        <SortDropdown
          options={['Popular', 'Newest', 'Highest Rated']}
        />
      </div>

      {/* Plugin Grid */}
      <div className="plugin-grid">
        {plugins.map(plugin => (
          <PluginCard key={plugin.id} plugin={plugin} />
        ))}
      </div>
    </div>
  );
}

function PluginCard({ plugin }) {
  return (
    <div className="plugin-card">
      <div className="plugin-icon">
        {plugin.icon ? <img src={plugin.icon} /> : <DefaultIcon />}
      </div>

      <h3>{plugin.display_name}</h3>
      {plugin.verified && <VerifiedBadge />}

      <p>{plugin.description}</p>

      <div className="plugin-stats">
        <span>★{plugin.rating_avg} ({plugin.rating_count})</span>
        <span>{plugin.install_count} installs</span>
      </div>

      <div className="plugin-pricing">
        ${plugin.per_call_price} per call
        <small>{plugin.free_tier_calls} free/month</small>
      </div>

      <Button onClick={() => installPlugin(plugin.name)}>
        Install
      </Button>
    </div>
  );
}
```

## Part 3: Plugin Runtime

### 3.1 Plugin Execution Engine

Implement secure plugin execution:

```python
# app/plugins/runtime.py

import docker
import json
from typing import Dict, Any

class PluginRuntime:
    """Executes plugins in isolated containers"""

    def __init__(self):
        self.docker_client = docker.from_env()
        self.containers = {}

    def load_plugin(self, plugin: Plugin, version: PluginVersion):
        """Load plugin into runtime"""

        # Pull plugin image (pre-built during publish)
        image_name = f"mockfactory/plugin-{plugin.name}:{version.version}"
        self.docker_client.images.pull(image_name)

        # Start container
        container = self.docker_client.containers.run(
            image_name,
            detach=True,
            network_mode='none',  # No network access
            mem_limit=f"{plugin.memory_limit_mb}m",
            cpu_period=100000,
            cpu_quota=50000,  # 50% CPU limit
            environment={
                'PLUGIN_NAME': plugin.name,
                'API_URL': Config.API_URL,
            },
            labels={
                'plugin': plugin.name,
                'version': version.version,
            }
        )

        # Store container reference
        self.containers[plugin.id] = container

        return container

    def execute(self, plugin: Plugin, method: str, path: str, headers: Dict, body: Any, user_id: str) -> Dict:
        """Execute plugin request"""

        container = self.containers.get(plugin.id)
        if not container:
            raise RuntimeError(f"Plugin {plugin.name} not loaded")

        # Build request payload
        request_data = {
            'method': method,
            'path': path,
            'headers': headers,
            'body': body,
            'user_id': user_id,
        }

        # Execute in container (via HTTP endpoint the plugin exposes)
        # Or via stdin/stdout pipe
        result = self._exec_in_container(container, request_data)

        return result

    def unload_plugin(self, plugin_id: int):
        """Unload plugin from runtime"""
        container = self.containers.get(plugin_id)
        if container:
            container.stop()
            container.remove()
            del self.containers[plugin_id]
```

### 3.2 Plugin Storage Backend

Implement plugin-specific storage:

```python
# app/plugins/storage.py

class PluginStorage:
    """Storage backend for plugins"""

    def put(self, plugin_name: str, collection: str, key: str, value: Dict) -> None:
        """Store value in plugin's namespace"""

        # Store in Redis or PostgreSQL JSONB
        storage_key = f"plugin:{plugin_name}:{collection}:{key}"

        redis_client.set(
            storage_key,
            json.dumps(value),
            ex=86400 * 30  # 30 day TTL
        )

    def get(self, plugin_name: str, collection: str, key: str) -> Optional[Dict]:
        """Retrieve value"""
        storage_key = f"plugin:{plugin_name}:{collection}:{key}"

        data = redis_client.get(storage_key)
        if not data:
            return None

        return json.loads(data)

    def query(self, plugin_name: str, collection: str, filters: Dict, limit: int) -> List[Dict]:
        """Query collection"""

        # Use PostgreSQL for complex queries
        # For simplicity, scan Redis keys
        pattern = f"plugin:{plugin_name}:{collection}:*"
        keys = redis_client.keys(pattern)

        results = []
        for key in keys[:limit]:
            data = redis_client.get(key)
            if data:
                results.append(json.loads(data))

        return results
```

## Timeline & Resources

**Phase 1: SDK Development** (3 weeks)
- Week 1: Plugin SDK (Python, Go)
- Week 2: Client SDK enhancements (Python, Node.js, Go)
- Week 3: CLI enhancements, documentation

**Phase 2: Platform Backend** (3 weeks)
- Week 4: Database schema, API endpoints
- Week 5: Plugin runtime, storage backend
- Week 6: Metering, billing integration

**Phase 3: Frontend & Marketplace** (2 weeks)
- Week 7: Marketplace UI, search
- Week 8: Developer dashboard, analytics

**Phase 4: Reference Plugins** (2 weeks)
- Week 9-10: Build 5 reference plugins (Stripe, Twilio, SendGrid, Datadog, GitHub)

**Phase 5: Testing & Launch** (2 weeks)
- Week 11: Private beta (20 developers)
- Week 12: Public launch

**Total: 12 weeks**

**Team Required**:
- 2 backend engineers
- 1 frontend engineer
- 1 DevOps engineer (plugin runtime, containers)
- 1 technical writer (documentation)

**Investment**: ~$150k (salaries + infrastructure + legal)

**ROI**: Platform fee revenue from day 1 of launch! 🚀
