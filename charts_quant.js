// Highcharts quantitative analytics – 24 charts + social + candlestick volume
(function () {
  'use strict';

  const DARK_BG   = '#1e222d';
  const GRID      = '#2a2e39';
  const TEXT2     = '#787b86';
  const GREEN     = '#22c55e';
  const RED       = '#ef4444';
  const YELLOW    = '#f59e0b';
  const BLUE      = '#2962ff';
  const PURPLE    = '#7c3aed';

  let allCharts = [];
  const sentScore = a => a.sentiment === 'positive' ? 1 : a.sentiment === 'negative' ? -1 : 0;
  const sColor    = s => s === 'positive' ? GREEN : s === 'negative' ? RED : YELLOW;

  function destroyAll() {
    allCharts.forEach(c => { try { c.destroy(); } catch (e) {} });
    allCharts = [];
  }

  function mkCard(panel, title, fullWidth) {
    const card = document.createElement('div');
    card.className = 'quant-card' + (fullWidth ? ' full-width' : '');
    const header = document.createElement('div');
    header.className = 'card-header';
    header.innerHTML = `<span class="card-title">${title}</span>`;
    card.appendChild(header);
    const chartDiv = document.createElement('div');
    chartDiv.className = 'hc-chart' + (fullWidth ? ' tall' : '');
    card.appendChild(chartDiv);
    panel.appendChild(card);
    return { card, chartDiv };
  }

  function addSMA(chartObj, dataArr) {
    const sma = (period) => dataArr.map((_, i) => {
      if (i < period-1) return null;
      const slice = dataArr.slice(i-period+1, i+1);
      return slice.reduce((a,b)=>a+b,0)/period;
    });
    chartObj.addSeries({ name: 'SMA5', data: sma(5), type: 'line', color: YELLOW, lineWidth: 1, marker: { enabled: false }, enableMouseTracking: false }, false);
    chartObj.addSeries({ name: 'SMA20', data: sma(20), type: 'line', color: RED, lineWidth: 1, marker: { enabled: false }, enableMouseTracking: false }, false);
  }

  function addIndicatorToggle(card, chartObj, dataArr) {
    const header = card.querySelector('.card-header');
    if (!header) return;
    const toggleDiv = document.createElement('div');
    toggleDiv.className = 'indicator-toggles';
    const createCb = (period) => {
      const lbl = document.createElement('label');
      lbl.innerHTML = `<input type="checkbox"> SMA(${period})`;
      const cb = lbl.querySelector('input');
      cb.addEventListener('change', () => {
        if (cb.checked) {
          const sma = dataArr.map((_, i) => {
            if (i < period-1) return null;
            const slice = dataArr.slice(i-period+1, i+1);
            return slice.reduce((a,b)=>a+b,0)/period;
          });
          chartObj.addSeries({
            name: 'SMA('+period+')', data: sma, type: 'line',
            color: period===5 ? YELLOW : RED, lineWidth: 1,
            marker: { enabled: false }, enableMouseTracking: false
          });
        } else {
          const s = chartObj.series.find(s => s.name === 'SMA('+period+')');
          if (s) s.remove(false);
        }
        chartObj.redraw();
      });
      toggleDiv.appendChild(lbl);
    };
    createCb(5);
    createCb(20);
    header.appendChild(toggleDiv);
  }

  function buildAnalytics(articles, candleInterval) {
    const panel = document.getElementById('quant-panel');
    if (!panel) return;
    destroyAll();
    panel.innerHTML = '';

    // ═══ CANDLESTICK VOLUME CHART (full width) ═══
    {
      const intervalMs = {
        '1m': 60_000, '5m': 300_000, '15m': 900_000, '1h': 3_600_000,
        '4h': 14_400_000, '12h': 43_200_000, '1d': 86_400_000,
        '7d': 604_800_000, '14d': 1_209_600_000, '1mo': 2_592_000_000
      }[candleInterval] || 300_000;

      const buckets = {};
      articles.forEach(a => {
        if (!a.timestamp) return;
        const ts = new Date(a.timestamp).getTime();
        const key = Math.floor(ts / intervalMs) * intervalMs;
        buckets[key] = (buckets[key] || 0) + 1;
      });

      const sortedKeys = Object.keys(buckets).map(Number).sort((a,b) => a - b);
      const labels = sortedKeys.map(k => {
        const d = new Date(k);
        if (candleInterval === '1mo') return d.toLocaleDateString('en-US', {month:'short', year:'2-digit'});
        if (candleInterval === '7d' || candleInterval === '14d') return d.toLocaleDateString('en-US', {month:'short', day:'numeric'});
        if (candleInterval === '1d') return d.toLocaleDateString('en-US', {month:'short', day:'numeric'});
        return d.toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit'});
      });
      const data = sortedKeys.map(k => buckets[k]);

      const { card, chartDiv } = mkCard(panel, 'Article Volume Candlesticks', true);
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: labels, crosshair: true },
        yAxis: { title: { text: null }, min: 0 },
        series: [{
          name: 'Articles',
          data: data,
          color: BLUE,
          borderWidth: 0
        }],
        plotOptions: { column: { borderRadius: 2 } },
        tooltip: { pointFormat: '{point.y} articles' }
      });
      allCharts.push(chartObj);
      addIndicatorToggle(card, chartObj, data);
    }

    // ═══ Daily bucketing for time‑series charts ═══
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
      const { card, chartDiv } = mkCard(panel, 'Daily Volume');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Articles', data: dailyVol, color: BLUE, borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 2 } }
      });
      allCharts.push(chartObj);
      addIndicatorToggle(card, chartObj, dailyVol);
    }

    // B2. Hourly Activity
    {
      const hours = new Array(24).fill(0);
      articles.forEach(a => { if (a.timestamp) hours[new Date(a.timestamp).getHours()]++; });
      const { card, chartDiv } = mkCard(panel, 'Hourly Activity');
      const labels = Array.from({length:24}, (_,i) => i+'h');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: labels },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Articles', data: hours, color: BLUE, borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 2 } }
      });
      allCharts.push(chartObj);
    }

    // B3. Weekday Activity
    {
      const dow = new Array(7).fill(0);
      articles.forEach(a => { if (a.timestamp) dow[new Date(a.timestamp).getDay()]++; });
      const { card, chartDiv } = mkCard(panel, 'Weekday Activity');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'] },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Articles', data: dow, color: BLUE, borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 5 } }
      });
      allCharts.push(chartObj);
    }

    // B4. Source × Sentiment stacked
    {
      const srcs = [...new Set(articles.map(a => a.source).filter(Boolean))].slice(0,8);
      const { card, chartDiv } = mkCard(panel, 'Source × Sentiment');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: srcs },
        yAxis: { title: { text: null }, min: 0, stackLabels: { enabled: false } },
        plotOptions: { column: { stacking: 'normal' } },
        series: [
          { name: 'Positive', data: srcs.map(s => articles.filter(a => a.source===s && a.sentiment==='positive').length), color: GREEN },
          { name: 'Negative', data: srcs.map(s => articles.filter(a => a.source===s && a.sentiment==='negative').length), color: RED },
          { name: 'Neutral',  data: srcs.map(s => articles.filter(a => a.source===s && a.sentiment==='neutral').length),  color: YELLOW },
        ]
      });
      allCharts.push(chartObj);
    }

    // B5. Silence Detection
    {
      const hourMap = {};
      articles.forEach(a => {
        if (!a.timestamp) return;
        const key = new Date(a.timestamp).toISOString().slice(0, 13);
        hourMap[key] = (hourMap[key] || 0) + 1;
      });
      const now = new Date();
      const last48 = [], last48L = [];
      for (let i = 47; i >= 0; i--) {
        const d = new Date(now - i * 3600000);
        const key = d.toISOString().slice(0, 13);
        last48.push(hourMap[key] || 0);
        last48L.push(d.getHours()+'h');
      }
      const { card, chartDiv } = mkCard(panel, 'Silence Detection · 48h');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: last48L, tickInterval: 4 },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Articles', data: last48, colorByPoint: true,
          colors: last48.map(v => v===0 ? RED : GREEN), borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 2 } }
      });
      allCharts.push(chartObj);
    }

    // C1. Sentiment Volatility
    {
      const dailyAvg = days.map(d => { const arr = byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const rollStd = dailyAvg.map((_, i) => {
        if (i < 4) return null;
        const sl = dailyAvg.slice(i-4, i+1), mean = sl.reduce((a,b)=>a+b,0)/5;
        return +Math.sqrt(sl.reduce((a,b)=>a+(b-mean)**2,0)/5).toFixed(3);
      });
      const { card, chartDiv } = mkCard(panel, 'Sentiment Volatility · 5d STD');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'line' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Volatility', data: rollStd, color: PURPLE, lineWidth: 1.5, marker: { radius: 2 } }],
        plotOptions: { line: { connectNulls: true } }
      });
      allCharts.push(chartObj);
      addIndicatorToggle(card, chartObj, rollStd.filter(v=>v!==null));
    }

    // C2. Sentiment Momentum
    {
      const posRatio = days.map(d => byDay[d].filter(a=>a.sentiment==='positive').length / byDay[d].length);
      const mom = posRatio.map((v,i) => i===0 ? 0 : +(v-posRatio[i-1]).toFixed(3));
      const { card, chartDiv } = mkCard(panel, 'Sentiment Momentum');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null } },
        series: [{ name: 'Momentum', data: mom, colorByPoint: true,
          colors: mom.map(v => v>=0 ? GREEN : RED), borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 3 } }
      });
      allCharts.push(chartObj);
    }

    // C3. Panic Index
    {
      const neg = articles.filter(a=>a.sentiment==='negative').length;
      const pct = articles.length ? Math.round(neg/articles.length*100) : 0;
      const col = pct>=60 ? RED : pct>=40 ? YELLOW : GREEN;
      const { card, chartDiv } = mkCard(panel, 'Panic Index');
      // Custom HTML inside card
      const numDiv = document.createElement('div');
      numDiv.style.cssText = `text-align:center;padding:8px 0 2px;font-family:'JetBrains Mono',monospace;font-size:38px;font-weight:500;color:${col};line-height:1;`;
      numDiv.textContent = pct+'%';
      card.appendChild(numDiv);
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'pie', height: 65 },
        title: { text: undefined },
        plotOptions: { pie: { startAngle: -90, endAngle: 90, center: ['50%','100%'], size: '100%', dataLabels: { enabled: false } } },
        series: [{ name: 'Panic', data: [{name:'Neg',y:pct,color:col},{name:'Rest',y:100-pct,color:'#3a3f4e'}], innerSize: '65%' }]
      });
      allCharts.push(chartObj);
    }

    // C4. Sentiment Velocity scatter
    {
      const pts = articles.filter(a=>a.timestamp).map(a => [new Date(a.timestamp).getHours(), sentScore(a)]);
      const { card, chartDiv } = mkCard(panel, 'Sentiment Velocity · Hour vs Score');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'scatter' },
        title: { text: undefined },
        xAxis: { title: { text: null }, min: 0, max: 23 },
        yAxis: { title: { text: null }, min: -1.5, max: 1.5 },
        series: [{ name: 'Velocity', data: pts, color: 'rgba(41,98,255,0.4)', marker: { radius: 3 } }]
      });
      allCharts.push(chartObj);
    }

    // C5. Category Volatility radar
    {
      const cats = [...new Set(articles.map(a=>a.category).filter(Boolean))].slice(0,8);
      const catStd = cats.map(cat => {
        const arr = articles.filter(a=>a.category===cat).map(sentScore);
        if (arr.length < 2) return 0;
        const mean = arr.reduce((a,b)=>a+b,0)/arr.length;
        return +Math.sqrt(arr.reduce((a,b)=>a+(b-mean)**2,0)/arr.length).toFixed(3);
      });
      const { card, chartDiv } = mkCard(panel, 'Category Volatility · STD');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { polar: true, type: 'line' },
        title: { text: undefined },
        xAxis: { categories: cats, tickmarkPlacement: 'on', lineWidth: 0 },
        yAxis: { gridLineInterpolation: 'polygon', min: 0 },
        series: [{ name: 'Volatility', data: catStd, color: BLUE, pointPlacement: 'on' }]
      });
      allCharts.push(chartObj);
    }

    // C6. Intraday Swing
    {
      const highs = days.map(d=>Math.max(...byDay[d].map(sentScore)));
      const lows  = days.map(d=>Math.min(...byDay[d].map(sentScore)));
      const close = days.map(d=>sentScore(byDay[d][byDay[d].length-1]));
      const { card, chartDiv } = mkCard(panel, 'Intraday Swing');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'line' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null }, min: -1.5, max: 1.5 },
        series: [
          { name: 'High',  data: highs, color: GREEN, lineWidth: 1.5, marker: { radius: 1 } },
          { name: 'Low',   data: lows,  color: RED,   lineWidth: 1.5, marker: { radius: 1 } },
          { name: 'Close', data: close, color: BLUE,  lineWidth: 2,   marker: { radius: 2 }, dashStyle: 'Dash' }
        ]
      });
      allCharts.push(chartObj);
    }

    // D1. Entity Type Distribution
    {
      const typeCounts = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.forEach(e => { const t = (e.type || 'OTHER').toUpperCase(); typeCounts[t] = (typeCounts[t]||0)+1; });
      });
      const types = Object.keys(typeCounts);
      const pieData = types.map(t => ({ name: t, y: typeCounts[t] }));
      const { card, chartDiv } = mkCard(panel, 'Entity Type Distribution');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'pie' },
        title: { text: undefined },
        plotOptions: { pie: { innerSize: '60%', dataLabels: { distance: -20, style: { color: TEXT2, fontSize: '8px' } } } },
        series: [{ name: 'Entities', data: pieData, colors: [BLUE,GREEN,PURPLE,YELLOW,RED,'#0891b2','#be185d','#0f766e'] }]
      });
      allCharts.push(chartObj);
    }

    // D2. Top Persons
    {
      const counts = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.filter(e=>e.type==='PERSON').forEach(e => { counts[e.name] = (counts[e.name]||0)+1; });
      });
      const top = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8);
      const { card, chartDiv } = mkCard(panel, 'Top Persons Mentioned');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'bar' },
        title: { text: undefined },
        xAxis: { categories: top.map(t=>t[0]) },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Mentions', data: top.map(t=>t[1]), color: BLUE, borderWidth: 0 }]
      });
      allCharts.push(chartObj);
    }

    // D3. Top Organizations
    {
      const counts = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.filter(e=>e.type==='ORGANIZATION').forEach(e => { counts[e.name] = (counts[e.name]||0)+1; });
      });
      const top = Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8);
      const { card, chartDiv } = mkCard(panel, 'Top Organizations');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'bar' },
        title: { text: undefined },
        xAxis: { categories: top.map(t=>t[0]) },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Mentions', data: top.map(t=>t[1]), color: PURPLE, borderWidth: 0 }]
      });
      allCharts.push(chartObj);
    }

    // D4. Entity Co‑occurrence
    {
      const pairs = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        const names = [...new Set(ents.map(e=>e.name).filter(Boolean))].slice(0,5);
        for (let i=0;i<names.length;i++) for(let j=i+1;j<names.length;j++) {
          const key = [names[i],names[j]].sort().join(' + ');
          pairs[key] = (pairs[key]||0)+1;
        }
      });
      const top = Object.entries(pairs).sort((a,b)=>b[1]-a[1]).slice(0,8);
      const { card, chartDiv } = mkCard(panel, 'Entity Co‑occurrence');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'bar' },
        title: { text: undefined },
        xAxis: { categories: top.map(t=>t[0]) },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Pairs', data: top.map(t=>t[1]), color: '#0891b2', borderWidth: 0 }]
      });
      allCharts.push(chartObj);
    }

    // D5. Entity Sentiment Breakdown
    {
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
      const top = Object.entries(entSent).sort((a,b)=>b[1].total-a[1].total).slice(0,8);
      const { card, chartDiv } = mkCard(panel, 'Entity Sentiment Breakdown');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: top.map(t=>t[0]) },
        yAxis: { title: { text: null }, min: 0 },
        plotOptions: { column: { stacking: 'normal' } },
        series: [
          { name: 'Pos', data: top.map(t=>t[1].pos), color: GREEN },
          { name: 'Neg', data: top.map(t=>t[1].neg), color: RED },
          { name: 'Neu', data: top.map(t=>t[1].neu), color: YELLOW }
        ]
      });
      allCharts.push(chartObj);
    }

    // E1. Sentiment Z‑Score
    {
      const dailyAvg = days.map(d => { const arr = byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const mean = dailyAvg.reduce((a,b)=>a+b,0)/dailyAvg.length;
      const std = Math.sqrt(dailyAvg.reduce((a,b)=>a+(b-mean)**2,0)/dailyAvg.length) || 1;
      const zScores = dailyAvg.map(v => +((v-mean)/std).toFixed(2));
      const { card, chartDiv } = mkCard(panel, 'Sentiment Z‑Score');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null } },
        series: [{ name: 'Z‑Score', data: zScores, colorByPoint: true,
          colors: zScores.map(v => v>=0 ? GREEN : RED), borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 3 } }
      });
      allCharts.push(chartObj);
    }

    // E2. Category Correlation
    {
      const cats = [...new Set(articles.map(a=>a.category).filter(Boolean))].slice(0,8);
      const pctPos = cats.map(c => {
        const sub = articles.filter(a=>a.category===c);
        return sub.length ? Math.round(sub.filter(a=>a.sentiment==='positive').length/sub.length*100) : 0;
      });
      const { card, chartDiv } = mkCard(panel, 'Category Correlation');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: cats },
        yAxis: { title: { text: null }, min: 0, max: 100 },
        series: [{ name: '% Positive', data: pctPos, colorByPoint: true,
          colors: pctPos.map(v => v>=50 ? GREEN : RED), borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 4 } }
      });
      allCharts.push(chartObj);
    }

    // E3. Bull/Bear Acceleration
    {
      const posR = days.map(d => byDay[d].filter(a=>a.sentiment==='positive').length/byDay[d].length);
      const mom = posR.map((v,i) => i===0 ? 0 : v-posR[i-1]);
      const accel = mom.map((v,i) => i===0 ? 0 : +(v-mom[i-1]).toFixed(3));
      const { card, chartDiv } = mkCard(panel, 'Bull/Bear Acceleration');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null } },
        series: [{ name: 'Accel', data: accel, colorByPoint: true,
          colors: accel.map(v => v>=0 ? GREEN : RED), borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 3 } }
      });
      allCharts.push(chartObj);
    }

    // E4. Sentiment Velocity · Hourly
    {
      const byHour = {};
      articles.forEach(a => { if (!a.timestamp) return; const h=new Date(a.timestamp).getHours(); if(!byHour[h]) byHour[h]=[]; byHour[h].push(sentScore(a)); });
      const hourAvg = Array.from({length:24}, (_,i) => { const arr=byHour[i]||[]; return arr.length ? +(arr.reduce((a,b)=>a+b,0)/arr.length).toFixed(2) : null; });
      const { card, chartDiv } = mkCard(panel, 'Sentiment Velocity · Hourly');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'line' },
        title: { text: undefined },
        xAxis: { categories: Array.from({length:24},(_,i)=>i+'h') },
        yAxis: { title: { text: null }, min: -1, max: 1 },
        series: [{ name: 'Avg Score', data: hourAvg, color: '#0891b2', lineWidth: 1.5, marker: { radius: 2 } }],
        plotOptions: { line: { connectNulls: true } }
      });
      allCharts.push(chartObj);
      addIndicatorToggle(card, chartObj, hourAvg.filter(v=>v!==null));
    }

    // E5. Cumulative Net Sentiment
    {
      let cum = 0;
      const cumArr = days.map(d => { cum += byDay[d].reduce((s,a)=>s+sentScore(a),0); return cum; });
      const col = cumArr[cumArr.length-1] >= 0 ? GREEN : RED;
      const { card, chartDiv } = mkCard(panel, 'Cumulative Net Sentiment');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'area' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null } },
        series: [{ name: 'Cumulative', data: cumArr, color: col, fillOpacity: 0.15, lineWidth: 2, marker: { radius: 1.5 } }]
      });
      allCharts.push(chartObj);
      addIndicatorToggle(card, chartObj, cumArr);
    }

    // E6. Daily Volatility
    {
      const swing = days.map(d => { const arr=byDay[d].map(sentScore); return +(Math.max(...arr)-Math.min(...arr)).toFixed(2); });
      const { card, chartDiv } = mkCard(panel, 'Daily Volatility');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Swing', data: swing, color: PURPLE, borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 3 } }
      });
      allCharts.push(chartObj);
    }

    // E7. SMA Crossover
    {
      const dailyAvg = days.map(d => { const arr=byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const sma = n => dailyAvg.map((_,i) => i<n-1 ? null : +(dailyAvg.slice(i-n+1,i+1).reduce((a,b)=>a+b,0)/n).toFixed(3));
      const { card, chartDiv } = mkCard(panel, 'SMA Crossover · 3d vs 7d');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'line' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null } },
        series: [
          { name: 'SMA3', data: sma(3), color: BLUE,   lineWidth: 2,   marker: { radius: 1.5 }, connectNulls: true },
          { name: 'SMA7', data: sma(7), color: YELLOW, lineWidth: 1.5, marker: { radius: 1.5 }, dashStyle: 'Dash', connectNulls: true }
        ]
      });
      allCharts.push(chartObj);
    }

    // E8. Intraday Sentiment Swing · 4h
    {
      const blocks = ['0–4h','4–8h','8–12h','12–16h','16–20h','20–24h'];
      const bData = blocks.map((_,i) => {
        const arr = articles.filter(a => { if(!a.timestamp) return false; const h=new Date(a.timestamp).getHours(); return h>=i*4 && h<(i+1)*4; }).map(sentScore);
        return arr.length ? +(arr.reduce((a,b)=>a+b,0)/arr.length).toFixed(2) : 0;
      });
      const { card, chartDiv } = mkCard(panel, 'Intraday Sentiment Swing · 4h');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: blocks },
        yAxis: { title: { text: null }, min: -1, max: 1 },
        series: [{ name: 'Swing', data: bData, colorByPoint: true,
          colors: bData.map(v => v>=0 ? GREEN : RED), borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 4 } }
      });
      allCharts.push(chartObj);
    }

    // F1. Flashpoint Detection
    {
      const dailyVol = days.map(d => byDay[d].length);
      const meanVol = dailyVol.reduce((a,b)=>a+b,0)/dailyVol.length;
      const stdVol = Math.sqrt(dailyVol.reduce((a,b)=>a+(b-meanVol)**2,0)/dailyVol.length) || 1;
      const zVol = dailyVol.map(v => +((v-meanVol)/stdVol).toFixed(2));
      const { card, chartDiv } = mkCard(panel, 'Flashpoint Detection');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null } },
        series: [{ name: 'Z‑Score', data: zVol, colorByPoint: true,
          colors: zVol.map(v => v>=2 ? RED : v>=1 ? YELLOW : BLUE), borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 4 } }
      });
      allCharts.push(chartObj);
    }

    // F2. Polarization Index
    {
      const bins = [-1.0,-0.8,-0.6,-0.4,-0.2,0,0.2,0.4,0.6,0.8,1.0];
      const hist = bins.map((b,i) => { const next=bins[i+1]||1.1; return articles.filter(a=>sentScore(a)>=b&&sentScore(a)<next).length; });
      const { card, chartDiv } = mkCard(panel, 'Polarization Index');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: bins.map(b=>b.toFixed(1)) },
        yAxis: { title: { text: null } },
        series: [{ name: 'Distribution', data: hist, colorByPoint: true,
          colors: hist.map((_,i) => i<5 ? RED : GREEN), borderWidth: 0 }],
        plotOptions: { column: { borderRadius: 3, pointPadding: 0, groupPadding: 0 } }
      });
      allCharts.push(chartObj);
    }

    // F3. Source Bias Matrix (scatter)
    {
      const sources = [...new Set(articles.map(a=>a.source))].slice(0,10);
      const data = sources.map(src => {
        const arts = articles.filter(a=>a.source===src);
        const avgSent = arts.length ? arts.reduce((s,a)=>s+sentScore(a),0)/arts.length : 0;
        const subjectivity = arts.length ? arts.reduce((s,a) => {
          const txt = ((a.title_en||a.title||'')+' '+(a.summary||'')).toLowerCase();
          const opWords = /\b(think|believe|opinion|suggest|maybe|perhaps|likely|feel|seem)\b/g;
          return s + (txt.match(opWords)||[]).length;
        },0)/arts.length : 0;
        return { x: +avgSent.toFixed(3), y: +subjectivity.toFixed(2), name: src };
      });
      const { card, chartDiv } = mkCard(panel, 'Source Bias Matrix');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'scatter' },
        title: { text: undefined },
        xAxis: { title: { text: 'Avg Sentiment' } },
        yAxis: { title: { text: 'Subjectivity' } },
        series: [{ name: 'Sources', data: data.map(d => [d.x, d.y]),
          color: data.map(d => d.x>=0 ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.7)') }]
      });
      allCharts.push(chartObj);
    }

    // F4. Political Weight Bar
    {
      const entCount = {};
      articles.forEach(a => {
        const ents = a.entities ? (typeof a.entities === 'string' ? JSON.parse(a.entities) : a.entities) : [];
        ents.filter(e=>e.type==='PERSON').forEach(e => { entCount[e.name]=(entCount[e.name]||0)+1+Math.abs(sentScore(a))*2; });
      });
      const top = Object.entries(entCount).sort((a,b)=>b[1]-a[1]).slice(0,15);
      const { card, chartDiv } = mkCard(panel, 'Political Weight');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'bar' },
        title: { text: undefined },
        xAxis: { categories: top.map(t=>t[0]) },
        yAxis: { title: { text: null } },
        series: [{ name: 'Weight', data: top.map(t=>t[1]), color: BLUE, borderWidth: 0 }]
      });
      allCharts.push(chartObj);
    }

    // F5. Stability Index
    {
      const dailySent = days.map(d => { const arr=byDay[d].map(sentScore); return arr.reduce((a,b)=>a+b,0)/arr.length; });
      const volatility = +(Math.sqrt(dailySent.reduce((a,b)=>a+(b-0)**2,0)/dailySent.length)).toFixed(3);
      const avgVol = days.map(d=>byDay[d].length).reduce((a,b)=>a+b,0)/days.length;
      const stability = Math.max(0, Math.min(100, Math.round((1-volatility)*50+(avgVol>5?30:20))));
      const col = stability>=60 ? GREEN : stability>=40 ? YELLOW : RED;
      const { card, chartDiv } = mkCard(panel, 'Stability Index');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'pie', height: 145 },
        title: { text: undefined },
        plotOptions: { pie: { startAngle: -90, endAngle: 90, center: ['50%','100%'], size: '100%', dataLabels: { enabled: false } } },
        series: [{ name: 'Stability', data: [{name:'Stable',y:stability,color:col},{name:'Remaining',y:100-stability,color:'#3a3f4e'}], innerSize: '72%' }]
      });
      allCharts.push(chartObj);
    }

    // F6. Reach vs Impact Bubble
    {
      const reachMap = {};
      articles.forEach(a => { reachMap[a.source] = (reachMap[a.source]||0)+1; });
      const data = articles.slice(0,80).map(a => ({
        x: Math.abs(sentScore(a)), y: reachMap[a.source]||1,
        z: Math.min(15, 3+(a.breaking||1)*2), sentiment: sentScore(a)
      }));
      const { card, chartDiv } = mkCard(panel, 'Reach vs Impact');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'bubble' },
        title: { text: undefined },
        xAxis: { title: { text: 'Sentiment Intensity' } },
        yAxis: { title: { text: 'Source Reach' } },
        series: [{ name: 'Articles', data: data.map(d => [d.x, d.y, d.z]),
          color: data.map(d => d.sentiment>=0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)') }]
      });
      allCharts.push(chartObj);
    }

    // F7. Source Reliability
    {
      const srcs = [...new Set(articles.map(a=>a.source))].slice(0,8);
      const factWords = /\b(according|reported|confirmed|official|data|statistics|document|statement|announced|figure)\b/g;
      const opWords = /\b(think|believe|opinion|suggest|maybe|perhaps|likely|feel|seem)\b/g;
      const data = srcs.map(src => {
        const arts = articles.filter(a=>a.source===src);
        let fact=0, op=0;
        arts.forEach(a => {
          const txt = ((a.title_en||a.title||'')+' '+(a.summary||'')).toLowerCase();
          fact += (txt.match(factWords)||[]).length;
          op += (txt.match(opWords)||[]).length;
        });
        const total = fact+op||1;
        return { src, fact: +(fact/total*100).toFixed(1), op: +(op/total*100).toFixed(1) };
      });
      const { card, chartDiv } = mkCard(panel, 'Source Reliability');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: data.map(d=>d.src) },
        yAxis: { title: { text: null }, min: 0, max: 100 },
        plotOptions: { column: { stacking: 'normal' } },
        series: [
          { name: 'Fact',    data: data.map(d=>d.fact), color: BLUE },
          { name: 'Opinion', data: data.map(d=>d.op),   color: RED }
        ]
      });
      allCharts.push(chartObj);
    }

    // G1. Article Velocity 7‑Day
    {
      const dailyVol = days.map(d => byDay[d].length);
      const rolling = dailyVol.map((_,i) => i<6 ? null : dailyVol.slice(i-6,i+1).reduce((a,b)=>a+b,0)/7);
      const { card, chartDiv } = mkCard(panel, 'Article Velocity · 7‑Day Avg');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'line' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null }, min: 0 },
        series: [
          { name: 'Daily', data: dailyVol, color: 'rgba(255,255,255,0.15)', lineWidth: 1, marker: { enabled: false } },
          { name: '7D Avg', data: rolling, color: BLUE, lineWidth: 2.5, marker: { radius: 2 }, connectNulls: true }
        ]
      });
      allCharts.push(chartObj);
    }

    // G2. Sentiment Volatility Bands
    {
      const dailyAvg = days.map(d => { const scores=byDay[d].map(sentScore); return scores.length ? scores.reduce((a,b)=>a+b,0)/scores.length : 0; });
      const dailyStd = days.map((d,i) => {
        const scores = days.slice(Math.max(0,i-6),i+1).flatMap(dd=>byDay[dd].map(sentScore));
        return scores.length ? Math.sqrt(scores.reduce((a,b)=>a+(b)**2,0)/scores.length) : 0;
      });
      const upper = dailyAvg.map((v,i)=>v+2*dailyStd[i]);
      const lower = dailyAvg.map((v,i)=>v-2*dailyStd[i]);
      const { card, chartDiv } = mkCard(panel, 'Sentiment Volatility Bands');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'arearange' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null }, min: -1, max: 1 },
        series: [
          { name: 'Band', data: lower.map((v,i)=>[v, upper[i]]), color: 'rgba(41,98,255,0.08)', lineWidth: 0, marker: { enabled: false } },
          { name: 'Sentiment', type: 'line', data: dailyAvg, color: YELLOW, lineWidth: 2, marker: { radius: 2 } }
        ]
      });
      allCharts.push(chartObj);
    }

    // G3. Source Dominance Area
    {
      const topSources = Object.entries(
        articles.reduce((acc,a) => { const s=a.source||'unknown'; acc[s]=(acc[s]||0)+1; return acc; }, {})
      ).sort((a,b)=>b[1]-a[1]).slice(0,6).map(e=>e[0]);
      const colors = [BLUE, YELLOW, RED, GREEN, PURPLE, '#0891b2'];
      const byDaySource = {};
      days.forEach(d => { byDaySource[d] = {}; topSources.forEach(s => byDaySource[d][s]=0); });
      articles.forEach(a => {
        const d = a.timestamp && a.timestamp.slice(0,10);
        if (d && byDaySource[d]) byDaySource[d][a.source||'unknown'] = (byDaySource[d][a.source||'unknown']||0)+1;
      });
      const { card, chartDiv } = mkCard(panel, 'Source Dominance');
      const series = topSources.map((s,i) => ({
        name: s, data: days.map(d => byDaySource[d][s]||0), color: colors[i%6], borderWidth: 0
      }));
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'area' },
        title: { text: undefined },
        xAxis: { categories: shortLbls },
        yAxis: { title: { text: null }, min: 0 },
        plotOptions: { area: { stacking: 'normal', marker: { enabled: false } } },
        series: series
      });
      allCharts.push(chartObj);
    }

    // G4. Geographical Impact
    {
      const cityScore = {};
      articles.forEach(a => {
        const loc = (a.location && a.location.name) || 'Erbil';
        const intensity = Math.abs(sentScore(a));
        cityScore[loc] = (cityScore[loc]||0) + 1 + intensity*5;
      });
      const topCities = Object.entries(cityScore).sort((a,b)=>b[1]-a[1]).slice(0,10);
      const { card, chartDiv } = mkCard(panel, 'Geographical Impact');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'bar' },
        title: { text: undefined },
        xAxis: { categories: topCities.map(e=>e[0]) },
        yAxis: { title: { text: null } },
        series: [{ name: 'Weight', data: topCities.map(e=>e[1]), color: GREEN, borderWidth: 0 }]
      });
      allCharts.push(chartObj);
    }

    // G5. Thematic Sentiment Radar
    {
      const categories = [...new Set(articles.map(a=>a.category).filter(Boolean))].slice(0,10);
      const categorySent = categories.map(c => {
        const arts = articles.filter(a=>a.category===c);
        return arts.length ? arts.reduce((s,a)=>s+sentScore(a),0)/arts.length : 0;
      });
      const { card, chartDiv } = mkCard(panel, 'Thematic Sentiment');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { polar: true, type: 'line' },
        title: { text: undefined },
        xAxis: { categories: categories, tickmarkPlacement: 'on', lineWidth: 0 },
        yAxis: { gridLineInterpolation: 'polygon', min: -1, max: 1 },
        series: [{ name: 'Sentiment', data: categorySent, color: YELLOW, pointPlacement: 'on' }]
      });
      allCharts.push(chartObj);
    }
  }

  // ═══ buildSocialAnalytics – TikTok charts in Highcharts ═══
  function buildSocialAnalytics(articles) {
    const panel = document.getElementById('social-panel');
    if (!panel) return;
    panel.innerHTML = '';

    const tiktokArts = articles.filter(a => a.source && a.source.toLowerCase().includes('tiktok'));
    if (tiktokArts.length === 0) {
      const msg = document.createElement('div');
      msg.textContent = 'No TikTok data available for this period.';
      msg.style.cssText = 'grid-column:1/-1; text-align:center; padding:40px; color:var(--tv-text2);';
      panel.appendChild(msg);
      return;
    }

    function getAccounts() { return [...new Set(tiktokArts.map(a=>a.source))]; }

    // F1 – Posts per Period
    {
      const byDay = {};
      tiktokArts.forEach(a => { if (!a.timestamp) return; const d=a.timestamp.slice(0,10); byDay[d]=(byDay[d]||0)+1; });
      const days = Object.keys(byDay).sort();
      const vals = days.map(d=>byDay[d]);
      const lbls = days.map(d=>d.slice(5));
      const { card, chartDiv } = mkCard(panel, 'TikTok Posts per Period');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: lbls },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Posts', data: vals, color: '#fe2c55', borderWidth: 0 }]
      });
      allCharts.push(chartObj);
    }

    // F2 – Posting Frequency per Account
    {
      const accounts = getAccounts();
      const counts = accounts.map(acc => tiktokArts.filter(a=>a.source===acc).length);
      const { card, chartDiv } = mkCard(panel, 'Posting Frequency per Account');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'bar' },
        title: { text: undefined },
        xAxis: { categories: accounts },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Posts', data: counts, color: '#fe2c55', borderWidth: 0 }]
      });
      allCharts.push(chartObj);
    }

    // F3 – Propaganda Level (simulated)
    {
      const accounts = getAccounts();
      const vals = accounts.map(() => Math.floor(Math.random()*100));
      const { card, chartDiv } = mkCard(panel, 'Pro‑Kurdish Propaganda Level (simulated)');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'column' },
        title: { text: undefined },
        xAxis: { categories: accounts },
        yAxis: { title: { text: null }, min: 0, max: 100 },
        series: [{ name: 'Propaganda', data: vals, colorByPoint: true,
          colors: vals.map(v => v>60 ? GREEN : YELLOW), borderWidth: 0 }]
      });
      allCharts.push(chartObj);
      const note = document.createElement('div');
      note.textContent = '(simulated data)';
      note.style.cssText = 'font-size:9px;color:var(--tv-text2);margin-top:4px;';
      card.appendChild(note);
    }

    // F4 – Crime chart
    {
      const crimeArts = tiktokArts.filter(a => a.category==='security'||a.category==='crime');
      const byDay = {};
      crimeArts.forEach(a => { if (!a.timestamp) return; const d=a.timestamp.slice(0,10); byDay[d]=(byDay[d]||0)+1; });
      const days = Object.keys(byDay).sort();
      const vals = days.map(d=>byDay[d]);
      const { card, chartDiv } = mkCard(panel, 'Crime in Region (TikTok)');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'line' },
        title: { text: undefined },
        xAxis: { categories: days.map(d=>d.slice(5)) },
        yAxis: { title: { text: null }, min: 0 },
        series: [{ name: 'Crime', data: vals, color: RED, lineWidth: 1.5, marker: { radius: 2 } }]
      });
      allCharts.push(chartObj);
    }

    // F5 – Leaderboard (simulated)
    {
      const accounts = getAccounts();
      const delays = accounts.map(() => Math.floor(Math.random()*120+1));
      const { card, chartDiv } = mkCard(panel, 'Fastest Reporter · Avg Delay (simulated)');
      const chartObj = Highcharts.chart(chartDiv, {
        chart: { type: 'bar' },
        title: { text: undefined },
        xAxis: { categories: accounts },
        yAxis: { title: { text: 'minutes' } },
        series: [{ name: 'Delay', data: delays, colorByPoint: true,
          colors: delays.map(d => d<30 ? GREEN : YELLOW), borderWidth: 0 }]
      });
      allCharts.push(chartObj);
      const note = document.createElement('div');
      note.textContent = '(simulated – event_time field not yet in data)';
      note.style.cssText = 'font-size:9px;color:var(--tv-text2);margin-top:4px;';
      card.appendChild(note);
    }
  }

  window.buildAnalytics = buildAnalytics;
  window.buildSocialAnalytics = buildSocialAnalytics;
})();
