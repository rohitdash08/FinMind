# Jay's Showcase Site 🚀

> **"The AI that runs the business while you sleep"**

A personal showcase site for Jay (AI Co-CEO) and The Hub, inspired by Alex Finn's "Henry" setup.

## 🎯 What This Is

This is a single-page showcase demonstrating Jay's capabilities as an autonomous AI co-founder. It features:

- **Terminal-style hero** with animated "thinking" display
- **Live stats** from The Hub API
- **Agent army roster** showing deployed AI workers
- **Tech stack breakdown** of what powers Jay
- **Dark theme** (#0f172a bg, #9333ea purple accent)
- **Mobile responsive** design
- **No frameworks** - pure HTML/CSS/JS

## 🚀 Quick Start

```bash
# Install dependencies
npm install

# Start the server (port 4006)
npm start

# Development with auto-reload
npm run dev
```

Visit: **http://localhost:4006**

## 📁 Structure

```
jay-site/
├── index.html      # Main showcase page
├── styles.css      # Dark theme styling
├── script.js       # Animations, API calls, interactivity
├── server.js       # Express server with API proxies
├── package.json    # Dependencies
└── README.md       # This file
```

## 🎨 Features

### Hero Section
- Animated terminal showing Jay "initializing"
- Typing effect with realistic command sequences
- Glowing badges (Always On, AI-Native, Autonomous)
- Click terminal to restart animation (easter egg)

### What Jay Does
- 6 capability cards with hover effects
- Icons for each capability
- Tags showing activity status
- Smooth animations on scroll

### Live Stats
- Fetches real data from The Hub API (localhost:4003)
- Animated counter on page load
- Falls back to defaults if Hub isn't running
- Auto-refreshes every 30 seconds

### Agent Army
- Dynamic roster loaded from API
- Shows agent name, role, model, schedule
- Live status indicators (pulsing green dots)
- Task counters

### Tech Stack
- Visual breakdown of Jay's architecture
- Hover effects on each stack card
- Clean, modern card design

### Footer
- Links to The Hub dashboard
- Telegram link
- Built by Syd & Jay credit
- Inspirational quote

## 🔌 API Endpoints

### GET /api/stats
Returns live performance metrics:
```json
{
  "dealsTracked": 1410,
  "agentsDeployed": 6,
  "modelsAvailable": 344,
  "costPerTask": 0.0008,
  "uptime": "24/7/365",
  "activeScrapers": 3,
  "lastDealTime": "2025-02-10T..."
}
```

### GET /api/agents
Returns agent roster:
```json
[
  {
    "name": "Scout Leader",
    "role": "Deal Discovery",
    "model": "GLM 4.7 Flash",
    "status": "active",
    "schedule": "24/7",
    "tasksToday": 247
  },
  ...
]
```

## 🎯 Design Principles

1. **Dark & Sleek** - Terminal/hacker vibes meet clean startup aesthetic
2. **Animated** - Smooth transitions, hover effects, scroll animations
3. **Live Data** - Real metrics from The Hub, not static numbers
4. **Mobile First** - Fully responsive, works on all devices
5. **Performance** - No frameworks, minimal JS, fast load times

## 🛠️ Customization

### Colors
Edit CSS variables in `styles.css`:
```css
:root {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --accent: #9333ea;
  --accent-light: #a855f7;
  /* ... */
}
```

### Terminal Commands
Edit the commands array in `script.js`:
```javascript
const commands = [
  'initializing jay.ai...',
  'loading neural networks...',
  // Add your own commands
];
```

### Agent Roster
Add/edit agents in `server.js` `/api/agents` endpoint.

### Stats
Modify stat cards in `index.html` and update API in `server.js`.

## 🔗 Integration with The Hub

The site connects to The Hub's dashboard API at `http://localhost:4003/api/dashboard/status` to fetch live stats. Make sure The Hub is running for live data.

If The Hub isn't running, the site falls back to default values.

## 📱 Sharing

This is a localhost showcase by default. To share publicly:

1. **Use ngrok or similar:**
   ```bash
   ngrok http 4006
   ```

2. **Deploy to Vercel/Netlify:**
   - The server.js can run as a serverless function
   - Or build a static version with hardcoded data

3. **Record a demo video:**
   - Screen record the site in action
   - Share on Twitter, LinkedIn, etc.

## 💡 Ideas for Enhancement

- [ ] Add WebSocket for real-time updates
- [ ] Chart.js graphs for deal trends
- [ ] Live activity feed from Telegram
- [ ] Voice narration using ElevenLabs
- [ ] Dark/light theme toggle
- [ ] More detailed agent logs/history
- [ ] Integration with mission control Kanban

## 🎬 Inspiration

Inspired by [Alex Finn's "Henry" showcase](https://alexfinn.com) - showing off what a truly autonomous AI assistant can do.

## 📄 License

Built by Syd & Jay for The Hub. Use as you like!

---

**Powered by ClawdBot** | **Built with ❤️ by human-AI collaboration**
