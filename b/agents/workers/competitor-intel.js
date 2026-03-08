#!/usr/bin/env node
/**
 * 🕵️ COMPETITOR INTEL AGENT
 * Monitors competitor platforms for changes, features, pricing
 * Model: GLM 4.7 Flash
 */

const https = require('https');
const { Agent, MODELS } = require('../core/engine');

const intel = new Agent({
  name: 'competitor-intel',
  role: 'Monitors competitor platforms and market landscape',
  model: MODELS.flash,
  maxTokens: 1000,
  systemPrompt: `You are a competitive intelligence analyst for The Hub (watch & sneaker deal aggregator).
Key competitors: WatchCharts, Chrono24, StockX, GOAT, WatchPatrol.
Your job: Analyze competitor data and identify opportunities, threats, and feature gaps.
Be specific and actionable. No fluff.
Output format: { "competitor", "findings", "opportunities", "threats", "recommendations" }`
});

const COMPETITORS = [
  { name: 'WatchCharts', url: 'https://watchcharts.com', focus: 'Watch price tracking' },
  { name: 'Chrono24', url: 'https://www.chrono24.com', focus: 'Watch marketplace' },
  { name: 'StockX', url: 'https://stockx.com', focus: 'Sneaker/watch marketplace' },
  { name: 'WatchPatrol', url: 'https://watchpatrol.net', focus: 'Watch deal aggregation' },
];

function fetchPage(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : require('http');
    client.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, (res) => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

async function analyzeCompetitor(competitor) {
  intel.log(`Analyzing ${competitor.name}...`);
  
  try {
    const html = await fetchPage(competitor.url);
    // Extract text content (rough)
    const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 2000);
    
    const result = await intel.think(
      `Analyze this competitor page for ${competitor.name} (${competitor.focus}):\n\nURL: ${competitor.url}\nPage content (excerpt): ${text.slice(0, 1500)}\n\nWhat features do they offer? What's their value prop? What can The Hub do better?`
    );

    return {
      competitor: competitor.name,
      url: competitor.url,
      analysis: result.content,
      scannedAt: new Date().toISOString(),
    };
  } catch (err) {
    intel.log(`Error analyzing ${competitor.name}: ${err.message}`);
    return { competitor: competitor.name, error: err.message };
  }
}

async function run() {
  console.log('🕵️ Competitor Intel Agent - Deploying...\n');

  const results = [];
  for (const comp of COMPETITORS) {
    console.log(`Analyzing ${comp.name}...`);
    const analysis = await analyzeCompetitor(comp);
    results.push(analysis);
    console.log(`✅ ${comp.name} analyzed`);
    await new Promise(r => setTimeout(r, 2000));
  }

  // Generate strategic summary
  console.log('\nGenerating strategic summary...');
  const summary = await intel.think(
    `Based on these competitor analyses, write a strategic intelligence brief for The Hub:\n\n${results.map(r => `${r.competitor}: ${r.analysis || r.error}`).join('\n\n')}\n\nInclude: Top 3 opportunities, Top 3 threats, Recommended next moves.`
  );

  intel.saveData(`intel-${new Date().toISOString().split('T')[0]}.json`, { results, summary: summary.content });
  intel.report('Competitor Intel Brief', { results, summary: summary.content });

  console.log(`\n📋 Strategic Brief:\n${summary.content}`);
  console.log(`\n✅ Competitor Intel complete! ${intel.totalCalls} API calls`);
}

if (require.main === module) {
  run().catch(console.error);
}

module.exports = { intel, analyzeCompetitor, run };
