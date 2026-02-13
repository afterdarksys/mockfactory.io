// Claude AI Assistant for MockFactory

class ClaudeAssistant {
    constructor() {
        this.isOpen = false;
        this.messages = [];
        this.setupEventListeners();
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

        // Quick actions
        this.addQuickActions();
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

    addQuickActions() {
        // Add helpful quick action buttons
        const quickActions = [
            { text: 'Create a PostgreSQL environment', action: () => this.handleCreateEnv() },
            { text: 'Generate sample SQL query', action: () => this.generateSQL() },
            { text: 'Explain connection strings', action: () => this.explainConnections() }
        ];

        // These could be shown as buttons below the initial message
    }

    async sendMessage() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();

        if (!message) return;

        // Add user message
        this.addMessage(message, 'user');
        input.value = '';

        // Show typing indicator
        this.showTyping();

        // Process message and get response
        const response = await this.processMessage(message);

        // Remove typing indicator and add response
        this.hideTyping();
        this.addMessage(response, 'assistant');
    }

    addMessage(text, sender) {
        this.messages.push({ text, sender, timestamp: new Date() });

        const messagesContainer = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');

        if (sender === 'user') {
            messageDiv.className = 'bg-primary text-white rounded-lg p-3 ml-auto max-w-[80%]';
            messageDiv.innerHTML = `<p class="text-sm">${this.escapeHtml(text)}</p>`;
        } else {
            messageDiv.className = 'bg-gray-100 dark:bg-gray-700 rounded-lg p-3 max-w-[80%]';
            messageDiv.innerHTML = `
                <p class="text-sm">
                    <span class="font-semibold">Claude:</span> ${this.formatMessage(text)}
                </p>
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
                <span class="font-semibold">Claude:</span> <span class="animate-pulse">Thinking...</span>
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

    async processMessage(message) {
        // Simulate AI processing with intelligent responses
        // In a real implementation, this would call an AI API (Claude, OpenAI, etc.)

        const lowerMessage = message.toLowerCase();

        // Intent detection
        if (lowerMessage.includes('create') && (lowerMessage.includes('environment') || lowerMessage.includes('database') || lowerMessage.includes('postgres'))) {
            return this.handleCreateEnv();
        }

        if (lowerMessage.includes('sql') || lowerMessage.includes('query')) {
            return this.generateSQL(message);
        }

        if (lowerMessage.includes('connect') || lowerMessage.includes('connection string')) {
            return this.explainConnections();
        }

        if (lowerMessage.includes('cost') || lowerMessage.includes('price') || lowerMessage.includes('billing')) {
            return this.explainPricing();
        }

        if (lowerMessage.includes('help') || lowerMessage.includes('what can you do')) {
            return this.showHelp();
        }

        if (lowerMessage.includes('supabase')) {
            return this.explainSupabase();
        }

        if (lowerMessage.includes('pgvector') || lowerMessage.includes('vector') || lowerMessage.includes('embedding')) {
            return this.explainPgvector();
        }

        if (lowerMessage.includes('postgis') || lowerMessage.includes('geo') || lowerMessage.includes('location')) {
            return this.explainPostGIS();
        }

        // Default response
        return `I can help you with:\n
• Creating and managing PostgreSQL environments\n
• Generating SQL queries\n
• Explaining connection strings\n
• Understanding pricing\n
• Learning about pgvector, PostGIS, and Supabase\n\n
What would you like to know more about?`;
    }

    handleCreateEnv() {
        // Open the create environment modal
        setTimeout(() => {
            document.getElementById('create-env-btn').click();
        }, 500);

        return `I've opened the environment creation form for you! Here's what I recommend:\n\n
<strong>For basic testing:</strong>\n
• Select "PostgreSQL Standard" ($0.10/hr)\n
• Good for general SQL testing\n\n
<strong>For AI/embeddings:</strong>\n
• Select "PostgreSQL + pgvector" ($0.12/hr)\n
• Perfect for RAG applications and similarity search\n\n
<strong>For full-stack apps:</strong>\n
• Select "PostgreSQL + Supabase" ($0.15/hr)\n
• Includes REST API and authentication\n\n
Would you like me to explain any of these options in more detail?`;
    }

    generateSQL(context = '') {
        const examples = [
            {
                name: 'Create a users table',
                sql: `CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(100),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);`
            },
            {
                name: 'Vector similarity search (pgvector)',
                sql: `-- Find similar items using cosine distance
SELECT id, content,
       1 - (embedding <=> query_embedding) AS similarity
FROM documents
ORDER BY embedding <=> query_embedding
LIMIT 10;`
            },
            {
                name: 'PostGIS location query',
                sql: `-- Find locations within 5km
SELECT name,
       ST_Distance(location, ST_MakePoint(-122.4194, 37.7749)::geography) / 1000 AS distance_km
FROM places
WHERE ST_DWithin(
  location,
  ST_MakePoint(-122.4194, 37.7749)::geography,
  5000
)
ORDER BY distance_km;`
            }
        ];

        const example = examples[Math.floor(Math.random() * examples.length)];

        return `Here's a sample SQL query for <strong>${example.name}</strong>:\n\n
<code style="display: block; background: rgba(0,0,0,0.1); padding: 12px; border-radius: 6px; margin: 8px 0; font-family: monospace; white-space: pre;">${this.escapeHtml(example.sql)}</code>\n\n
Would you like me to explain any part of this query or generate something else?`;
    }

    explainConnections() {
        return `<strong>Connection Strings Explained:</strong>\n\n
When you create an environment, you'll get connection strings like:\n\n
<code>postgresql://user:password@host:5432/database</code>\n\n
<strong>Components:</strong>\n
• <strong>postgresql://</strong> - Protocol\n
• <strong>user:password</strong> - Credentials\n
• <strong>host:5432</strong> - Server address and port\n
• <strong>/database</strong> - Database name\n\n
<strong>Using in your code:</strong>\n
Python: <code>psycopg2.connect(connection_string)</code>\n
Node.js: <code>new Pool({ connectionString })</code>\n
Go: <code>sql.Open("postgres", connectionString)</code>\n\n
The passwords in the UI are masked for security, but you can copy the full string!`;
    }

    explainPricing() {
        return `<strong>MockFactory Pricing:</strong>\n\n
💰 <strong>Pay only when running</strong> - no upfront costs!\n\n
<strong>Service Rates (per hour):</strong>\n
• PostgreSQL Standard: $0.10/hr\n
• PostgreSQL + Supabase: $0.15/hr\n
• PostgreSQL + pgvector: $0.12/hr\n
• PostgreSQL + PostGIS: $0.12/hr\n
• Redis: $0.10/hr\n
• AWS S3/SQS/SNS: $0.03-0.05/hr each\n\n
<strong>Auto-shutdown protection:</strong> Environments automatically stop after 4 hours (configurable) to prevent runaway costs.\n\n
<strong>Example:</strong> A PostgreSQL + Redis environment running for 2 hours = $0.40 total.\n\n
Want to create an environment?`;
    }

    explainSupabase() {
        return `<strong>PostgreSQL + Supabase</strong> includes:\n\n
✅ <strong>Standard PostgreSQL</strong> - Full SQL database\n
✅ <strong>PostgREST</strong> - Auto-generated REST API for your tables\n
✅ <strong>Authentication</strong> - Mock auth system for testing\n
✅ <strong>Storage API</strong> - File upload/download testing\n\n
<strong>Perfect for:</strong>\n
• Full-stack app development\n
• Testing REST API integrations\n
• Rapid prototyping\n
• Learning Supabase before production\n\n
<strong>Cost:</strong> $0.15/hr (about $0.60 for 4 hours)\n\n
Ready to create a Supabase environment?`;
    }

    explainPgvector() {
        return `<strong>PostgreSQL + pgvector</strong> is for AI applications:\n\n
🤖 <strong>Vector Embeddings:</strong> Store AI-generated embeddings\n
🔍 <strong>Similarity Search:</strong> Find similar items using cosine/euclidean distance\n
⚡ <strong>HNSW Indexing:</strong> Fast approximate nearest neighbor search\n\n
<strong>Perfect for:</strong>\n
• RAG (Retrieval Augmented Generation) apps\n
• Semantic search\n
• Recommendation systems\n
• Document similarity\n\n
<strong>Example Use Case:</strong>\n
Store OpenAI embeddings and search for similar documents:\n
<code>SELECT * FROM docs ORDER BY embedding <=> query_vector LIMIT 5;</code>\n\n
Want to create a pgvector environment?`;
    }

    explainPostGIS() {
        return `<strong>PostgreSQL + PostGIS</strong> adds geospatial superpowers:\n\n
🗺️ <strong>Geographic Data:</strong> Store points, lines, polygons\n
📍 <strong>Location Queries:</strong> Find nearby places, calculate distances\n
🎯 <strong>Spatial Indexing:</strong> Fast geographic searches\n\n
<strong>Perfect for:</strong>\n
• Mapping applications\n
• Location-based services\n
• Geofencing and proximity alerts\n
• Delivery/logistics systems\n\n
<strong>Example Query:</strong>\n
<code>-- Find restaurants within 2km
SELECT * FROM restaurants
WHERE ST_DWithin(location::geography,
  ST_MakePoint(lon, lat)::geography, 2000);</code>\n\n
Want to create a PostGIS environment?`;
    }

    showHelp() {
        return `<strong>I'm your MockFactory AI assistant!</strong> 🤖\n\n
I can help you:\n\n
💻 <strong>Create Environments</strong>\n
  "Create a PostgreSQL environment"\n
  "Set up a database with pgvector"\n\n
📝 <strong>Generate SQL</strong>\n
  "Generate a sample query"\n
  "Show me a vector search example"\n\n
🔌 <strong>Explain Concepts</strong>\n
  "How do connection strings work?"\n
  "What is Supabase?"\n
  "Tell me about pgvector"\n\n
💰 <strong>Pricing & Billing</strong>\n
  "How much does it cost?"\n
  "Explain the pricing"\n\n
Just ask me anything in natural language!`;
    }

    formatMessage(text) {
        // Convert markdown-like formatting to HTML
        return text
            .replace(/\n/g, '<br>')
            .replace(/<code>/g, '<code style="background: rgba(0,0,0,0.1); padding: 2px 6px; border-radius: 3px; font-family: monospace;">')
            .replace(/<strong>/g, '<strong style="font-weight: 600;">');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize Claude Assistant
const claude = new ClaudeAssistant();
