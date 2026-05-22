// Aura-Erbil Analytics Panel — self‑contained, zero impact on existing code
(function() {
  'use strict';

  // Wait for articles to be available (they're loaded asynchronously)
  function initWhenReady() {
    if (typeof articles === 'undefined' || !articles.length) {
      setTimeout(initWhenReady, 500);
      return;
    }
    buildAnalyticsGrid();
    // Rebuild when data refreshes (the existing auto-refresh sets window.articles)
    window.addEventListener('articlesUpdated', buildAnalyticsGrid);
  }

  function buildAnalyticsGrid() {
    const grid = document.getElementById('analytics-grid');
    if (!grid) return;
    grid.innerHTML = ''; // clear previous charts
    const arts = window.articles || [];

    // Create chart containers and inject them
    const chartDefs = [
      { id: 'sent-doughnut', title: 'Sentiment Distribution', type: 'doughnut' },
      { id: 'sent-trend', title: 'Sentiment Trend (7d)', type: 'line' },
      { id: 'vol-daily', title: 'Articles per Day (30d)', type: 'bar' },
      { id: 'hourly', title: 'Posting Hour', type: 'bar' },
      { id: 'weekday', title: 'Weekday Activity', type: 'bar' },
      { id: 'category-pie', title: 'Category Breakdown', type: 'pie' },
      { id: 'cat-stacked', title: 'Category × Sentiment', type: 'bar' },
      { id: 'sources', title: 'Top Sources', type: 'bar' },
      { id: 'gauge', title: 'Sentiment Index', type: 'doughnut' },
      { id: 'breaking', title: 'Breaking News Score', type: 'bar' },
      { id: 'entities', title: 'Top Entities', type: 'bar' },
      { id: 'posneg-trend', title: 'Positive vs Negative', type: 'line' },
      { id: 'neutral-ratio', title: 'Neutral Ratio', type: 'line' },
      { id: 'volatility', title: 'Volatility Index', type: 'line' },
      { id: 'recent-feed', title: 'Recent Articles', type: 'feed' },
      { id: 'length-sentiment', title: 'Title Length vs Sentiment', type: 'scatter' },
      { id: 'heatmap-table', title: 'Hourly Sentiment Heatmap', type: 'table' }
    ];

    chartDefs.forEach(def => {
      const card = document.createElement('div');
      card.className = 'bg-card';
      card.style.cssText = 'background:var(--card);border:1px solid var(--border);border-radius:0.5rem;padding:1rem;';
      const title = document.createElement('h3');
      title.textContent = def.title;
      title.style.cssText = 'font-size:0.75rem;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted-foreground);margin-bottom:0.5rem;';
      card.appendChild(title);
      if (def.type === 'feed') {
        const feedDiv = document.createElement('div');
        feedDiv.id = def.id;
        feedDiv.style.maxHeight = '200px';
        feedDiv.style.overflowY = 'auto';
        feedDiv.style.fontSize = '0.75rem';
        card.appendChild(feedDiv);
      } else if (def.type === 'table') {
        const table = document.createElement('table');
        table.id = def.id;
        table.style.cssText = 'width:100%;font-size:0.75rem;border-collapse:collapse;';
        card.appendChild(table);
      } else {
        const canvas = document.createElement('canvas');
        canvas.id = def.id;
        canvas.height = 160;
        card.appendChild(canvas);
      }
      grid.appendChild(card);
    });

    renderCharts(arts);
  }

  function renderCharts(articles) {
    if (!articles.length) return;

    // Helper: sentiment counts
    const pos = articles.filter(a=>a.sentiment==='positive').length;
    const neg = articles.filter(a=>a.sentiment==='negative').length;
    const neu = articles.filter(a=>a.sentiment==='neutral').length;

    // 1. Sentiment Doughnut
    new Chart(document.getElementById('sent-doughnut'), {
      type: 'doughnut',
      data: { labels: ['Bullish','Bearish','Neutral'], datasets: [{ data: [pos,neg,neu], backgroundColor: ['#059669','#dc2626','#d97706'] }] }
    });

    // 2. Sentiment Trend 7 days
    const days = {};
    for (let i=6; i>=0; i--) { let d=new Date(); d.setDate(d.getDate()-i); days[d.toISOString().slice(0,10)]={pos:0,neg:0,neu:0}; }
    articles.forEach(a=>{ let d=a.timestamp.slice(0,10); if(days[d]){ if(a.sentiment==='positive')days[d].pos++; else if(a.sentiment==='negative')days[d].neg++; else days[d].neu++; } });
    const labels7 = Object.keys(days).sort();
    new Chart(document.getElementById('sent-trend'), {
      type: 'line',
      data: { labels: labels7, datasets: [
        { label:'Bullish', data: labels7.map(d=>days[d].pos), borderColor:'#059669', fill:false },
        { label:'Bearish', data: labels7.map(d=>days[d].neg), borderColor:'#dc2626', fill:false },
        { label:'Neutral', data: labels7.map(d=>days[d].neu), borderColor:'#d97706', fill:false }
      ]}
    });

    // 3. Volume per day (30 days)
    const dailyMap = {};
    articles.forEach(a=>{ let d=a.timestamp.slice(0,10); dailyMap[d]=(dailyMap[d]||0)+1; });
    const sortedDays = Object.keys(dailyMap).sort().slice(-30);
    new Chart(document.getElementById('vol-daily'), {
      type: 'bar',
      data: { labels: sortedDays, datasets: [{ data: sortedDays.map(d=>dailyMap[d]), backgroundColor:'#1a56db' }] }
    });

    // 4. Hourly
    const hours = Array(24).fill(0);
    articles.forEach(a=>{ let h=new Date(a.timestamp).getHours(); hours[h]++; });
    new Chart(document.getElementById('hourly'), {
      type: 'bar',
      data: { labels: Array.from({length:24},(_,i)=>i+':00'), datasets: [{ data: hours, backgroundColor:'#1a56db' }] }
    });

    // 5. Weekday
    const weekdays = Array(7).fill(0);
    const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    articles.forEach(a=>{ let d=new Date(a.timestamp).getDay(); weekdays[d]++; });
    new Chart(document.getElementById('weekday'), {
      type: 'bar',
      data: { labels: dayNames, datasets: [{ data: weekdays, backgroundColor:'#1a56db' }] }
    });

    // 6. Category pie
    const cats = {};
    articles.forEach(a=>{ cats[a.category]=(cats[a.category]||0)+1; });
    const catLabels = Object.keys(cats);
    new Chart(document.getElementById('category-pie'), {
      type: 'pie',
      data: { labels: catLabels, datasets: [{ data: catLabels.map(c=>cats[c]) }] }
    });

    // 7. Category stacked bar
    const catSent = {};
    catLabels.forEach(c=>{ catSent[c]={pos:0,neg:0,neu:0}; });
    articles.forEach(a=>{ if(catSent[a.category]){ if(a.sentiment==='positive')catSent[a.category].pos++; else if(a.sentiment==='negative')catSent[a.category].neg++; else catSent[a.category].neu++; } });
    new Chart(document.getElementById('cat-stacked'), {
      type: 'bar',
      data: { labels: catLabels, datasets: [
        { label:'Bullish', data: catLabels.map(c=>catSent[c].pos), backgroundColor:'#059669' },
        { label:'Bearish', data: catLabels.map(c=>catSent[c].neg), backgroundColor:'#dc2626' },
        { label:'Neutral', data: catLabels.map(c=>catSent[c].neu), backgroundColor:'#d97706' }
      ]},
      options: { scales: { x:{stacked:true}, y:{stacked:true} } }
    });

    // 8. Sources
    const srcMap = {};
    articles.forEach(a=>{ srcMap[a.source]=(srcMap[a.source]||0)+1; });
    const srcSorted = Object.entries(srcMap).sort((a,b)=>b[1]-a[1]).slice(0,10);
    new Chart(document.getElementById('sources'), {
      type: 'bar',
      data: { labels: srcSorted.map(e=>e[0]), datasets: [{ data: srcSorted.map(e=>e[1]), backgroundColor:'#1a56db' }] },
      options: { indexAxis:'y' }
    });

    // 9. Gauge
    const total = pos+neg+neu;
    const score = total ? Math.round((pos*100 + neu*50)/total) : 50;
    new Chart(document.getElementById('gauge'), {
      type: 'doughnut',
      data: { datasets: [{ data: [score,100-score], backgroundColor: ['#1a56db','#e5e7eb'], circumference:180, rotation:270 }] },
      options: { plugins:{tooltip:{enabled:false}} }
    });

    // 10. Breaking scores
    const b1=articles.filter(a=>a.breaking===1).length;
    const b2=articles.filter(a=>a.breaking===2).length;
    const b3=articles.filter(a=>a.breaking===3).length;
    new Chart(document.getElementById('breaking'), {
      type: 'bar',
      data: { labels: ['Score 1','Score 2','Score 3'], datasets: [{ data: [b1,b2,b3], backgroundColor:['#9ca3af','#d97706','#dc2626'] }] }
    });

    // 11. Top Entities
    const entMap = {};
    articles.forEach(a=>{
      const entities = Array.isArray(a.entities) ? a.entities : (typeof a.entities === 'string' ? JSON.parse(a.entities||'[]') : []);
      entities.forEach(e=>{ const name = typeof e==='string'?e:(e.name||e.text||''); if(name) entMap[name]=(entMap[name]||0)+1; });
    });
    const topEnts = Object.entries(entMap).sort((a,b)=>b[1]-a[1]).slice(0,10);
    new Chart(document.getElementById('entities'), {
      type: 'bar',
      data: { labels: topEnts.map(e=>e[0]), datasets: [{ data: topEnts.map(e=>e[1]), backgroundColor:'#1a56db' }] },
      options: { indexAxis:'y' }
    });

    // 12. Pos vs Neg trend
    new Chart(document.getElementById('posneg-trend'), {
      type: 'line',
      data: { labels: labels7, datasets: [
        { label:'Bullish', data: labels7.map(d=>days[d].pos), borderColor:'#059669', fill:true, backgroundColor:'rgba(5,150,105,0.1)' },
        { label:'Bearish', data: labels7.map(d=>days[d].neg), borderColor:'#dc2626', fill:true, backgroundColor:'rgba(220,38,38,0.1)' }
      ]}
    });

    // 13. Neutral ratio
    const neutralRatio = labels7.map(d => days[d].neu / ((days[d].pos+days[d].neg+days[d].neu)||1));
    new Chart(document.getElementById('neutral-ratio'), {
      type: 'line',
      data: { labels: labels7, datasets: [{ data: neutralRatio, borderColor:'#d97706' }] },
      options: { scales:{y:{min:0,max:1}} }
    });

    // 14. Volatility
    const scores = articles.map(a=> a.sentiment==='positive'?1:(a.sentiment==='negative'?-1:0));
    const vols=[];
    for(let i=2;i<scores.length;i+=3){
      const slice=scores.slice(i-2,i+1);
      const avg=slice.reduce((a,b)=>a+b,0)/slice.length;
      const variance=slice.reduce((a,b)=>a+(b-avg)**2,0)/slice.length;
      vols.push(Math.sqrt(variance));
    }
    new Chart(document.getElementById('volatility'), {
      type: 'line',
      data: { labels: vols.map((_,i)=>'Day '+(i+1)), datasets: [{ data: vols, borderColor:'#6b7280' }] }
    });

    // 15. Recent feed
    const feedDiv = document.getElementById('recent-feed');
    if(feedDiv){
      const recent5 = articles.slice(0,5);
      feedDiv.innerHTML = recent5.map(a=>`
        <div style="display:flex;justify-content:space-between;padding:0.25rem 0;border-bottom:1px solid var(--border);">
          <span style="max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${a.title_en||a.title}</span>
          <span style="color:${a.sentiment==='positive'?'#059669':(a.sentiment==='negative'?'#dc2626':'#d97706')};font-weight:bold;">${a.sentiment}</span>
        </div>
      `).join('');
    }

    // 16. Title length vs sentiment (scatter)
    const scatterData = articles.map(a => ({
      x: (a.title_en||a.title||'').length,
      y: a.sentiment==='positive'?1:(a.sentiment==='negative'?-1:0),
      sentiment: a.sentiment
    }));
    new Chart(document.getElementById('length-sentiment'), {
      type: 'scatter',
      data: { datasets: [{
        label: 'Title Length vs Sentiment',
        data: scatterData,
        backgroundColor: scatterData.map(d=> d.sentiment==='positive'?'#059669':(d.sentiment==='negative'?'#dc2626':'#d97706'))
      }] },
      options: { scales:{x:{title:{display:true,text:'Title Length'}},y:{title:{display:true,text:'Sentiment (-1 Bearish, 0 Neutral, 1 Bullish)'}}} }
    });

    // 17. Hourly sentiment heatmap table
    const table = document.getElementById('heatmap-table');
    if(table){
      const hourSent = Array.from({length:24},()=>({pos:0,neg:0,neu:0}));
      articles.forEach(a=>{ const h=new Date(a.timestamp).getHours(); if(a.sentiment==='positive')hourSent[h].pos++; else if(a.sentiment==='negative')hourSent[h].neg++; else hourSent[h].neu++; });
      let html = '<tr><th>Hour</th><th>Bullish</th><th>Bearish</th><th>Neutral</th></tr>';
      hourSent.forEach((v,i)=>{ html += `<tr><td>${i}:00</td><td style="color:#059669">${v.pos}</td><td style="color:#dc2626">${v.neg}</td><td style="color:#d97706">${v.neu}</td></tr>`; });
      table.innerHTML = html;
    }
  }

  // Start polling for articles
  initWhenReady();
})();
