// Demo script to show how to use login anomaly detection logic (pure JS).
// This does not integrate with the TS utilities, but provides a quick sanity check.

function mostCommon(arr){
  if(!arr || arr.length===0) return null;
  const freq = {};
  for (const v of arr){ freq[v]=(freq[v]||0)+1; }
  let max = 0; let val=null;
  for (const k of Object.keys(freq)){
    if (freq[k] > max){ max=freq[k]; val=k; }
  }
  return val;
}

function detectUnusualLogin(events){
  const byUser = new Map();
  for(const e of events){ if(!e.userId) continue; if(!byUser.has(e.userId)) byUser.set(e.userId,[]); byUser.get(e.userId).push(e); }
  const anomalies=[];
  for(const [user, list] of byUser.entries()){
    const sorted = list.slice().sort((a,b)=> new Date(a.timestamp)-new Date(b.timestamp));
    for(let i=0;i<sorted.length;i++){
      const ev = sorted[i]; const time = new Date(ev.timestamp).getTime();
      const windowMs = 7*24*60*60*1000;
      const prev = sorted.filter((_,idx)=> idx<i && (new Date(sorted[idx].timestamp).getTime() >= time - windowMs));
      const prevDevices = prev.map(p=>p.device).filter(Boolean);
      const most = mostCommon(prevDevices);
      let reason=''; let score=0;
      if(prev.length>0 && ev.location){ const diff = prev.some(p=> p.location && p.location !== ev.location); if(diff){ reason += 'Unusual login location'; score++; }}
      if(ev.device && most && ev.device !== most){ reason += (reason? '; ': '') + 'New device detected'; score++; }
      if(reason){ anomalies.push({userId:user, loginEvent:ev, reason, score}); }
    }
  }
  return anomalies;
}

const sample = [
  {userId:'u1', ip:'1.1.1.1', location:'US', device:'Chrome-iPhone', timestamp:'2026-03-01T10:00:00Z'},
  {userId:'u1', ip:'1.1.1.2', location:'US', device:'Chrome-Laptop', timestamp:'2026-03-01T12:00:00Z'},
  {userId:'u1', ip:'1.1.2.3', location:'DE', device:'Chrome-Laptop', timestamp:'2026-03-01T18:00:00Z'},
  {userId:'u1', ip:'1.1.3.4', location:'DE', device:'Firefox-PC', timestamp:'2026-03-02T09:00:00Z'},
  {userId:'u2', ip:'9.9.9.9', location:'IN', device:'App', timestamp:'2026-03-01T11:00:00Z'},
  {userId:'u2', ip:'9.9.9.10', location:'IN', device:'App', timestamp:'2026-03-01T11:30:00Z'},
  {userId:'u2', ip:'9.9.9.11', location:'US', device:'App', timestamp:'2026-03-01T12:10:00Z'},
];

const anomalies = detectUnusualLogin(sample);
console.log('Anomalies found:', anomalies);
