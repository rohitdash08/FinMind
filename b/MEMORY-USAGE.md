# Memory System Usage Guide

## Overview
OpenClaw memory is **plain Markdown in the agent workspace**. Files are the source of truth—the model only "remembers" what gets written to disk.

## Memory Files

### `memory/YYYY-MM-DD.md` - Daily Log
- **Purpose:** Append-only daily journal
- **Read:** Today + yesterday at session start
- **Content:** Events, decisions, work done, lessons learned
- **Format:** Timestamped sections with headers

```markdown
## 🚀 14:00 - Feature Built
Built pricing plans component for The Hub...

## 🐛 15:30 - Bug Fixed  
Fixed Empire CLI spawn issue...
```

### `MEMORY.md` - Long-Term Knowledge
- **Purpose:** Curated permanent memory
- **Security:** ONLY load in main/private session (never group chats)
- **Content:** Key relationships, project facts, lessons, preferences
- **Maintenance:** Review and update every few days

## When to Write Memory

| What | Where | Why |
|------|-------|-----|
| Decisions, preferences, facts | `MEMORY.md` | Permanent knowledge |
| Daily work, bugs, features | `memory/YYYY-MM-DD.md` | Chronological log |
| "Remember this" requests | Either file | Don't trust RAM |
| Before compaction | Daily file | Flush context |

## Memory Tools

### `memory_search` - Semantic Search
```
memory_search("PWA implementation details")
```
- Searches `MEMORY.md` + all `memory/*.md` files
- Uses vector embeddings (semantic match)
- Returns snippets with file path + line numbers
- Hybrid search: BM25 keywords + vector similarity

**When to use:**
- "What did we decide about X?"
- "When did we last work on Y?"
- "Do we have notes about Z?"

### `memory_get` - Read Memory File
```
memory_get("memory/2026-02-08.md", from: 50, lines: 20)
```
- Reads specific memory file
- Optional: starting line + line count
- Only works with memory files (security)

**When to use:**
- After memory_search finds something
- Reading today's log
- Checking yesterday's work

## Memory Maintenance Workflow

### Daily (During Work)
1. Append significant events to today's daily file
2. Include context: what, why, outcome
3. Keep chronological order

### Weekly (During Heartbeat)
1. Read last 3-7 days of daily files
2. Extract important learnings
3. Update `MEMORY.md` with distilled knowledge
4. Remove outdated info from `MEMORY.md`

### Before Compaction
When session nears token limit, system automatically:
1. Triggers silent agentic turn
2. Reminds to write durable memory
3. Expects `NO_REPLY` if nothing to store
4. Then compacts context

## Best Practices

✅ **DO:**
- Write decisions immediately
- Use timestamps in daily files
- Keep MEMORY.md organized with sections
- Update facts when they change
- Use memory_search before asking user

❌ **DON'T:**
- Keep important info only in chat (it will be compacted)
- Write secrets in memory (filesystem = trust boundary)
- Load MEMORY.md in group chats (security)
- Edit past daily file entries (append-only)
- Reply to memory flush prompts (use NO_REPLY)

## Example Workflow

**User says:** "Remember to use port 4003 for Empire"

```markdown
# In memory/2026-02-08.md
## 💡 15:45 - Configuration Note
Empire command center runs on port 4003, not 4001.
Main agent empire uses different port than Mission Control.
```

**Later, user asks:** "What port is Empire on?"

```
1. memory_search("Empire port configuration")
2. Find snippet from daily file
3. Answer: "Port 4003"
```

## Memory Search Configuration

**Current Setup:**
- Provider: OpenAI (or auto-detect)
- Hybrid search: Enabled (BM25 + vector)
- Files indexed: `MEMORY.md` + `memory/**/*.md`
- Auto-updates: Watches for file changes
- Cache: Enabled for faster re-indexing

**Fallback:**
If embeddings fail, still works (keyword search only).

## Security Notes

- **Memory files are plain text** on filesystem
- Anyone with file access can read them
- Don't store API keys or passwords
- MEMORY.md only loads in main session (not groups)
- Session transcripts are separate (experimental)

---

**TL;DR:** Daily files are your journal, MEMORY.md is your operating manual. Write everything down. Use memory_search to recall. Don't trust your context window.
