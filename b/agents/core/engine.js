/**
 * Agent Army Engine - Core runtime for all AI agents
 * CEO: Jay | HQ: OpenRouter
 * Uses GLM 4.7 Flash for cheap, fast agent operations
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

const OPENROUTER_KEY = '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';

const MODELS = {
  flash: 'z-ai/glm-4.7-flash',       // Ultra-cheap scout work ($0.00006/1M in)
  standard: 'z-ai/glm-4.7',           // Standard tasks
  research: 'perplexity/sonar-pro',    // Deep research with citations
  free: 'z-ai/glm-4.5-air:free',      // Completely free tier
};

class Agent {
  constructor(config) {
    this.name = config.name;
    this.role = config.role;
    this.model = config.model || MODELS.flash;
    this.systemPrompt = config.systemPrompt || '';
    this.maxTokens = config.maxTokens || 1000;
    this.logDir = path.join(__dirname, '..', 'logs');
    this.dataDir = path.join(__dirname, '..', 'data');
    this.totalCost = 0;
    this.totalCalls = 0;

    // Ensure dirs exist
    if (!fs.existsSync(this.logDir)) fs.mkdirSync(this.logDir, { recursive: true });
    if (!fs.existsSync(this.dataDir)) fs.mkdirSync(this.dataDir, { recursive: true });
  }

  /**
   * Send a prompt to the agent's model
   */
  async think(prompt, options = {}) {
    const model = options.model || this.model;
    const maxTokens = options.maxTokens || this.maxTokens;

    const messages = [];
    if (this.systemPrompt) {
      messages.push({ role: 'system', content: this.systemPrompt });
    }
    messages.push({ role: 'user', content: prompt });

    const data = JSON.stringify({
      model,
      messages,
      max_tokens: maxTokens,
    });

    return new Promise((resolve, reject) => {
      const opts = {
        hostname: 'openrouter.ai',
        path: '/api/v1/chat/completions',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${OPENROUTER_KEY}`,
          'X-Title': `Agent Army - ${this.name}`,
        },
      };

      const req = https.request(opts, (res) => {
        let body = '';
        res.on('data', (d) => body += d);
        res.on('end', () => {
          try {
            const json = JSON.parse(body);
            if (json.error) {
              reject(new Error(json.error.message || JSON.stringify(json.error)));
              return;
            }
            const content = json.choices?.[0]?.message?.content || '';
            const usage = json.usage || {};

            this.totalCalls++;
            this.log(`[${this.name}] Think complete | model=${model} | tokens=${usage.total_tokens || 0}`);

            resolve({
              content,
              usage,
              model: json.model,
            });
          } catch (e) {
            reject(new Error(`Parse error: ${body.slice(0, 200)}`));
          }
        });
      });

      req.on('error', reject);
      req.setTimeout(30000, () => {
        req.destroy();
        reject(new Error('Request timeout'));
      });
      req.write(data);
      req.end();
    });
  }

  /**
   * Log agent activity
   */
  log(message) {
    const timestamp = new Date().toISOString();
    const logLine = `${timestamp} ${message}\n`;
    const logFile = path.join(this.logDir, `${this.name}.log`);

    fs.appendFileSync(logFile, logLine);

    if (process.env.AGENT_VERBOSE) {
      console.log(`[${this.name}] ${message}`);
    }
  }

  /**
   * Save data to agent's data store
   */
  saveData(filename, data) {
    const filePath = path.join(this.dataDir, filename);
    fs.writeFileSync(filePath, typeof data === 'string' ? data : JSON.stringify(data, null, 2));
    this.log(`Saved data to ${filename}`);
  }

  /**
   * Load data from agent's data store
   */
  loadData(filename) {
    const filePath = path.join(this.dataDir, filename);
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, 'utf8');
    try { return JSON.parse(raw); } catch { return raw; }
  }

  /**
   * Report results (save + log)
   */
  report(title, findings) {
    const report = {
      agent: this.name,
      role: this.role,
      timestamp: new Date().toISOString(),
      title,
      findings,
      stats: { totalCalls: this.totalCalls, totalCost: this.totalCost },
    };
    this.saveData(`report-${Date.now()}.json`, report);
    this.log(`Report: ${title} | ${typeof findings === 'string' ? findings.slice(0, 100) : JSON.stringify(findings).slice(0, 100)}`);
    return report;
  }
}

module.exports = { Agent, MODELS };
