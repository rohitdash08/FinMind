#!/usr/bin/env node
/**
 * 🎯 PROSPECT FINDER AGENT
 * Finds potential beta testers and users on Reddit
 * Model: GLM 4.7 Flash
 */

const https = require('https');
const { Agent, MODELS } = require('../core/engine');

const finder = new Agent({
  name: 'prospect-finder',
  role: 'Finds and qualifies potential users for The Hub',
  model: MODELS.flash,
  maxTokens: 1000,
  systemPrompt: `You are a prospect researcher for The Hub, a deal aggregator for watches and sneakers.
Your job: Find people who would benefit from real-time deal alerts across marketplaces.
Ideal prospect: Active buyer on Reddit (r/Watchexchange, r/SneakerMarket) with transaction history.
Output: JSON with { "prospects": [{ "username", "looking_for", "transactions", "priority", "message_draft" }] }
Priority: high (10+ transactions), medium (3-9), low (0-2).
Message draft: Under 75 words, references their specific need, offers free beta access.`
});

async function fetchRedditJSON(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'TheHub/1.0' } }, (res) => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

async function findProspects() {
  finder.log('Starting prospect search...');
  
  const subreddits = ['Watchexchange', 'SneakerMarket'];
  const allProspects = [];

  for (const sub of subreddits) {
    finder.log(`Searching r/${sub}...`);
    
    try {
      // Search for WTB posts
      const searchUrl = `https://www.reddit.com/r/${sub}/search.json?q=WTB+OR+%22want+to+buy%22&sort=new&restrict_sr=on&limit=25`;
      const data = await fetchRedditJSON(searchUrl);
      const posts = data?.data?.children || [];

      if (posts.length === 0) {
        finder.log(`No WTB posts found on r/${sub}`);
        continue;
      }

      const postsText = posts.slice(0, 15).map((p, i) => {
        const d = p.data;
        return `${i+1}. u/${d.author}: "${d.title}" (score: ${d.score}, ${d.num_comments} comments) | URL: https://reddit.com${d.permalink}`;
      }).join('\n');

      const result = await finder.think(
        `Analyze these WTB posts from r/${sub} and identify the best prospects for The Hub beta:\n\n${postsText}\n\nFor each good prospect, create a personalized outreach message. Focus on people with specific product needs.`
      );

      allProspects.push({
        subreddit: sub,
        analysis: result.content,
        postsScanned: posts.length,
      });

      // Rate limit between subreddits
      await new Promise(r => setTimeout(r, 2000));
    } catch (err) {
      finder.log(`Error on r/${sub}: ${err.message}`);
    }
  }

  return allProspects;
}

async function run() {
  console.log('🎯 Prospect Finder Agent - Deploying...\n');

  const prospects = await findProspects();

  finder.saveData(`prospects-${new Date().toISOString().split('T')[0]}.json`, prospects);
  finder.report('Daily Prospect Scan', prospects);

  console.log('\n✅ Prospect Finder complete!');
  console.log(`📊 Found prospects across ${prospects.length} subreddits`);
  console.log(`📊 Stats: ${finder.totalCalls} API calls`);
  
  // Print summary
  prospects.forEach(p => {
    console.log(`\nr/${p.subreddit}: Scanned ${p.postsScanned} posts`);
    console.log(p.analysis);
  });
}

if (require.main === module) {
  run().catch(console.error);
}

module.exports = { finder, findProspects, run };
