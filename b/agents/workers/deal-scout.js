#!/usr/bin/env node
/**
 * 🔍 DEAL SCOUT AGENT
 * Scans Reddit for hot deals and WTB opportunities
 * Model: GLM 4.7 Flash (ultra-cheap)
 */

const https = require('https');
const { Agent, MODELS } = require('../core/engine');

const scout = new Agent({
  name: 'deal-scout',
  role: 'Scans marketplaces for deals and buying opportunities',
  model: MODELS.flash,
  maxTokens: 800,
  systemPrompt: `You are a deal scout for The Hub, a watch and sneaker deal aggregator.
Your job: Analyze marketplace listings and identify HOT DEALS.
A hot deal = listed significantly below market value (15%+ discount).
Be concise. Output JSON format: { "deals": [{ "title", "price", "marketValue", "discount", "source", "url", "score" }] }
Score: 1-20 (20 = incredible deal). Only include deals scoring 10+.`
});

async function fetchRedditJSON(subreddit, sort = 'new', limit = 25) {
  return new Promise((resolve, reject) => {
    const url = `https://www.reddit.com/r/${subreddit}/${sort}.json?limit=${limit}`;
    https.get(url, { headers: { 'User-Agent': 'TheHub/1.0' } }, (res) => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

async function scanSubreddit(subreddit) {
  scout.log(`Scanning r/${subreddit}...`);
  
  try {
    const data = await fetchRedditJSON(subreddit);
    const posts = data?.data?.children || [];
    
    // Filter for sale posts
    const salePosts = posts
      .map(p => p.data)
      .filter(p => {
        const title = (p.title || '').toLowerCase();
        return title.includes('[wts]') || title.includes('for sale') || title.includes('selling');
      })
      .slice(0, 10);

    if (salePosts.length === 0) {
      scout.log(`No sale posts found on r/${subreddit}`);
      return [];
    }

    // Analyze with AI
    const listingsText = salePosts.map((p, i) => 
      `${i+1}. "${p.title}" | Score: ${p.score} | URL: https://reddit.com${p.permalink}`
    ).join('\n');

    const result = await scout.think(
      `Analyze these r/${subreddit} listings. Identify any hot deals (significantly below market value):\n\n${listingsText}\n\nReturn JSON with deals found. If none are clearly hot deals, return {"deals": []}.`
    );

    scout.log(`Analysis complete for r/${subreddit}: ${result.content.slice(0, 200)}`);
    return result.content;
  } catch (err) {
    scout.log(`Error scanning r/${subreddit}: ${err.message}`);
    return [];
  }
}

async function scanWTBThread(subreddit) {
  scout.log(`Scanning WTB threads on r/${subreddit}...`);
  
  try {
    const data = await fetchRedditJSON(subreddit, 'new', 50);
    const posts = data?.data?.children || [];
    
    const wtbPosts = posts
      .map(p => p.data)
      .filter(p => {
        const title = (p.title || '').toLowerCase();
        return title.includes('[wtb]') || title.includes('want to buy') || title.includes('looking for');
      })
      .slice(0, 10);

    if (wtbPosts.length === 0) {
      scout.log(`No WTB posts found on r/${subreddit}`);
      return [];
    }

    const result = await scout.think(
      `These are Want-To-Buy posts from r/${subreddit}. Extract what each person is looking for:\n\n${wtbPosts.map((p, i) => `${i+1}. "${p.title}" by u/${p.author} | URL: https://reddit.com${p.permalink}`).join('\n')}\n\nReturn JSON: { "prospects": [{ "username", "looking_for", "url" }] }`
    );

    return result.content;
  } catch (err) {
    scout.log(`Error scanning WTB on r/${subreddit}: ${err.message}`);
    return [];
  }
}

async function run() {
  console.log('🔍 Deal Scout Agent - Deploying...\n');
  
  const subreddits = ['Watchexchange', 'SneakerMarket', 'Watches'];
  const allResults = {};

  for (const sub of subreddits) {
    console.log(`📡 Scanning r/${sub}...`);
    allResults[sub] = {
      deals: await scanSubreddit(sub),
      wtb: await scanWTBThread(sub),
    };
    // Rate limit
    await new Promise(r => setTimeout(r, 2000));
  }

  // Save full report
  scout.saveData(`scan-${new Date().toISOString().split('T')[0]}.json`, allResults);
  scout.report('Daily Deal Scan', allResults);
  
  console.log('\n✅ Deal Scout scan complete!');
  console.log(`📊 Stats: ${scout.totalCalls} API calls`);
  console.log(`📁 Report saved to agents/data/`);
}

// Run if called directly
if (require.main === module) {
  run().catch(console.error);
}

module.exports = { scout, scanSubreddit, scanWTBThread, run };
