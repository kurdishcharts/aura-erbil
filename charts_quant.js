// Aura-Erbil Quantitative Analytics — Group B (Volume & Activity) + Group C (Volatility & Momentum)
// Uses global D array from index.html. Auto-refreshes every 2 minutes.
(function () {
  'use strict';

  const TICK = { font: { family: 'DM Mono', size: 9 }, color: '#8892a4' };
  const GRID = '#eaecf2';
  const BASE = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } };
  let allCharts = [];

  const sentScore = a => a.sentiment === 'positive' ? 1 : a.sentiment === 'negative' ? -1 : 0;
  const sColor    = s => s === 'positive' ? '#059669' : s === 'negative' ? '#dc2626' : '#d97706';

  function destroyAll() {
    allCharts.forEach(c => { try { c.destroy(); } catch (e) {} });
    allCharts = [];
  }

  function mkCard(panel, title) {
    const card = document.createElement('div');
    card.className = 'quant-card';
    card.style.cssText = 'background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;';
    const h = document.createElement('div');
    h.style.cssText = 'font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:12px;';
    h.textContent = title;
    card.appendChild(h);
    panel.appendChild(card);
    return card;
  }

  function mkCanvas(card, height) {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'height:' + height + 'px;position:relative;';
    card.appendChild(wrap);
    const canvas = document.createElement('canvas');
    wrap.appendChild(canvas);
    return canvas;
  }

  function mkC(canvas, cfg) {
    const c = new Chart(canvas.getContext('2d'), cfg);
    allCharts.push(c);
    return c;
  }

  function buildAll(articles) {
    const panel = document.getElementById('quant-panel');
    if (!panel) return;

    const byDay = {};
    articles.forEach(a => {
      if (!a.timestamp) return;
      const d = a.timestamp.slice(0, 10);
      if (!byDay[d]) byDay[d] = [];
      byDay[d].push(a);
    });
    const days      = Object.keys(byDay).sort();
    const shortLbls = days.map(d => d.slice(5));
    const dailyVol  = days.map(d => byDay[d].length);

    // B1. Daily Volume
    {
      const card   = mkCard(panel, 'Daily Volume · Articles per Day');
      const canvas = mkCanvas(card, 145);
      mkC(canvas, {
        type: 'bar',
        data: { labels: shortLbls, datasets: [{ data: dailyVol, backgroundColor: '#bfdbfe', borderColor: '#1a56db', borderWidth: 1, borderRadius: 3, borderSkipped: false }] },
        options: { ...BASE, scales: { x: { ticks: TICK, grid: { display: false } }, y: { ticks: TICK, grid: { color: GRID }, beginAtZero: true } } }
      });
    }

    // B2. Hourly Activity
    {
      const card   = mkCard(panel, 'Hourly Activity · Articles by Hour');
      const canvas = mkCanvas(card, 145);
      const hours  = new Array(24).fill(0);
      articles.forEach(a => { if (a.timestamp) hours[new Date(a.timestamp).getHours()]++; });
      mkC(canvas, {
        type: 'bar',
        data: { labels: Array.from({ length: 24 }, (_, i) => i + 'h'), datasets: [{ data: hours, backgroundColor: hours.map(v => `rgba(26,86,219,${Math.min(0.15 + v / 10, 0.9)})`), borderWidth: 0, borderRadius: 2, borderSkipped: false }] },
        options: { ...BASE, scales: { x: { ticks: TICK, grid: { display: false } }, y: { ticks: TICK, grid: { color: GRID }, beginAtZero: true } } }
      });
    }

    // B3. Weekday Activity
    {
      const card   = mkCard(panel, 'Weekday Activity · Which Day is Busiest');
      const canvas = mkCanvas(card, 145);
      const dow    = new Array(7).fill(0);
      articles.forEach(a => { if (a.timestamp) dow[new Date(a.timestamp).getDay()]++; });
      mkC(canvas, {
        type: 'bar',
        data: { labels: ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'], datasets: [{ data: dow, backgroundColor: ['#e0e7ff','#c7d2fe','#a5b4fc','#818cf8','#6366f1','#4f46e5','#4338ca'], borderWidth: 0, borderRadius: 5, borderSkipped: false }] },
        options: { ...BASE, scales: { x: { ticks: TICK, grid: { display: false } }, y: { ticks: TICK, grid: { color: GRID }, beginAtZero: true } } }
      });
    }

    // B4. Source × Sentiment stacked
    {
      const card   = mkCard(panel, 'Source × Sentiment · Stacked');
      const canvas = mkCanvas(card, 145);
      const srcs   = [...new Set(articles.map(a => a.source).filter(Boolean))].slice(0, 8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: srcs, datasets: [
          { label: 'Positive', data: srcs.map(s => articles.filter(a => a.source===s && a.sentiment==='positive').length), backgroundColor: 'rgba(5,150,105,.75)' },
          { label: 'Negative', data: srcs.map(s => articles.filter(a => a.source===s && a.sentiment==='negative').length), backgroundColor: 'rgba(220,38,38,.75)' },
          { label: 'Neutral',  data: srcs.map(s => articles.filter(a => a.source===s && a.sentiment==='neutral').length),  backgroundColor: 'rgba(217,119,6,.65)' },
        ]},
        options: { ...BASE,
          plugins: { legend: { display: true, position: 'top', labels: { font: { family: 'DM Sans', size: 9 }, color: '#4b5875', padding: 8, usePointStyle: true, pointStyleWidth: 6 } } },
          scales: { x: { stacked: true, ticks: { ...TICK, maxRotation: 45 }, grid: { display: false } }, y: { stacked: true, ticks: TICK, grid: { color: GRID }, beginAtZero: true } }
        }
      });
    }

    // B5. Silence Detection — 48h coverage
    {
      const card    = mkCard(panel, 'Silence Detection · 48h Coverage Gaps');
      const canvas  = mkCanvas(card, 145);
      const hourMap = {};
      articles.forEach(a => {
        if (!a.timestamp) return;
        const key = new Date(a.timestamp).toISOString().slice(0, 13);
        hourMap[key] = (hourMap[key] || 0) + 1;
      });
      const now = new Date();
      const last48 = [], last48L = [];
      for (let i = 47; i >= 0; i--) {
        const d   = new Date(now - i * 3600000);
        const key = d.toISOString().slice(0, 13);
        last48.push(hourMap[key] || 0);
        last48L.push(d.getHours() + 'h');
      }
      mkC(canvas, {
        type: 'bar',
        data: { labels: last48L, datasets: [{ data: last48, backgroundColor: last48.map(v => v === 0 ? 'rgba(220,38,38,.45)' : 'rgba(5,150,105,.45)'), borderWidth: 0, borderRadius: 2, borderSkipped: false }] },
        options: { ...BASE, scales: { x: { ticks: { ...TICK, maxTicksLimit: 12 }, grid: { display: false } }, y: { ticks: TICK, grid: { color: GRID }, beginAtZero: true } } }
      });
    }

    // C1. Sentiment Volatility — 5-day rolling STD
    {
      const card     = mkCard(panel, 'Sentiment Volatility · 5-Day Rolling STD');
      const canvas   = mkCanvas(card, 145);
      const dailyAvg = days.map(d => { const arr = byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const rollStd  = dailyAvg.map((_, i) => {
        if (i < 4) return null;
        const sl = dailyAvg.slice(i-4, i+1), mean = sl.reduce((a,b)=>a+b,0)/5;
        return +Math.sqrt(sl.reduce((a,b)=>a+(b-mean)**2,0)/5).toFixed(3);
      });
      mkC(canvas, {
        type: 'line',
        data: { labels: shortLbls, datasets: [{ data: rollStd, borderColor: '#7c3aed', backgroundColor: 'rgba(124,58,237,.08)', fill: true, tension: .4, pointRadius: 2, spanGaps: true }] },
        options: { ...BASE, scales: { x: { ticks: TICK, grid: { display: false } }, y: { ticks: TICK, grid: { color: GRID }, min: 0 } } }
      });
    }

    // C2. Sentiment Momentum
    {
      const card     = mkCard(panel, 'Sentiment Momentum · Day-over-Day Δ');
      const canvas   = mkCanvas(card, 145);
      const posRatio = days.map(d => byDay[d].filter(a=>a.sentiment==='positive').length / byDay[d].length);
      const mom      = posRatio.map((v,i) => i===0 ? 0 : +(v-posRatio[i-1]).toFixed(3));
      mkC(canvas, {
        type: 'bar',
        data: { labels: shortLbls, datasets: [{ data: mom, backgroundColor: mom.map(v=>v>=0?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderColor: mom.map(v=>v>=0?'#059669':'#dc2626'), borderWidth: 1, borderRadius: 3, borderSkipped: false }] },
        options: { ...BASE, scales: { x: { ticks: TICK, grid: { display: false } }, y: { ticks: TICK, grid: { color: GRID } } } }
      });
    }

    // C3. Panic Index
    {
      const card = mkCard(panel, 'Panic Index · % Negative Right Now');
      const neg  = articles.filter(a=>a.sentiment==='negative').length;
      const pct  = articles.length ? Math.round(neg/articles.length*100) : 0;
      const col  = pct>=60?'#dc2626':pct>=40?'#d97706':'#059669';
      const lbl  = pct>=60?'HIGH PANIC':pct>=40?'ELEVATED':'CALM';
      const num  = document.createElement('div');
      num.style.cssText = `text-align:center;padding:12px 0 2px;font-family:'DM Mono',monospace;font-size:42px;font-weight:500;color:${col};line-height:1;`;
      num.textContent = pct+'%'; card.appendChild(num);
      const lb = document.createElement('div');
      lb.style.cssText = `text-align:center;font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:${col};margin-bottom:10px;`;
      lb.textContent = lbl; card.appendChild(lb);
      const canvas = mkCanvas(card, 65);
      mkC(canvas, { type:'doughnut', data:{ datasets:[{ data:[pct,100-pct], backgroundColor:[col,'#e8ecf3'], borderWidth:0, circumference:180, rotation:270 }]}, options:{...BASE,cutout:'65%',plugins:{legend:{display:false},tooltip:{enabled:false}}} });
    }

    // C4. Sentiment Velocity — scatter
    {
      const card   = mkCard(panel, 'Sentiment Velocity · Hour vs Score');
      const canvas = mkCanvas(card, 145);
      const pts    = articles.filter(a=>a.timestamp).map(a=>({x:new Date(a.timestamp).getHours(),y:sentScore(a),s:a.sentiment}));
      mkC(canvas, {
        type: 'scatter',
        data: { datasets: [{ data: pts, backgroundColor: pts.map(p=>sColor(p.s)+'88'), pointRadius: 3, pointHoverRadius: 5 }] },
        options: { ...BASE, scales: { x:{ticks:{...TICK,callback:v=>v+'h'},grid:{display:false},min:0,max:23}, y:{ticks:{...TICK,callback:v=>v===1?'▲+':v===-1?'▼-':'—'},grid:{color:GRID},min:-1.5,max:1.5} } }
      });
    }

    // C5. Category Volatility — radar
    {
      const card   = mkCard(panel, 'Category Volatility · STD per Category');
      const canvas = mkCanvas(card, 165);
      const cats   = [...new Set(articles.map(a=>a.category).filter(Boolean))].slice(0,8);
      const catStd = cats.map(cat => {
        const arr = articles.filter(a=>a.category===cat).map(sentScore);
        if (arr.length < 2) return 0;
        const mean = arr.reduce((a,b)=>a+b,0)/arr.length;
        return +Math.sqrt(arr.reduce((a,b)=>a+(b-mean)**2,0)/arr.length).toFixed(3);
      });
      mkC(canvas, {
        type: 'radar',
        data: { labels: cats, datasets: [{ data: catStd, borderColor: '#1a56db', backgroundColor: 'rgba(26,86,219,.1)', pointBackgroundColor: '#1a56db', pointRadius: 3, borderWidth: 1.5 }] },
        options: { ...BASE, scales: { r: { ticks:{...TICK,backdropColor:'transparent',maxTicksLimit:3}, grid:{color:GRID}, angleLines:{color:GRID}, pointLabels:{font:{family:'DM Sans',size:9},color:'#4b5875'}, min:0 } } }
      });
    }

    // C6. Intraday Swing
    {
      const card   = mkCard(panel, 'Intraday Swing · Daily High / Low / Close');
      const canvas = mkCanvas(card, 145);
      const highs  = days.map(d=>Math.max(...byDay[d].map(sentScore)));
      const lows   = days.map(d=>Math.min(...byDay[d].map(sentScore)));
      const close  = days.map(d=>sentScore(byDay[d][byDay[d].length-1]));
      mkC(canvas, {
        type: 'line',
        data: { labels: shortLbls, datasets: [
          { label:'High',  data:highs, borderColor:'#059669', backgroundColor:'rgba(5,150,105,.07)',  fill:'+1', tension:.3, pointRadius:1, borderWidth:1.5 },
          { label:'Low',   data:lows,  borderColor:'#dc2626', backgroundColor:'rgba(220,38,38,.07)', fill:false, tension:.3, pointRadius:1, borderWidth:1.5 },
          { label:'Close', data:close, borderColor:'#1a56db', backgroundColor:'transparent',          fill:false, tension:.3, pointRadius:2, borderWidth:2, borderDash:[4,3] },
        ]},
        options: { ...BASE,
          plugins: { legend:{ display:true, position:'top', labels:{ font:{family:'DM Sans',size:9}, color:'#4b5875', padding:8, usePointStyle:true, pointStyleWidth:6 } } },
          scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:{...TICK,callback:v=>v===1?'+1':v===-1?'-1':'0'},grid:{color:GRID},min:-1.5,max:1.5} }
        }
      });
    }
  }

  function init() {
    if (typeof D === 'undefined' || !D || !D.length) { setTimeout(init, 500); return; }
    const panel = document.getElementById('quant-panel');
    if (!panel) { setTimeout(init, 500); return; }
    buildAll(D);
    setInterval(() => {
      if (typeof D === 'undefined' || !D.length) return;
      destroyAll();
      document.querySelectorAll('.quant-card').forEach(el => el.remove());
      buildAll(D);
    }, 120_000);
  }

  init();
})();

function buildTikTokPanel() {
  const accounts = [
    {username: 'rudaw.official', name: 'Rudaw'},
    {username: 'channel8corp', name: 'Channel8'},
    {username: 'nrttvofficial', name: 'NRT'},
    {username: '964.kurdi', name: '964 Kurdi'},
    {username: 'vartvnet', name: 'Var TV'},
    {username: 'paytextmedia', name: 'Paytext Media'},
    {username: 'kurdistan24', name: 'Kurdistan24'},
    {username: 'avamediatv', name: 'Ava Media'}
  ];
  const grid = document.getElementById('quant-panel');
  if (!grid) return;
  const section = document.createElement('div');
  section.style.cssText = 'grid-column:1/-1;';
  const title = document.createElement('h2');
  title.textContent = 'TikTok News Accounts';
  title.style.cssText = 'font-size:0.85rem;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted-foreground);margin-bottom:0.75rem;';
  section.appendChild(title);
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;flex-wrap:wrap;gap:1rem;';
  accounts.forEach(acc => {
    const card = document.createElement('div');
    card.style.cssText = 'background:var(--card);border:1px solid var(--border);border-radius:0.5rem;padding:0.75rem 1rem;min-width:160px;';
    card.innerHTML = `<a href="https://www.tiktok.com/@${acc.username}" target="_blank" style="text-decoration:none;color:var(--text);">
      <div style="font-weight:600;font-size:0.9rem;">${acc.name}</div>
      <div style="font-size:0.75rem;color:var(--text2);">@${acc.username}</div>
    </a>`;
    row.appendChild(card);
  });
  section.appendChild(row);
  grid.appendChild(section);
}
if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', function() {
    setTimeout(buildTikTokPanel, 500);
  });
} else {
  setTimeout(buildTikTokPanel, 500);
}
