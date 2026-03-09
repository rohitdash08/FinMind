#!/usr/bin/env node
/**
 * 🪖 AGENT ARMY DEPLOYMENT SCRIPT
 * CEO: Jay | HQ: OpenRouter
 * Deploys all agents for a full sweep
 */

const path = require('path');

const AGENTS = {
  'deal-scout': { file: './workers/deal-scout.js', emoji: '🔍', desc: 'Scanning Reddit for deals' },
  'content-writer': { file: './workers/content-writer.js', emoji: '📝', desc: 'Generating content' },
  'prospect-finder': { file: './workers/prospect-finder.js', emoji: '🎯', desc: 'Finding beta prospects' },
  'competitor-intel': { file: './workers/competitor-intel.js', emoji: '🕵️', desc: 'Analyzing competitors' },
  'inbox-monitor': { file: './workers/inbox-monitor.js', emoji: '📬', desc: 'Monitoring inbox' },
};

async function deployAgent(name) {
  const agent = AGENTS[name];
  if (!agent) {
    console.error(`Unknown agent: ${name}`);
    return;
  }

  console.log(`${agent.emoji} Deploying ${name}: ${agent.desc}`);
  try {
    const { run } = require(agent.file);
    await run();
    console.log(`✅ ${name} complete\n`);
  } catch (err) {
    console.error(`❌ ${name} failed: ${err.message}\n`);
  }
}

async function deployAll() {
  console.log('╔══════════════════════════════════════╗');
  console.log('║   🪖 AGENT ARMY - FULL DEPLOYMENT   ║');
  console.log('║   CEO: Jay | HQ: OpenRouter          ║');
  console.log('║   Model: GLM 4.7 Flash               ║');
  console.log('╚══════════════════════════════════════╝\n');

  const startTime = Date.now();
  const target = process.argv[2];

  if (target && AGENTS[target]) {
    await deployAgent(target);
  } else if (target === 'all' || !target) {
    for (const name of Object.keys(AGENTS)) {
      await deployAgent(name);
    }
  } else {
    console.log('Usage: node deploy.js [agent-name|all]');
    console.log('\nAvailable agents:');
    Object.entries(AGENTS).forEach(([name, a]) => {
      console.log(`  ${a.emoji} ${name} - ${a.desc}`);
    });
    return;
  }

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log('═══════════════════════════════════════');
  console.log(`🏁 Deployment complete in ${elapsed}s`);
  console.log('═══════════════════════════════════════');
}

deployAll().catch(console.error);
