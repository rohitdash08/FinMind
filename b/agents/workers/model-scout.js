#!/usr/bin/env node
/**
 * 🔭 MODEL SCOUT AGENT
 * Monitors OpenRouter for new, cheap, powerful models
 * Keeps the army equipped with the best weapons
 */

const https = require('https');
const fs = require('fs');
const path = require('path');
const { Agent } = require('../core/engine');

const scout = new Agent({
  name: 'model-scout',
  role: 'Finds new AI models on OpenRouter for the Agent Army',
  model: 'z-ai/glm-4.7-flash',
  maxTokens: 500,
});

const KNOWN_MODELS_FILE = path.join(__dirname, '..', 'data', 'known-models.json');

function fetchModels() {
  return new Promise((resolve, reject) => {
    https.get('https://openrouter.ai/api/v1/models', (res) => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => {
        try { resolve(JSON.parse(data).data || []); } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

async function run() {
  console.log('🔭 Model Scout - Scanning OpenRouter...\n');

  const models = await fetchModels();
  
  // Load previously known models
  let knownModels = [];
  if (fs.existsSync(KNOWN_MODELS_FILE)) {
    knownModels = JSON.parse(fs.readFileSync(KNOWN_MODELS_FILE, 'utf8'));
  }
  const knownIds = new Set(knownModels.map(m => m.id));

  // Find new models
  const newModels = models.filter(m => !knownIds.has(m.id));

  // Find cheapest models (input cost per token)
  const cheapest = models
    .filter(m => m.pricing && parseFloat(m.pricing.prompt) > 0)
    .sort((a, b) => parseFloat(a.pricing.prompt) - parseFloat(b.pricing.prompt))
    .slice(0, 20);

  // Find free models
  const freeModels = models.filter(m => m.pricing && parseFloat(m.pricing.prompt) === 0);

  // Find high-context models (100k+)
  const bigContext = models
    .filter(m => m.context_length >= 100000)
    .sort((a, b) => b.context_length - a.context_length)
    .slice(0, 15);

  // Report
  console.log(`📊 Total models on OpenRouter: ${models.length}`);
  console.log(`🆕 New models since last scan: ${newModels.length}`);
  console.log(`🆓 Free models available: ${freeModels.length}`);
  console.log(`📏 100k+ context models: ${bigContext.length}`);

  if (newModels.length > 0) {
    console.log('\n🆕 NEW MODELS FOUND:');
    newModels.slice(0, 10).forEach(m => {
      const cost = m.pricing ? `$${m.pricing.prompt}/in $${m.pricing.completion}/out` : 'N/A';
      console.log(`  • ${m.id} (ctx: ${m.context_length}) - ${cost}`);
    });
  }

  console.log('\n💰 TOP 10 CHEAPEST (non-free):');
  cheapest.slice(0, 10).forEach(m => {
    console.log(`  • ${m.id} - $${m.pricing.prompt}/tok in | ctx: ${m.context_length}`);
  });

  console.log('\n🆓 FREE MODELS:');
  freeModels.forEach(m => {
    console.log(`  • ${m.id} (ctx: ${m.context_length})`);
  });

  // Save current model list for next comparison
  const modelSummary = models.map(m => ({
    id: m.id,
    name: m.name,
    context_length: m.context_length,
    pricing: m.pricing,
  }));
  fs.writeFileSync(KNOWN_MODELS_FILE, JSON.stringify(modelSummary, null, 2));

  // Save report
  const report = {
    scannedAt: new Date().toISOString(),
    totalModels: models.length,
    newModels: newModels.length,
    freeModels: freeModels.map(m => m.id),
    cheapest: cheapest.slice(0, 10).map(m => ({ id: m.id, cost: m.pricing?.prompt, ctx: m.context_length })),
    bigContext: bigContext.slice(0, 10).map(m => ({ id: m.id, ctx: m.context_length, cost: m.pricing?.prompt })),
    newModelDetails: newModels.slice(0, 20).map(m => ({ id: m.id, name: m.name, ctx: m.context_length, pricing: m.pricing })),
  };
  scout.saveData(`model-scan-${new Date().toISOString().split('T')[0]}.json`, report);

  console.log(`\n✅ Model Scout complete! Catalog saved.`);
  return report;
}

if (require.main === module) {
  run().catch(console.error);
}

module.exports = { run };
