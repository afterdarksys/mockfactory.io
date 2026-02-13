// MockFactory Dashboard Application
const API_BASE = window.location.origin + '/api/v1';

// State management
const state = {
    user: null,
    environments: [],
    token: localStorage.getItem('mf_token') || null
};

// API client
class APIClient {
    static async request(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (state.token) {
            headers['Authorization'] = `Bearer ${state.token}`;
        }

        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            headers
        });

        if (response.status === 401) {
            // Token expired or invalid
            localStorage.removeItem('mf_token');
            window.location.href = '/login.html';
            return;
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || 'Request failed');
        }

        return response.json();
    }

    static async getEnvironments(statusFilter = null) {
        const query = statusFilter ? `?status_filter=${statusFilter}` : '';
        return this.request(`/environments${query}`);
    }

    static async createEnvironment(data) {
        return this.request('/environments/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    static async deleteEnvironment(envId) {
        return this.request(`/environments/${envId}`, {
            method: 'DELETE'
        });
    }

    static async stopEnvironment(envId) {
        return this.request(`/environments/${envId}/stop`, {
            method: 'POST'
        });
    }

    static async startEnvironment(envId) {
        return this.request(`/environments/${envId}/start`, {
            method: 'POST'
        });
    }
}

// UI Components
class Dashboard {
    static async init() {
        // Check authentication
        if (!state.token) {
            // For demo purposes, create a demo token
            // In production, redirect to login
            console.log('No token found, using demo mode');
            state.token = 'demo-token';
            state.user = { email: 'demo@mockfactory.io', tier: 'Free' };
        }

        this.setupEventListeners();
        await this.loadEnvironments();
        this.updateStats();
        this.startPolling();
    }

    static setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const view = e.currentTarget.dataset.view;
                this.switchView(view);
            });
        });

        // Create environment buttons
        document.getElementById('create-env-btn').addEventListener('click', () => {
            this.openCreateModal();
        });
        document.getElementById('create-env-btn-2').addEventListener('click', () => {
            this.openCreateModal();
        });

        // Modal close buttons
        document.querySelectorAll('.close-modal').forEach(btn => {
            btn.addEventListener('click', () => {
                this.closeCreateModal();
            });
        });

        // Create environment form
        document.getElementById('create-env-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.createEnvironment(e.target);
        });

        // Logout
        document.getElementById('logout-btn').addEventListener('click', () => {
            localStorage.removeItem('mf_token');
            window.location.href = '/';
        });

        // Update user info
        if (state.user) {
            document.getElementById('user-email').textContent = state.user.email;
            document.getElementById('user-tier').textContent = state.user.tier + ' Tier';
        }
    }

    static switchView(viewName) {
        // Hide all views
        document.querySelectorAll('.view-container').forEach(view => {
            view.classList.add('hidden');
        });

        // Show selected view
        document.getElementById(`${viewName}-view`).classList.remove('hidden');

        // Update nav
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('text-primary', 'bg-primary/10');
            link.classList.add('text-gray-600', 'dark:text-gray-300');
        });
        const activeLink = document.querySelector(`[data-view="${viewName}"]`);
        if (activeLink) {
            activeLink.classList.add('text-primary', 'bg-primary/10');
            activeLink.classList.remove('text-gray-600', 'dark:text-gray-300');
        }
    }

    static openCreateModal() {
        document.getElementById('create-env-modal').classList.remove('hidden');
    }

    static closeCreateModal() {
        document.getElementById('create-env-modal').classList.add('hidden');
        document.getElementById('create-env-form').reset();
    }

    static async createEnvironment(form) {
        const formData = new FormData(form);
        const selectedServices = Array.from(form.querySelectorAll('input[name="service"]:checked'))
            .map(input => input.value);

        if (selectedServices.length === 0) {
            alert('Please select at least one service');
            return;
        }

        const data = {
            name: formData.get('name') || undefined,
            services: selectedServices.map(type => ({
                type: type,
                version: 'latest',
                config: {}
            })),
            auto_shutdown_hours: parseInt(formData.get('auto_shutdown_hours'))
        };

        try {
            const submitButton = form.querySelector('button[type="submit"]');
            submitButton.disabled = true;
            submitButton.textContent = 'Creating...';

            await APIClient.createEnvironment(data);

            this.closeCreateModal();
            await this.loadEnvironments();
            this.updateStats();

            this.showNotification('Environment created successfully!', 'success');
        } catch (error) {
            console.error('Failed to create environment:', error);
            this.showNotification('Failed to create environment: ' + error.message, 'error');
        } finally {
            const submitButton = form.querySelector('button[type="submit"]');
            submitButton.disabled = false;
            submitButton.textContent = 'Create Environment';
        }
    }

    static async loadEnvironments() {
        try {
            const data = await APIClient.getEnvironments();
            state.environments = data.environments || [];
            this.renderEnvironments();
        } catch (error) {
            console.error('Failed to load environments:', error);
            // For demo, use empty array
            state.environments = [];
            this.renderEnvironments();
        }
    }

    static renderEnvironments() {
        const activeEnvs = state.environments.filter(env =>
            env.status === 'running' || env.status === 'provisioning'
        );

        // Render active environments
        const activeContainer = document.getElementById('active-environments');
        if (activeEnvs.length === 0) {
            activeContainer.innerHTML = `
                <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                    No active environments. Create one to get started!
                </div>
            `;
        } else {
            activeContainer.innerHTML = activeEnvs.map(env => this.renderEnvironmentCard(env)).join('');
        }

        // Render all environments
        const allContainer = document.getElementById('all-environments');
        if (state.environments.length === 0) {
            allContainer.innerHTML = `
                <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                    No environments yet. Create your first one!
                </div>
            `;
        } else {
            allContainer.innerHTML = state.environments.map(env => this.renderEnvironmentCard(env)).join('');
        }

        // Attach event listeners
        this.attachEnvironmentListeners();
    }

    static renderEnvironmentCard(env) {
        const statusColors = {
            'running': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
            'stopped': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
            'provisioning': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
            'destroying': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
            'error': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
        };

        const serviceNames = {
            'postgresql': 'PostgreSQL',
            'postgresql_supabase': 'PostgreSQL + Supabase',
            'postgresql_pgvector': 'PostgreSQL + pgvector',
            'postgresql_postgis': 'PostgreSQL + PostGIS',
            'redis': 'Redis',
            'aws_s3': 'AWS S3',
            'aws_sqs': 'AWS SQS',
            'aws_sns': 'AWS SNS'
        };

        const services = Object.keys(env.services).map(key =>
            serviceNames[key] || key
        ).join(', ');

        const endpoints = env.endpoints ? Object.entries(env.endpoints).map(([service, url]) => `
            <div class="flex items-center justify-between text-sm">
                <span class="text-gray-600 dark:text-gray-400">${service}:</span>
                <code class="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">${url}</code>
            </div>
        `).join('') : '';

        return `
            <div class="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6 fade-in">
                <div class="flex justify-between items-start mb-4">
                    <div>
                        <h3 class="text-lg font-bold">${env.name || env.id}</h3>
                        <p class="text-sm text-gray-500 dark:text-gray-400">${env.id}</p>
                    </div>
                    <span class="px-3 py-1 rounded-full text-xs font-semibold ${statusColors[env.status] || statusColors.error}">
                        ${env.status.toUpperCase()}
                    </span>
                </div>

                <div class="mb-4">
                    <p class="text-sm text-gray-600 dark:text-gray-400 mb-2">Services:</p>
                    <p class="text-sm">${services}</p>
                </div>

                ${endpoints ? `
                    <div class="mb-4 space-y-2">
                        ${endpoints}
                    </div>
                ` : ''}

                <div class="flex items-center justify-between mb-4 text-sm">
                    <span class="text-gray-600 dark:text-gray-400">Cost:</span>
                    <span class="font-bold text-primary">$${env.hourly_rate.toFixed(2)}/hr</span>
                </div>

                <div class="flex items-center justify-between mb-4 text-sm">
                    <span class="text-gray-600 dark:text-gray-400">Total spent:</span>
                    <span class="font-semibold">$${env.total_cost.toFixed(2)}</span>
                </div>

                <div class="flex space-x-2">
                    ${env.status === 'running' ? `
                        <button data-action="stop" data-env-id="${env.id}" class="flex-1 px-4 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 transition-colors text-sm font-semibold">
                            Stop
                        </button>
                    ` : ''}
                    ${env.status === 'stopped' ? `
                        <button data-action="start" data-env-id="${env.id}" class="flex-1 px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors text-sm font-semibold">
                            Start
                        </button>
                    ` : ''}
                    ${env.status !== 'destroying' ? `
                        <button data-action="delete" data-env-id="${env.id}" class="flex-1 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors text-sm font-semibold">
                            Destroy
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }

    static attachEnvironmentListeners() {
        document.querySelectorAll('[data-action]').forEach(button => {
            button.addEventListener('click', async (e) => {
                const action = e.currentTarget.dataset.action;
                const envId = e.currentTarget.dataset.envId;
                await this.handleEnvironmentAction(action, envId);
            });
        });
    }

    static async handleEnvironmentAction(action, envId) {
        try {
            switch (action) {
                case 'stop':
                    await APIClient.stopEnvironment(envId);
                    this.showNotification('Environment stopped', 'success');
                    break;
                case 'start':
                    await APIClient.startEnvironment(envId);
                    this.showNotification('Environment started', 'success');
                    break;
                case 'delete':
                    if (confirm('Are you sure you want to destroy this environment? This cannot be undone.')) {
                        await APIClient.deleteEnvironment(envId);
                        this.showNotification('Environment destroyed', 'success');
                    }
                    break;
            }
            await this.loadEnvironments();
            this.updateStats();
        } catch (error) {
            console.error(`Failed to ${action} environment:`, error);
            this.showNotification(`Failed to ${action} environment: ` + error.message, 'error');
        }
    }

    static updateStats() {
        const runningEnvs = state.environments.filter(env => env.status === 'running');
        const totalCost = runningEnvs.reduce((sum, env) => sum + env.hourly_rate, 0);
        const totalSpent = state.environments.reduce((sum, env) => sum + env.total_cost, 0);

        document.getElementById('stat-active').textContent = runningEnvs.length;
        document.getElementById('stat-cost').textContent = `$${totalCost.toFixed(2)}/hr`;
        document.getElementById('stat-spent').textContent = `$${totalSpent.toFixed(2)}`;
    }

    static showNotification(message, type = 'info') {
        // Simple notification - could be enhanced with a toast library
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            info: 'bg-blue-500'
        };

        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 fade-in`;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    static startPolling() {
        // Poll for environment updates every 10 seconds
        setInterval(async () => {
            await this.loadEnvironments();
            this.updateStats();
        }, 10000);
    }
}

// Initialize dashboard when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Dashboard.init());
} else {
    Dashboard.init();
}
