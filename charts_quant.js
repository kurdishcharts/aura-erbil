// Aura-Erbil Quantitative Analytics — Complete Chart Suite
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

    // B5. Silence Detection
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

    // C1. Sentiment Volatility
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

    // C4. Sentiment Velocity scatter
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

    // C5. Category Volatility radar
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

    // D1. Entity Type Distribution
    {
      const card   = mkCard(panel, 'Entity Type Distribution');
      const canvas = mkCanvas(card, 145);
      const typeCounts = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.forEach(e => {
          const t = (e.type || 'OTHER').toUpperCase();
          typeCounts[t] = (typeCounts[t] || 0) + 1;
        });
      });
      const types  = Object.keys(typeCounts);
      const colors = ['#1a56db','#059669','#7c3aed','#d97706','#dc2626','#0891b2','#be185d','#0f766e'];
      mkC(canvas, {
        type: 'doughnut',
        data: { labels: types, datasets: [{ data: types.map(t=>typeCounts[t]), backgroundColor: colors.slice(0,types.length), borderWidth: 0 }] },
        options: { ...BASE, cutout:'60%', plugins:{ legend:{ display:true, position:'right', labels:{ font:{family:'DM Sans',size:9}, color:'#4b5875', padding:6, usePointStyle:true, pointStyleWidth:6 } } } }
      });
    }

    // D2. Top Persons Mentioned
    {
      const card   = mkCard(panel, 'Top Persons Mentioned');
      const canvas = mkCanvas(card, 145);
      const counts = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.filter(e => e.type === 'PERSON').forEach(e => { counts[e.name] = (counts[e.name] || 0) + 1; });
      });
      const top = Object.entries(counts).sort((a,b) => b[1]-a[1]).slice(0,8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t=>t[0]), datasets: [{ data: top.map(t=>t[1]), backgroundColor: 'rgba(26,86,219,.65)', borderWidth: 0, borderRadius: 4, borderSkipped: false }] },
        options: { ...BASE, indexAxis:'y', scales: { x:{ticks:TICK,grid:{color:GRID},beginAtZero:true}, y:{ticks:{...TICK,font:{size:9}},grid:{display:false}} } }
      });
    }

    // D3. Top Organizations
    {
      const card   = mkCard(panel, 'Top Organizations');
      const canvas = mkCanvas(card, 145);
      const counts = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.filter(e => e.type === 'ORGANIZATION').forEach(e => { counts[e.name] = (counts[e.name] || 0) + 1; });
      });
      const top = Object.entries(counts).sort((a,b) => b[1]-a[1]).slice(0,8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t=>t[0]), datasets: [{ data: top.map(t=>t[1]), backgroundColor: 'rgba(124,58,237,.65)', borderWidth: 0, borderRadius: 4, borderSkipped: false }] },
        options: { ...BASE, indexAxis:'y', scales: { x:{ticks:TICK,grid:{color:GRID},beginAtZero:true}, y:{ticks:{...TICK,font:{size:9}},grid:{display:false}} } }
      });
    }

    // D4. Entity Co-occurrence
    {
      const card   = mkCard(panel, 'Entity Co-occurrence · Top Pairs');
      const canvas = mkCanvas(card, 145);
      const pairs = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        const names = [...new Set(ents.map(e => e.name).filter(Boolean))].slice(0,5);
        for (let i=0; i<names.length; i++) for (let j=i+1; j<names.length; j++) {
          const key = [names[i],names[j]].sort().join(' + ');
          pairs[key] = (pairs[key] || 0) + 1;
        }
      });
      const top = Object.entries(pairs).sort((a,b) => b[1]-a[1]).slice(0,8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t=>t[0]), datasets: [{ data: top.map(t=>t[1]), backgroundColor: 'rgba(8,145,178,.65)', borderWidth: 0, borderRadius: 3, borderSkipped: false }] },
        options: { ...BASE, indexAxis:'y', scales: { x:{ticks:TICK,grid:{color:GRID},beginAtZero:true}, y:{ticks:{...TICK,font:{size:8}},grid:{display:false}} } }
      });
    }

    // D5. Entity Sentiment Breakdown
    {
      const card   = mkCard(panel, 'Entity Sentiment Breakdown');
      const canvas = mkCanvas(card, 145);
      const entSent = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.slice(0,3).forEach(e => {
          const n = e.name; if (!n) return;
          if (!entSent[n]) entSent[n] = {pos:0,neg:0,neu:0,total:0};
          entSent[n][a.sentiment==='positive'?'pos':a.sentiment==='negative'?'neg':'neu']++;
          entSent[n].total++;
        });
      });
      const top = Object.entries(entSent).sort((a,b) => b[1].total-a[1].total).slice(0,8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t=>t[0]), datasets:[
          { label:'Pos', data:top.map(t=>t[1].pos), backgroundColor:'rgba(5,150,105,.75)',  borderWidth:0 },
          { label:'Neg', data:top.map(t=>t[1].neg), backgroundColor:'rgba(220,38,38,.75)',  borderWidth:0 },
          { label:'Neu', data:top.map(t=>t[1].neu), backgroundColor:'rgba(217,119,6,.65)',  borderWidth:0 },
        ]},
        options: { ...BASE,
          plugins:{ legend:{ display:true, position:'top', labels:{font:{family:'DM Sans',size:9},color:'#4b5875',padding:6,usePointStyle:true,pointStyleWidth:6} } },
          scales:{ x:{stacked:true,ticks:{...TICK,font:{size:8}},grid:{display:false}}, y:{stacked:true,ticks:TICK,grid:{color:GRID},beginAtZero:true} }
        }
      });
    }

    // E1. Sentiment Z-Score
    {
      const card     = mkCard(panel, 'Sentiment Z-Score · Daily vs Mean');
      const canvas   = mkCanvas(card, 145);
      const dailyAvg = days.map(d => { const arr = byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const mean     = dailyAvg.reduce((a,b)=>a+b,0)/dailyAvg.length;
      const std      = Math.sqrt(dailyAvg.reduce((a,b)=>a+(b-mean)**2,0)/dailyAvg.length) || 1;
      const zScores  = dailyAvg.map(v => +((v-mean)/std).toFixed(2));
      mkC(canvas, {
        type: 'bar',
        data: { labels: shortLbls, datasets: [{ data: zScores, backgroundColor: zScores.map(v=>v>=0?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderWidth:0, borderRadius:3, borderSkipped:false }] },
        options: { ...BASE, scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} } }
      });
    }

    // E2. Category Correlation
    {
      const card   = mkCard(panel, 'Category Correlation · % Positive per Category');
      const canvas = mkCanvas(card, 145);
      const cats   = [...new Set(articles.map(a => a.category).filter(Boolean))].slice(0,8);
      const pctPos = cats.map(c => {
        const sub = articles.filter(a => a.category === c);
        return sub.length ? Math.round(sub.filter(a => a.sentiment === 'positive').length / sub.length * 100) : 0;
      });
      mkC(canvas, {
        type: 'bar',
        data: { labels: cats, datasets: [{ data: pctPos, backgroundColor: pctPos.map(v=>v>=50?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderWidth:0, borderRadius:4, borderSkipped:false }] },
        options: { ...BASE, scales: { x:{ticks:{...TICK,maxRotation:45},grid:{display:false}}, y:{ticks:{...TICK,callback:v=>v+'%'},grid:{color:GRID},beginAtZero:true,max:100} } }
      });
    }

    // E3. Bull/Bear Acceleration
    {
      const card   = mkCard(panel, 'Bull/Bear Acceleration · Δ² Pos Ratio');
      const canvas = mkCanvas(card, 145);
      const posR   = days.map(d => byDay[d].filter(a => a.sentiment === 'positive').length / byDay[d].length);
      const mom    = posR.map((v,i) => i===0 ? 0 : v - posR[i-1]);
      const accel  = mom.map((v,i) => i===0 ? 0 : +(v - mom[i-1]).toFixed(3));
      mkC(canvas, {
        type: 'bar',
        data: { labels: shortLbls, datasets: [{ data: accel, backgroundColor: accel.map(v=>v>=0?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderWidth:0, borderRadius:3, borderSkipped:false }] },
        options: { ...BASE, scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} } }
      });
    }

    // E4. Sentiment Velocity · Hourly
    {
      const card    = mkCard(panel, 'Sentiment Velocity · Hourly Average Score');
      const canvas  = mkCanvas(card, 145);
      const byHour  = {};
      articles.forEach(a => { if (!a.timestamp) return; const h = new Date(a.timestamp).getHours(); if (!byHour[h]) byHour[h]=[]; byHour[h].push(sentScore(a)); });
      const hourAvg = Array.from({length:24}, (_,i) => { const arr = byHour[i] || []; return arr.length ? +(arr.reduce((a,b)=>a+b,0)/arr.length).toFixed(2) : null; });
      mkC(canvas, {
        type:'line',
        data: { labels: Array.from({length:24},(_,i)=>i+'h'), datasets: [{ data: hourAvg, borderColor:'#0891b2', backgroundColor:'rgba(8,145,178,.08)', fill:true, tension:.4, pointRadius:2, spanGaps:true }] },
        options: { ...BASE, scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID},min:-1,max:1} } }
      });
    }

    // E5. Cumulative Net Sentiment
    {
      const card   = mkCard(panel, 'Cumulative Net Sentiment');
      const canvas = mkCanvas(card, 145);
      let cum = 0;
      const cumArr = days.map(d => { cum += byDay[d].reduce((s,a) => s + sentScore(a), 0); return cum; });
      const col    = cumArr[cumArr.length-1] >= 0 ? '#059669' : '#dc2626';
      mkC(canvas, {
        type:'line',
        data: { labels: shortLbls, datasets: [{ data: cumArr, borderColor: col, backgroundColor: col+'18', fill:true, tension:.4, pointRadius:1.5 }] },
        options: { ...BASE, scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} } }
      });
    }

    // E6. Daily Volatility
    {
      const card   = mkCard(panel, 'Daily Volatility · Absolute Daily Swing');
      const canvas = mkCanvas(card, 145);
      const swing  = days.map(d => { const arr = byDay[d].map(sentScore); return +(Math.max(...arr) - Math.min(...arr)).toFixed(2); });
      mkC(canvas, {
        type:'bar',
        data: { labels: shortLbls, datasets: [{ data: swing, backgroundColor:'rgba(124,58,237,.55)', borderWidth:0, borderRadius:3, borderSkipped:false }] },
        options: { ...BASE, scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID},beginAtZero:true} } }
      });
    }

    // E7. SMA Crossover
    {
      const card     = mkCard(panel, 'SMA Crossover · 3d vs 7d');
      const canvas   = mkCanvas(card, 145);
      const dailyAvg = days.map(d => { const arr = byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const sma      = n => dailyAvg.map((_,i) => i<n-1 ? null : +(dailyAvg.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n).toFixed(3));
      mkC(canvas, {
        type:'line',
        data: { labels: shortLbls, datasets: [
          { label:'SMA3', data:sma(3), borderColor:'#1a56db', tension:.4, pointRadius:1.5, borderWidth:2,   spanGaps:true },
          { label:'SMA7', data:sma(7), borderColor:'#d97706', tension:.4, pointRadius:1.5, borderWidth:1.5, borderDash:[4,3], spanGaps:true },
        ]},
        options: { ...BASE,
          plugins:{ legend:{ display:true, position:'top', labels:{font:{family:'DM Sans',size:9},color:'#4b5875',padding:8,usePointStyle:true,pointStyleWidth:6} } },
          scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} }
        }
      });
    }

    // E8. Intraday Sentiment Swing · 4h
    {
      const card   = mkCard(panel, 'Intraday Sentiment Swing · 4h Blocks');
      const canvas = mkCanvas(card, 145);
      const blocks = ['0–4h','4–8h','8–12h','12–16h','16–20h','20–24h'];
      const bData  = blocks.map((_,i) => {
        const arr = articles.filter(a => { if (!a.timestamp) return false; const h = new Date(a.timestamp).getHours(); return h>=i*4 && h<(i+1)*4; }).map(sentScore);
        return arr.length ? +(arr.reduce((a,b)=>a+b,0)/arr.length).toFixed(2) : 0;
      });
      mkC(canvas, {
        type:'bar',
        data: { labels: blocks, datasets: [{ data: bData, backgroundColor: bData.map(v=>v>=0?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderWidth:0, borderRadius:4, borderSkipped:false }] },
        options: { ...BASE, scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID},min:-1,max:1} } }
      });
    }

    // F1. Flashpoint Detection
    {
      const card   = mkCard(panel, 'Flashpoint Detection · Volume Z‑Score');
      const canvas = mkCanvas(card, 145);
      const dailyVol = days.map(d => byDay[d].length);
      const meanVol  = dailyVol.reduce((a,b)=>a+b,0)/dailyVol.length;
      const stdVol   = Math.sqrt(dailyVol.reduce((a,b)=>a+(b-meanVol)**2,0)/dailyVol.length) || 1;
      const zVol     = dailyVol.map(v => +((v-meanVol)/stdVol).toFixed(2));
      const highlights = dailyVol.map((v,i) => v > meanVol + 1.5*stdVol ? v : 0);
      mkC(canvas, {
        type: 'bar',
        data: { labels: shortLbls, datasets: [
          { label: 'Z‑Score', data: zVol, backgroundColor: zVol.map(v => v>=2?'rgba(220,38,38,.85)':v>=1?'rgba(217,119,6,.65)':'rgba(26,86,219,.40)'), borderWidth:0, borderRadius:4, borderSkipped:false },
          { label: 'Spike', data: highlights, backgroundColor: 'rgba(220,38,38,.90)', borderWidth:0, type:'bar', order:1 }
        ]},
        options: { ...BASE, scales: { x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} } }
      });
    }

    // F2. Polarization Index
    {
      const card   = mkCard(panel, 'Polarization Index · Sentiment Distribution');
      const canvas = mkCanvas(card, 145);
      const bins   = [-1.0,-0.8,-0.6,-0.4,-0.2,0,0.2,0.4,0.6,0.8,1.0];
      const hist   = bins.map((b,i) => {
        const next = bins[i+1] || 1.1;
        return articles.filter(a => sentScore(a) >= b && sentScore(a) < next).length;
      });
      mkC(canvas, {
        type: 'bar',
        data: { labels: bins.map(b => b.toFixed(1)), datasets: [{ data: hist, backgroundColor: hist.map((_,i) => i<5?'rgba(220,38,38,.65)':'rgba(5,150,105,.65)'), borderWidth:0, borderRadius:3, barPercentage:0.95 }] },
        options: { ...BASE, scales: { x:{ticks:{...TICK,font:{size:8}},grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} } }
      });
    }

    // F3. Source Bias Matrix
    {
      const card   = mkCard(panel, 'Source Bias Matrix · Sentiment vs Subjectivity');
      const canvas = mkCanvas(card, 145);
      const sources = [...new Set(articles.map(a => a.source))].slice(0,10);
      const data = sources.map(src => {
        const arts = articles.filter(a => a.source === src);
        const avgSent = arts.length ? arts.reduce((s,a) => s+sentScore(a),0)/arts.length : 0;
        const subjectivity = arts.length ? arts.reduce((s,a) => {
          const txt = ((a.title_en||a.title||'') + ' ' + (a.summary||'')).toLowerCase();
          const opinionWords = /\b(think|believe|opinion|suggest|maybe|perhaps|likely|feel|seem)\b/g;
          return s + (txt.match(opinionWords) || []).length;
        },0)/arts.length : 0;
        return { x: +avgSent.toFixed(3), y: +subjectivity.toFixed(2), label: src };
      });
      mkC(canvas, {
        type: 'scatter',
        data: { datasets: [{ label: 'Sources', data: data, backgroundColor: data.map(d => d.x >= 0 ? 'rgba(5,150,105,.7)' : 'rgba(220,38,38,.7)'), borderColor: 'transparent' }] },
        options: { ...BASE,
          plugins: { tooltip: { callbacks: { label: ctx => ctx.raw.label } } },
          scales: { x: { title:{display:true,text:'Avg Sentiment'}, ticks:TICK, grid:{color:GRID} }, y: { title:{display:true,text:'Subjectivity'}, ticks:TICK, grid:{color:GRID} } }
        }
      });
    }

    // F4. Political Weight Bar
    {
      const card   = mkCard(panel, 'Political Weight · Top Figures');
      const canvas = mkCanvas(card, 145);
      const entCount = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.filter(e => e.type === 'PERSON').forEach(e => {
          entCount[e.name] = (entCount[e.name] || 0) + 1 + Math.abs(sentScore(a)) * 2;
        });
      });
      const top = Object.entries(entCount).sort((a,b) => b[1]-a[1]).slice(0,15);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t => t[0]), datasets: [{ data: top.map(t => t[1]), backgroundColor: 'rgba(26,86,219,.70)', borderWidth:0, borderRadius:3, borderSkipped:false }] },
        options: { ...BASE, indexAxis:'y', scales: { x:{ticks:TICK,grid:{color:GRID}}, y:{ticks:{...TICK,font:{size:8}},grid:{display:false}} } }
      });
    }

    // F5. Stability Index
    {
      const card   = mkCard(panel, 'Stability Index · KRI Composite');
      const canvas = mkCanvas(card, 145);
      const dailySent = days.map(d => {
        const arr = byDay[d].map(sentScore);
        return arr.reduce((a,b)=>a+b,0)/arr.length;
      });
      const volatility = +(Math.sqrt(dailySent.reduce((a,b)=>a+(b-0)**2,0)/dailySent.length)).toFixed(3);
      const avgVol     = days.map(d => byDay[d].length).reduce((a,b)=>a+b,0)/days.length;
      const stability  = Math.max(0, Math.min(100, Math.round((1 - volatility) * 50 + (avgVol>5?30:20))));
      const color      = stability >= 60 ? '#059669' : stability >= 40 ? '#d97706' : '#dc2626';
      mkC(canvas, {
        type: 'doughnut',
        data: { datasets: [{ data: [stability, 100-stability], backgroundColor: [color, '#e8ecf3'], borderWidth:0, circumference:180, rotation:270 }] },
        options: { ...BASE, cutout:'72%', plugins:{ legend:{display:false}, tooltip:{enabled:false} } }
      });
    }

    // F6. Reach vs Impact Bubble
    {
      const card   = mkCard(panel, 'Reach vs Impact · Bubble');
      const canvas = mkCanvas(card, 145);
      const reachMap = {};
      articles.forEach(a => { reachMap[a.source] = (reachMap[a.source]||0)+1; });
      const data = articles.slice(0,80).map(a => ({
        x: Math.abs(sentScore(a)),
        y: reachMap[a.source] || 1,
        r: Math.min(15, 3 + (a.breaking || 1) * 2),
        sentiment: sentScore(a)
      }));
      mkC(canvas, {
        type: 'bubble',
        data: { datasets: [{ data: data, backgroundColor: data.map(d => d.sentiment >= 0 ? 'rgba(5,150,105,.6)' : 'rgba(220,38,38,.6)'), borderColor: 'transparent' }] },
        options: { ...BASE, scales: { x: { title:{display:true,text:'Sentiment Intensity'}, ticks:TICK, grid:{color:GRID} }, y: { title:{display:true,text:'Source Reach'}, ticks:TICK, grid:{color:GRID} } } }
      });
    }

    // F7. Source Reliability
    {
      const card   = mkCard(panel, 'Source Reliability · Fact vs Opinion');
      const canvas = mkCanvas(card, 145);
      const srcs = [...new Set(articles.map(a => a.source))].slice(0,8);
      const factWords = /\b(according|reported|confirmed|official|data|statistics|document|statement|announced|figure)\b/g;
      const opWords   = /\b(think|believe|opinion|suggest|maybe|perhaps|likely|feel|seem)\b/g;
      const data = srcs.map(src => {
        const arts = articles.filter(a => a.source === src);
        let fact=0, op=0;
        arts.forEach(a => {
          const txt = ((a.title_en||a.title||'') + ' ' + (a.summary||'')).toLowerCase();
          fact += (txt.match(factWords) || []).length;
          op   += (txt.match(opWords) || []).length;
        });
        const total = fact+op || 1;
        return { src, fact: +(fact/total*100).toFixed(1), op: +(op/total*100).toFixed(1) };
      });
      mkC(canvas, {
        type: 'bar',
        data: { labels: data.map(d => d.src), datasets: [
          { label:'Fact', data: data.map(d => d.fact), backgroundColor:'rgba(26,86,219,.75)', borderWidth:0 },
          { label:'Opinion', data: data.map(d => d.op), backgroundColor:'rgba(220,38,38,.55)', borderWidth:0 }
        ]},
        options: { ...BASE,
          plugins:{ legend:{ display:true, position:'top', labels:{font:{family:'DM Sans',size:9},color:'#4b5875',padding:6,usePointStyle:true,pointStyleWidth:6} } },
          scales:{ x:{stacked:true,ticks:{...TICK,maxRotation:45},grid:{display:false}}, y:{stacked:true,ticks:{...TICK,callback:v=>v+'%'},grid:{color:GRID},min:0,max:100} }
        }
      });
    }

    // G1. Article Velocity 7‑Day
    {
      const card   = mkCard(panel, 'Article Velocity · 7‑Day Rolling Avg');
      const canvas = mkCanvas(card, 145);
      const dailyVol = days.map(d => byDay[d].length);
      const rolling = dailyVol.map((_,i) => i<6 ? null : dailyVol.slice(i-6,i+1).reduce((a,b)=>a+b,0)/7);
      mkC(canvas, {
        type: 'line',
        data: { labels: shortLbls, datasets: [
          { label: 'Daily', data: dailyVol, borderColor: 'rgba(255,255,255,.15)', backgroundColor: 'transparent', tension: .3, pointRadius: 0 },
          { label: '7D Avg', data: rolling, borderColor: '#00B2FF', borderWidth: 2.5, tension: .4, pointRadius: 2, pointBackgroundColor: '#00B2FF', spanGaps: true }
        ]},
        options: { ...BASE,
          plugins: { legend: { display: true, position: 'top', labels: { font: {family:'DM Sans',size:9}, color:'#4b5875', padding:6, usePointStyle:true, pointStyleWidth:6 } } },
          scales: { x: { ticks: TICK, grid: { display: false } }, y: { ticks: TICK, grid: { color: GRID }, beginAtZero: true } }
        }
      });
    }

    // G2. Sentiment Volatility Bands
    {
      const card   = mkCard(panel, 'Sentiment Volatility Bands · Mean ±2σ');
      const canvas = mkCanvas(card, 145);
      const dailyAvg = days.map(d => {
        const scores = byDay[d].map(sentScore);
        return scores.length ? scores.reduce((a,b)=>a+b,0)/scores.length : 0;
      });
      const dailyStd = days.map((d,i) => {
        const scores = days.slice(Math.max(0,i-6),i+1).flatMap(dd => byDay[dd].map(sentScore));
        return scores.length ? Math.sqrt(scores.reduce((a,b)=>a+(b)**2,0)/scores.length) : 0;
      });
      const upper = dailyAvg.map((v,i) => v + 2*dailyStd[i]);
      const lower = dailyAvg.map((v,i) => v - 2*dailyStd[i]);
      mkC(canvas, {
        type: 'line',
        data: { labels: shortLbls, datasets: [
          { label: 'Upper', data: upper, borderColor: 'transparent', backgroundColor: 'transparent', pointRadius: 0 },
          { label: 'Lower', data: lower, borderColor: 'transparent', backgroundColor: 'rgba(0,178,255,0.08)', fill: 1, pointRadius: 0 },
          { label: 'Sentiment', data: dailyAvg, borderColor: '#FFD700', borderWidth: 2, tension: .4, pointRadius: 2, pointBackgroundColor: '#FFD700' }
        ]},
        options: { ...BASE,
          plugins: { legend: { display: false } },
          scales: { x: { ticks: TICK, grid: { display: false } }, y: { ticks: TICK, grid: { color: GRID }, min: -1, max: 1 } }
        }
      });
    }

    // G3. Source Dominance Area
    {
      const card   = mkCard(panel, 'Source Dominance · Share of Voice');
      const canvas = mkCanvas(card, 145);
      const topSources = Object.entries(
        articles.reduce((acc,a) => { const s = a.source || 'unknown'; acc[s] = (acc[s]||0)+1; return acc; }, {})
      ).sort((a,b) => b[1]-a[1]).slice(0,6).map(e => e[0]);
      const byDaySource = {};
      days.forEach(d => { byDaySource[d] = {}; topSources.forEach(s => byDaySource[d][s] = 0); });
      articles.forEach(a => {
        const d = a.timestamp && a.timestamp.slice(0,10);
        if (d && byDaySource[d]) byDaySource[d][a.source || 'unknown'] = (byDaySource[d][a.source || 'unknown']||0)+1;
      });
      const colors = ['#00B2FF','#FFD700','#FF4B4B','#00FFC2','#C77DFF','#FFA500'];
      mkC(canvas, {
        type: 'bar',
        data: { labels: shortLbls, datasets: topSources.map((s,i) => ({
          label: s, data: days.map(d => byDaySource[d][s]||0), backgroundColor: colors[i%6], borderWidth: 0, borderRadius: 2, borderSkipped: false
        }))},
        options: { ...BASE,
          plugins: { legend: { display: true, position: 'top', labels: { font: {family:'DM Sans',size:8}, color:'#4b5875', padding:4, usePointStyle:true, pointStyleWidth:4 } } },
          scales: { x: { stacked: true, ticks: TICK, grid: { display: false } }, y: { stacked: true, ticks: TICK, grid: { color: GRID }, beginAtZero: true } }
        }
      });
    }

    // G4. Geographical Impact
    {
      const card   = mkCard(panel, 'Geographical Impact · Weighted Score');
      const canvas = mkCanvas(card, 145);
      const cityScore = {};
      articles.forEach(a => {
        const loc = (a.location && a.location.name) || 'Erbil';
        const intensity = Math.abs(sentScore(a));
        cityScore[loc] = (cityScore[loc] || 0) + 1 + intensity * 5;
      });
      const topCities = Object.entries(cityScore).sort((a,b) => b[1]-a[1]).slice(0,10);
      mkC(canvas, {
        type: 'bar',
        data: { labels: topCities.map(e => e[0]), datasets: [{ data: topCities.map(e => e[1]), backgroundColor: 'rgba(0,255,194,.65)', borderWidth:0, borderRadius:4, borderSkipped:false }] },
        options: { ...BASE, indexAxis:'y', scales: { x:{ticks:TICK,grid:{color:GRID}}, y:{ticks:{...TICK,font:{size:8}},grid:{display:false}} } }
      });
    }

    // G5. Thematic Sentiment Radar
    {
      const card   = mkCard(panel, 'Thematic Sentiment · Radar');
      const canvas = mkCanvas(card, 145);
      const categories = [...new Set(articles.map(a => a.category).filter(Boolean))].slice(0,10);
      const categorySent = categories.map(c => {
        const arts = articles.filter(a => a.category === c);
        return arts.length ? arts.reduce((s,a) => s+sentScore(a),0)/arts.length : 0;
      });
      mkC(canvas, {
        type: 'radar',
        data: { labels: categories, datasets: [{ data: categorySent, borderColor: '#FFD700', backgroundColor: 'rgba(255,215,0,.1)', borderWidth: 2, pointBackgroundColor: '#FFD700' }] },
        options: { ...BASE,
          plugins: { legend: { display: false } },
          scales: { r: { ticks: { display: false }, grid: { color: GRID }, min: -1, max: 1, beginAtZero: true } }
        }
      });
    }

    // ── Entity helper ──
    function parseEnts(a) {
      if (!a.entities) return [];
      try {
        const e = typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities;
        return Array.isArray(e) ? e : [];
      } catch(_) { return []; }
    }

    // D1. Entity Type Distribution
    {
      const card   = mkCard(panel, 'Entity Type Distribution');
      const canvas = mkCanvas(card, 145);
      const typeCounts = {};
      articles.forEach(a => parseEnts(a).forEach(e => {
        const t = (e.type || 'OTHER').toUpperCase();
        typeCounts[t] = (typeCounts[t] || 0) + 1;
      }));
      const types  = Object.keys(typeCounts);
      const colors = ['#1a56db','#059669','#7c3aed','#d97706','#dc2626','#0891b2','#be185d','#0f766e'];
      mkC(canvas, {
        type: 'doughnut',
        data: { labels: types, datasets: [{ data: types.map(t=>typeCounts[t]), backgroundColor: colors.slice(0,types.length), borderWidth: 0 }] },
        options: { ...BASE, cutout:'60%', plugins:{ legend:{ display:true, position:'right', labels:{ font:{family:'DM Sans',size:9}, color:'#4b5875', padding:6, usePointStyle:true, pointStyleWidth:6 } } } }
      });
    }

    // D2. Top Persons Mentioned
    {
      const card   = mkCard(panel, 'Top Persons Mentioned');
      const canvas = mkCanvas(card, 145);
      const counts = {};
      articles.forEach(a => parseEnts(a).filter(e=>e.type==='PERSON').forEach(e => {
        counts[e.name] = (counts[e.name] || 0) + 1;
      }));
      const top = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t=>t[0]), datasets: [{ data: top.map(t=>t[1]), backgroundColor:'rgba(26,86,219,.65)', borderWidth:0, borderRadius:4, borderSkipped:false }] },
        options: { ...BASE, indexAxis:'y', scales: { x:{ticks:TICK,grid:{color:GRID},beginAtZero:true}, y:{ticks:{...TICK,font:{size:9}},grid:{display:false}} } }
      });
    }

    // D3. Top Organizations
    {
      const card   = mkCard(panel, 'Top Organizations');
      const canvas = mkCanvas(card, 145);
      const counts = {};
      articles.forEach(a => parseEnts(a).filter(e=>e.type==='ORGANIZATION').forEach(e => {
        counts[e.name] = (counts[e.name] || 0) + 1;
      }));
      const top = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t=>t[0]), datasets: [{ data: top.map(t=>t[1]), backgroundColor:'rgba(124,58,237,.65)', borderWidth:0, borderRadius:4, borderSkipped:false }] },
        options: { ...BASE, indexAxis:'y', scales: { x:{ticks:TICK,grid:{color:GRID},beginAtZero:true}, y:{ticks:{...TICK,font:{size:9}},grid:{display:false}} } }
      });
    }

    // D4. Entity Co-occurrence · Top Pairs
    {
      const card   = mkCard(panel, 'Entity Co-occurrence · Top Pairs');
      const canvas = mkCanvas(card, 145);
      const pairs  = {};
      articles.forEach(a => {
        const names = [...new Set(parseEnts(a).map(e=>e.name).filter(Boolean))].slice(0,5);
        for (let i=0;i<names.length;i++) for(let j=i+1;j<names.length;j++) {
          const key = [names[i],names[j]].sort().join(' + ');
          pairs[key] = (pairs[key]||0)+1;
        }
      });
      const top = Object.entries(pairs).sort((a,b)=>b[1]-a[1]).slice(0,8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t=>t[0]), datasets: [{ data: top.map(t=>t[1]), backgroundColor:'rgba(8,145,178,.65)', borderWidth:0, borderRadius:3, borderSkipped:false }] },
        options: { ...BASE, indexAxis:'y', scales: { x:{ticks:TICK,grid:{color:GRID},beginAtZero:true}, y:{ticks:{...TICK,font:{size:8}},grid:{display:false}} } }
      });
    }

    // D5. Entity Sentiment Breakdown
    {
      const card   = mkCard(panel, 'Entity Sentiment Breakdown');
      const canvas = mkCanvas(card, 145);
      const entSent = {};
      articles.forEach(a => parseEnts(a).slice(0,3).forEach(e => {
        const n = e.name; if (!n) return;
        if (!entSent[n]) entSent[n] = {pos:0,neg:0,neu:0,total:0};
        entSent[n][a.sentiment==='positive'?'pos':a.sentiment==='negative'?'neg':'neu']++;
        entSent[n].total++;
      }));
      const top = Object.entries(entSent).sort((a,b)=>b[1].total-a[1].total).slice(0,8);
      mkC(canvas, {
        type: 'bar',
        data: { labels: top.map(t=>t[0]), datasets:[
          { label:'Pos', data:top.map(t=>t[1].pos), backgroundColor:'rgba(5,150,105,.75)',  borderWidth:0 },
          { label:'Neg', data:top.map(t=>t[1].neg), backgroundColor:'rgba(220,38,38,.75)',  borderWidth:0 },
          { label:'Neu', data:top.map(t=>t[1].neu), backgroundColor:'rgba(217,119,6,.65)',  borderWidth:0 },
        ]},
        options: { ...BASE,
          plugins:{ legend:{ display:true, position:'top', labels:{font:{family:'DM Sans',size:9},color:'#4b5875',padding:6,usePointStyle:true,pointStyleWidth:6} } },
          scales:{ x:{stacked:true,ticks:{...TICK,font:{size:8}},grid:{display:false}}, y:{stacked:true,ticks:TICK,grid:{color:GRID},beginAtZero:true} }
        }
      });
    }

    // E1. Sentiment Z-Score
    {
      const card     = mkCard(panel, 'Sentiment Z-Score · Daily vs Mean');
      const canvas   = mkCanvas(card, 145);
      const dailyAvg = days.map(d=>{ const arr=byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const mean     = dailyAvg.reduce((a,b)=>a+b,0)/dailyAvg.length;
      const std      = Math.sqrt(dailyAvg.reduce((a,b)=>a+(b-mean)**2,0)/dailyAvg.length)||1;
      const zScores  = dailyAvg.map(v=>+((v-mean)/std).toFixed(2));
      mkC(canvas, {
        type: 'bar',
        data: { labels: shortLbls, datasets:[{ data:zScores, backgroundColor:zScores.map(v=>v>=0?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderWidth:0, borderRadius:3, borderSkipped:false }] },
        options: { ...BASE, scales:{ x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} } }
      });
    }

    // E2. Category Correlation · % Positive per Category
    {
      const card   = mkCard(panel, 'Category Correlation · % Positive per Category');
      const canvas = mkCanvas(card, 145);
      const cats   = [...new Set(articles.map(a=>a.category).filter(Boolean))].slice(0,8);
      const pctPos = cats.map(c=>{ const sub=articles.filter(a=>a.category===c); return sub.length?Math.round(sub.filter(a=>a.sentiment==='positive').length/sub.length*100):0; });
      mkC(canvas, {
        type: 'bar',
        data: { labels:cats, datasets:[{ data:pctPos, backgroundColor:pctPos.map(v=>v>=50?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderWidth:0, borderRadius:4, borderSkipped:false }] },
        options: { ...BASE, scales:{ x:{ticks:{...TICK,maxRotation:45},grid:{display:false}}, y:{ticks:{...TICK,callback:v=>v+'%'},grid:{color:GRID},beginAtZero:true,max:100} } }
      });
    }

    // E3. Bull/Bear Acceleration
    {
      const card   = mkCard(panel, 'Bull/Bear Acceleration · Δ² Pos Ratio');
      const canvas = mkCanvas(card, 145);
      const posR   = days.map(d=>byDay[d].filter(a=>a.sentiment==='positive').length/byDay[d].length);
      const mom    = posR.map((v,i)=>i===0?0:v-posR[i-1]);
      const accel  = mom.map((v,i)=>i===0?0:+(v-mom[i-1]).toFixed(3));
      mkC(canvas, {
        type: 'bar',
        data:{ labels:shortLbls, datasets:[{ data:accel, backgroundColor:accel.map(v=>v>=0?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderWidth:0, borderRadius:3, borderSkipped:false }] },
        options:{ ...BASE, scales:{ x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} } }
      });
    }

    // E4. Sentiment Velocity · Hourly Average Score
    {
      const card    = mkCard(panel, 'Sentiment Velocity · Hourly Average Score');
      const canvas  = mkCanvas(card, 145);
      const byHour  = {};
      articles.forEach(a=>{ if(!a.timestamp) return; const h=new Date(a.timestamp).getHours(); if(!byHour[h]) byHour[h]=[]; byHour[h].push(sentScore(a)); });
      const hourAvg = Array.from({length:24},(_,i)=>{ const arr=byHour[i]||[]; return arr.length?+(arr.reduce((a,b)=>a+b,0)/arr.length).toFixed(2):null; });
      mkC(canvas, {
        type:'line',
        data:{ labels:Array.from({length:24},(_,i)=>i+'h'), datasets:[{ data:hourAvg, borderColor:'#0891b2', backgroundColor:'rgba(8,145,178,.08)', fill:true, tension:.4, pointRadius:2, spanGaps:true }] },
        options:{ ...BASE, scales:{ x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID},min:-1,max:1} } }
      });
    }

    // E5. Cumulative Net Sentiment
    {
      const card   = mkCard(panel, 'Cumulative Net Sentiment');
      const canvas = mkCanvas(card, 145);
      let cum = 0;
      const cumArr = days.map(d=>{ cum += byDay[d].reduce((s,a)=>s+sentScore(a),0); return cum; });
      const col    = cumArr[cumArr.length-1] >= 0 ? '#059669' : '#dc2626';
      mkC(canvas, {
        type:'line',
        data:{ labels:shortLbls, datasets:[{ data:cumArr, borderColor:col, backgroundColor:col+'18', fill:true, tension:.4, pointRadius:1.5 }] },
        options:{ ...BASE, scales:{ x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} } }
      });
    }

    // E6. Daily Volatility
    {
      const card   = mkCard(panel, 'Daily Volatility · Absolute Daily Swing');
      const canvas = mkCanvas(card, 145);
      const swing  = days.map(d=>{ const arr=byDay[d].map(sentScore); return +(Math.max(...arr)-Math.min(...arr)).toFixed(2); });
      mkC(canvas, {
        type:'bar',
        data:{ labels:shortLbls, datasets:[{ data:swing, backgroundColor:'rgba(124,58,237,.55)', borderWidth:0, borderRadius:3, borderSkipped:false }] },
        options:{ ...BASE, scales:{ x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID},beginAtZero:true} } }
      });
    }

    // E7. SMA Crossover (3d vs 7d)
    {
      const card     = mkCard(panel, 'SMA Crossover · 3d vs 7d');
      const canvas   = mkCanvas(card, 145);
      const dailyAvg = days.map(d=>{ const arr=byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const sma      = n => dailyAvg.map((_,i)=>i<n-1?null:+(dailyAvg.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n).toFixed(3));
      mkC(canvas, {
        type:'line',
        data:{ labels:shortLbls, datasets:[
          { label:'SMA3', data:sma(3), borderColor:'#1a56db', tension:.4, pointRadius:1.5, borderWidth:2,   spanGaps:true },
          { label:'SMA7', data:sma(7), borderColor:'#d97706', tension:.4, pointRadius:1.5, borderWidth:1.5, borderDash:[4,3], spanGaps:true },
        ]},
        options:{ ...BASE,
          plugins:{ legend:{ display:true, position:'top', labels:{font:{family:'DM Sans',size:9},color:'#4b5875',padding:8,usePointStyle:true,pointStyleWidth:6} } },
          scales:{ x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID}} }
        }
      });
    }

    // E8. Intraday Sentiment Swing · 4h Blocks
    {
      const card   = mkCard(panel, 'Intraday Sentiment Swing · 4h Blocks');
      const canvas = mkCanvas(card, 145);
      const blocks = ['0–4h','4–8h','8–12h','12–16h','16–20h','20–24h'];
      const bData  = blocks.map((_,i)=>{ const arr=articles.filter(a=>{ if(!a.timestamp) return false; const h=new Date(a.timestamp).getHours(); return h>=i*4&&h<(i+1)*4; }).map(sentScore); return arr.length?+(arr.reduce((a,b)=>a+b,0)/arr.length).toFixed(2):0; });
      mkC(canvas, {
        type:'bar',
        data:{ labels:blocks, datasets:[{ data:bData, backgroundColor:bData.map(v=>v>=0?'rgba(5,150,105,.65)':'rgba(220,38,38,.65)'), borderWidth:0, borderRadius:4, borderSkipped:false }] },
        options:{ ...BASE, scales:{ x:{ticks:TICK,grid:{display:false}}, y:{ticks:TICK,grid:{color:GRID},min:-1,max:1} } }
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
