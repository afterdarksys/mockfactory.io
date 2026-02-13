// Real Claude AI Assistant for MockFactory (Paywalled Feature)

class ClaudeAssistantReal {
    constructor() {
        this.isOpen = false;
        this.messages = [];
        this.sessionId = this.generateSessionId();
        this.usage = null;
        this.setupEventListeners();
        this.loadUsage();
    }

    generateSessionId() {
        return `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }

    setupEventListeners() {
        // Open/close assistant
        document.getElementById('open-assistant').addEventListener('click', () => {
            this.open();
        });

        document.getElementById('close-assistant').addEventListener('click', () => {
            this.close();
        });

        // Send message
        document.getElementById('send-chat').addEventListener('click', () => {
            this.sendMessage();
        });

        document.getElementById('chat-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    open() {
        this.isOpen = true;
        document.getElementById('claude-assistant').classList.remove('translate-x-full');
        document.getElementById('open-assistant').classList.add('scale-0');
    }

    close() {
        this.isOpen = false;
        document.getElementById('claude-assistant').classList.add('translate-x-full');
        document.getElementById('open-assistant').classList.remove('scale-0');
    }

    async loadUsage() {
        try {
            const response = await APIClient.request('/ai/usage');
            this.usage = response;
            this.updateUsageDisplay();
        } catch (error) {
            console.error('Failed to load AI usage:', error);
        }
    }

    updateUsageDisplay() {
        if (!this.usage) return;

        // Show usage info in the chat header or as a banner
        const messagesContainer = document.getElementById('chat-messages');
        const existingBanner = document.getElementById('usage-banner');

        if (existingBanner) {
            existingBanner.remove();
        }

        if (!this.usage.has_access) {
            // Show paywall
            const banner = document.createElement('div');
            banner.id = 'usage-banner';
            banner.className = 'bg-yellow-100 dark:bg-yellow-900 text-yellow-900 dark:text-yellow-100 p-3 rounded-lg mb-4';
            banner.innerHTML = `
                <p class="text-sm font-semibold mb-2">🔒 AI Assistant is a Premium Feature</p>
                <p class="text-xs mb-2">Upgrade to Student tier or higher to chat with Claude!</p>
                <button onclick="window.location.href='/pricing.html'" class="text-xs bg-primary text-white px-3 py-1 rounded hover:bg-primary/90">
                    View Pricing
                </button>
            `;
            messagesContainer.insertBefore(banner, messagesContainer.firstChild);
        } else if (this.usage.daily_remaining <= 0) {
            // Daily limit reached
            const banner = document.createElement('div');
            banner.id = 'usage-banner';
            banner.className = 'bg-red-100 dark:bg-red-900 text-red-900 dark:text-red-100 p-3 rounded-lg mb-4';
            banner.innerHTML = `
                <p class="text-sm font-semibold mb-2">⚠️ Daily Limit Reached</p>
                <p class="text-xs mb-2">You've used all ${this.usage.daily_limit} messages today. Resets at midnight UTC.</p>
                <button onclick="window.location.href='/pricing.html'" class="text-xs bg-primary text-white px-3 py-1 rounded hover:bg-primary/90">
                    Upgrade Plan
                </button>
            `;
            messagesContainer.insertBefore(banner, messagesContainer.firstChild);
        } else if (this.usage.daily_remaining <= 3) {
            // Low on messages
            const banner = document.createElement('div');
            banner.id = 'usage-banner';
            banner.className = 'bg-orange-100 dark:bg-orange-900 text-orange-900 dark:text-orange-100 p-3 rounded-lg mb-4';
            banner.innerHTML = `
                <p class="text-xs">
                    ⚡ ${this.usage.daily_remaining} messages remaining today
                    ${this.usage.daily_remaining <= 1 ? '· Consider upgrading!' : ''}
                </p>
            `;
            messagesContainer.insertBefore(banner, messagesContainer.firstChild);
        } else {
            // Show usage stats
            const banner = document.createElement('div');
            banner.id = 'usage-banner';
            banner.className = 'bg-blue-50 dark:bg-gray-700 p-2 rounded-lg mb-4 text-xs text-gray-600 dark:text-gray-300';
            banner.innerHTML = `
                <div class="flex justify-between">
                    <span>Tier: <strong>${this.usage.tier}</strong></span>
                    <span>${this.usage.daily_remaining}/${this.usage.daily_limit} left today</span>
                </div>
            `;
            messagesContainer.insertBefore(banner, messagesContainer.firstChild);
        }
    }

    async sendMessage() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();

        if (!message) return;

        // Check if user has access
        if (this.usage && !this.usage.has_access) {
            this.showPaywall();
            return;
        }

        if (this.usage && this.usage.daily_remaining <= 0) {
            this.showLimitReached();
            return;
        }

        // Add user message
        this.addMessage(message, 'user');
        input.value = '';

        // Disable input while processing
        const sendButton = document.getElementById('send-chat');
        input.disabled = true;
        sendButton.disabled = true;

        // Show typing indicator
        this.showTyping();

        try {
            // Call real API
            const response = await APIClient.request('/ai/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: message,
                    session_id: this.sessionId,
                    context: {
                        environments: state.environments
                    }
                })
            });

            // Remove typing indicator
            this.hideTyping();

            // Add Claude's response
            this.addMessage(response.response, 'assistant', {
                tokens: response.tokens_used,
                cost: response.cost,
                remaining: response.messages_remaining
            });

            // Update usage
            this.usage.daily_remaining = response.messages_remaining;
            this.usage.daily_used = this.usage.daily_limit - response.messages_remaining;
            this.updateUsageDisplay();

        } catch (error) {
            this.hideTyping();

            // Handle specific errors
            if (error.message.includes('402') || error.message.includes('payment required')) {
                this.showPaywall();
            } else if (error.message.includes('429') || error.message.includes('limit reached')) {
                this.showLimitReached();
            } else {
                this.addMessage(
                    `Sorry, I encountered an error: ${error.message}\n\nPlease try again or contact support.`,
                    'error'
                );
            }
        } finally {
            input.disabled = false;
            sendButton.disabled = false;
            input.focus();
        }
    }

    addMessage(text, sender, metadata = null) {
        this.messages.push({ text, sender, metadata, timestamp: new Date() });

        const messagesContainer = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');

        if (sender === 'user') {
            messageDiv.className = 'bg-primary text-white rounded-lg p-3 ml-auto max-w-[80%]';
            messageDiv.innerHTML = `<p class="text-sm whitespace-pre-wrap">${this.escapeHtml(text)}</p>`;
        } else if (sender === 'error') {
            messageDiv.className = 'bg-red-100 dark:bg-red-900 text-red-900 dark:text-red-100 rounded-lg p-3 max-w-[80%]';
            messageDiv.innerHTML = `<p class="text-sm whitespace-pre-wrap">${this.escapeHtml(text)}</p>`;
        } else {
            messageDiv.className = 'bg-gray-100 dark:bg-gray-700 rounded-lg p-3 max-w-[80%]';

            let metadataHtml = '';
            if (metadata) {
                metadataHtml = `
                    <div class="mt-2 pt-2 border-t border-gray-300 dark:border-gray-600 text-xs text-gray-600 dark:text-gray-400 flex justify-between">
                        <span>Tokens: ${metadata.tokens.total}</span>
                        <span>Cost: $${metadata.cost.toFixed(4)}</span>
                        <span>${metadata.remaining} left</span>
                    </div>
                `;
            }

            messageDiv.innerHTML = `
                <p class="text-sm">
                    <span class="font-semibold text-primary">Claude:</span>
                    <span class="whitespace-pre-wrap">${this.formatMessage(text)}</span>
                </p>
                ${metadataHtml}
            `;
        }

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    showTyping() {
        const messagesContainer = document.getElementById('chat-messages');
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'bg-gray-100 dark:bg-gray-700 rounded-lg p-3 max-w-[80%]';
        typingDiv.innerHTML = `
            <p class="text-sm">
                <span class="font-semibold text-primary">Claude:</span>
                <span class="animate-pulse">Thinking...</span>
            </p>
        `;
        messagesContainer.appendChild(typingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    hideTyping() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    showPaywall() {
        const messagesContainer = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'bg-gradient-to-r from-primary to-secondary text-white rounded-lg p-4 max-w-full';
        messageDiv.innerHTML = `
            <p class="text-sm font-bold mb-2">🔒 Unlock AI Assistant</p>
            <p class="text-xs mb-3">Chat with Claude to get help with PostgreSQL, generate SQL, and more!</p>
            <div class="space-y-2 text-xs mb-3">
                <div class="flex justify-between">
                    <span>Student:</span>
                    <span class="font-bold">$4.99/mo · 10 msgs/day</span>
                </div>
                <div class="flex justify-between">
                    <span>Professional:</span>
                    <span class="font-bold">$19.99/mo · 100 msgs/day</span>
                </div>
                <div class="flex justify-between">
                    <span>Enterprise:</span>
                    <span class="font-bold">Custom · Unlimited</span>
                </div>
            </div>
            <button onclick="window.location.href='/pricing.html'" class="w-full bg-white text-primary px-4 py-2 rounded hover:bg-gray-100 font-semibold">
                View Pricing
            </button>
        `;
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    showLimitReached() {
        const messagesContainer = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'bg-yellow-100 dark:bg-yellow-900 text-yellow-900 dark:text-yellow-100 rounded-lg p-4 max-w-full';
        messageDiv.innerHTML = `
            <p class="text-sm font-bold mb-2">⚠️ Daily Limit Reached</p>
            <p class="text-xs mb-3">You've used all your messages for today. Your limit resets at midnight UTC.</p>
            <button onclick="window.location.href='/pricing.html'" class="w-full bg-primary text-white px-4 py-2 rounded hover:bg-primary/90 font-semibold">
                Upgrade for More Messages
            </button>
        `;
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    formatMessage(text) {
        // Basic markdown-like formatting
        return this.escapeHtml(text)
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/`(.+?)`/g, '<code style="background: rgba(0,0,0,0.1); padding: 2px 6px; border-radius: 3px; font-family: monospace;">$1</code>')
            .replace(/\n/g, '<br>');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Replace the fake assistant with the real one
const claude = new ClaudeAssistantReal();
