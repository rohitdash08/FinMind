#!/usr/bin/env node
/**
 * 📝 CONTENT WRITER AGENT
 * Generates social posts, blog drafts, newsletter content
 * Model: GLM 4.7 Flash
 */

const { Agent, MODELS } = require('../core/engine');

const writer = new Agent({
  name: 'content-writer',
  role: 'Creates engaging content for The Hub across platforms',
  model: MODELS.flash,
  maxTokens: 1000,
  systemPrompt: `You are a content writer for The Hub - a watch and sneaker deal aggregator platform.
Your style: Sharp, engaging, no fluff. Think modern tech startup meets streetwear culture.
Audience: Watch collectors, sneakerheads, resellers (ages 18-35).
Tone: Confident but not arrogant. Data-driven. A bit edgy.
NEVER use cringe phrases like "game-changer", "unlock", "elevate your journey".
Keep it real.`
});

async function generateTelegramPost(topic, context = '') {
  const result = await writer.think(
    `Write a Telegram channel post about: ${topic}\n\nContext: ${context}\n\nRequirements:\n- Under 280 characters\n- Include 1-2 relevant emojis\n- End with engagement hook (question or CTA)\n- No hashtags (not Instagram)\n- Sound human, not corporate`
  );
  return result.content;
}

async function generateBlogDraft(topic, keyPoints = []) {
  const result = await writer.think(
    `Write a blog post draft about: ${topic}\n\nKey points to cover:\n${keyPoints.map(p => `- ${p}`).join('\n')}\n\nFormat:\n- Title (catchy, SEO-friendly)\n- Introduction (2-3 sentences, hook the reader)\n- 3-4 sections with headers\n- Conclusion with CTA\n- Target: 500-800 words\n- Include specific numbers/data where possible`
  );
  return result.content;
}

async function generateSocialBatch(deals = []) {
  const dealsText = deals.length > 0 
    ? deals.map(d => `${d.title} - $${d.price}`).join('\n')
    : 'General watch and sneaker market content';

  const result = await writer.think(
    `Generate a batch of 5 social media posts for The Hub:\n\nDeals to feature:\n${dealsText}\n\nGenerate:\n1. Twitter/X post (under 280 chars)\n2. Telegram channel post\n3. Instagram caption (with hashtags)\n4. Reddit comment (helpful, not salesy)\n5. Discord announcement\n\nEach should be unique in tone/angle. Label each clearly.`
  );
  return result.content;
}

async function generateNewsletterSection(topic, data = '') {
  const result = await writer.think(
    `Write a newsletter section about: ${topic}\n\nData: ${data}\n\nFormat: HTML-compatible (use <h2>, <p>, <strong>, <a> tags)\nLength: 150-250 words\nStyle: Informative, valuable, not salesy\nInclude a CTA button at the end`
  );
  return result.content;
}

async function run() {
  console.log('📝 Content Writer Agent - Deploying...\n');

  // Generate today's content batch
  console.log('Generating Telegram post...');
  const telegramPost = await generateTelegramPost(
    'Watch market trends and deal alerts',
    'We track 1,400+ listings across Reddit, eBay, Chrono24'
  );
  console.log(`\n📱 Telegram:\n${telegramPost}\n`);

  console.log('Generating social batch...');
  const socialBatch = await generateSocialBatch([
    { title: 'Grand Seiko Snowflake SBGA211', price: 4822 },
    { title: 'Rolex Submariner 116610LN', price: 9200 },
  ]);
  console.log(`\n🌐 Social Batch:\n${socialBatch}\n`);

  // Save all content
  writer.saveData(`content-${new Date().toISOString().split('T')[0]}.json`, {
    telegramPost,
    socialBatch,
    generatedAt: new Date().toISOString(),
  });

  writer.report('Daily Content Generation', { telegramPost, socialBatch });
  
  console.log('\n✅ Content Writer complete!');
  console.log(`📊 Stats: ${writer.totalCalls} API calls`);
}

if (require.main === module) {
  run().catch(console.error);
}

module.exports = { writer, generateTelegramPost, generateBlogDraft, generateSocialBatch, generateNewsletterSection, run };
