let trendChart = null;
let elasticityChart = null;

document.addEventListener('DOMContentLoaded', () => {
  initDashboard();
});

async function initDashboard() {
  await Promise.all([
    loadIndexMetrics(),
    loadTrendChart(),
    loadElasticityChart(),
    loadQuotes()
  ]);
}

// 1. Fetch & Render KPI Cards
async function loadIndexMetrics() {
  try {
    const res = await fetch('/api/index');
    const data = await res.json();
    if (data.status === 'success' && data.index) {
      const idx = data.index;
      document.getElementById('kpi-headline').textContent = Number(idx.headline).toFixed(2);
      document.getElementById('kpi-t1').textContent = Number(idx.apix_t1).toFixed(2);
      document.getElementById('kpi-t30').textContent = Number(idx.apix_t30).toFixed(2);
      document.getElementById('kpi-sample').textContent = idx.sample_size || '0';
    }
  } catch (err) {
    console.error('Failed to load index metrics:', err);
  }
}

// 2. Fetch & Render Historical APIx Trend Line Chart
async function loadTrendChart() {
  try {
    const res = await fetch('/api/history?limit=14');
    const data = await res.json();
    const history = data.history || [];

    const labels = history.map(item => item.calc_date.slice(5)); // MM-DD
    const headlineVals = history.map(item => item.headline_apix);
    const t1Vals = history.map(item => item.apix_t1);
    const t7Vals = history.map(item => item.apix_t7);
    const t30Vals = history.map(item => item.apix_t30);

    const ctx = document.getElementById('trendChart').getContext('2d');
    if (trendChart) trendChart.destroy();

    trendChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Headline APIx (Composite)',
            data: headlineVals,
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6, 182, 212, 0.1)',
            borderWidth: 3,
            tension: 0.3,
            fill: true
          },
          {
            label: 'T+1 (Emergency)',
            data: t1Vals,
            borderColor: '#ef4444',
            borderDash: [5, 5],
            borderWidth: 1.5,
            tension: 0.3
          },
          {
            label: 'T+7 (1 Week)',
            data: t7Vals,
            borderColor: '#f59e0b',
            borderWidth: 1.5,
            tension: 0.3
          },
          {
            label: 'T+30 (Leisure)',
            data: t30Vals,
            borderColor: '#10b981',
            borderWidth: 1.5,
            tension: 0.3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: '#94a3b8', boxWidth: 12, font: { size: 11 } }
          }
        },
        scales: {
          x: {
            grid: { color: 'rgba(51, 65, 85, 0.4)' },
            ticks: { color: '#94a3b8' }
          },
          y: {
            grid: { color: 'rgba(51, 65, 85, 0.4)' },
            ticks: { color: '#94a3b8' }
          }
        }
      }
    });
  } catch (err) {
    console.error('Failed to load trend chart:', err);
  }
}

// 3. Fetch & Render Lead-Time Price Elasticity Chart
async function loadElasticityChart() {
  try {
    const res = await fetch('/api/elasticity');
    const data = await res.json();
    const curve = data.curve || [];

    const labels = curve.map(c => c.window);
    const indexVals = curve.map(c => c.index);

    const ctx = document.getElementById('elasticityChart').getContext('2d');
    if (elasticityChart) elasticityChart.destroy();

    elasticityChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Advance Window Price Index',
          data: indexVals,
          backgroundColor: [
            'rgba(239, 68, 68, 0.85)',   // T+1
            'rgba(245, 158, 11, 0.85)',  // T+7
            'rgba(59, 130, 246, 0.85)',  // T+15
            'rgba(16, 185, 129, 0.85)',  // T+30
            'rgba(6, 182, 212, 0.85)'    // T+45
          ],
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#94a3b8', font: { size: 11 } }
          },
          y: {
            min: 80,
            grid: { color: 'rgba(51, 65, 85, 0.4)' },
            ticks: { color: '#94a3b8' }
          }
        }
      }
    });
  } catch (err) {
    console.error('Failed to load elasticity chart:', err);
  }
}

// 4. Fetch & Populate Airfare Quotes Table
async function loadQuotes() {
  const tbody = document.getElementById('quotes-tbody');
  try {
    const res = await fetch('/api/quotes?limit=25');
    const data = await res.json();
    const quotes = data.quotes || [];

    if (quotes.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center" style="color: #94a3b8;">No quotes recorded yet. Click "Scrape Fares As Needed" above to collect live fares!</td></tr>`;
      return;
    }

    tbody.innerHTML = quotes.map(q => `
      <tr>
        <td><strong>${q.carrier}</strong></td>
        <td><code>${q.flight_number}</code></td>
        <td>${q.route_code}</td>
        <td>${q.departure_date}</td>
        <td><span class="badge">T+${q.advance_days}</span></td>
        <td>₹${Number(q.base_fare).toLocaleString('en-IN')}</td>
        <td>₹${Number(q.udf_charges).toLocaleString('en-IN')}</td>
        <td>₹${Number(q.taxes_fees).toLocaleString('en-IN')}</td>
        <td><strong>₹${Number(q.total_fare).toLocaleString('en-IN')}</strong></td>
        <td style="color: #94a3b8; font-size: 0.78rem;">${(q.scraped_at || '').slice(11, 19) || 'Just now'}</td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="10" class="text-center text-red">Failed to load quotes.</td></tr>`;
  }
}

// 5. On-Demand Scrape Action Trigger
async function triggerScrape() {
  const routeCode = document.getElementById('route-select').value;
  const advanceDays = parseInt(document.getElementById('window-select').value, 10);
  const btn = document.getElementById('btn-scrape');
  const scrapeIcon = document.getElementById('scrape-icon');
  const scrapeText = document.getElementById('scrape-text');
  const feedback = document.getElementById('scrape-feedback');

  // Loading State
  btn.disabled = true;
  scrapeIcon.textContent = '⏳';
  scrapeText.textContent = 'Scraping portals...';
  feedback.classList.remove('hidden');
  feedback.textContent = `Connecting to airline endpoints for ${routeCode} (T+${advanceDays})...`;

  try {
    const res = await fetch('/api/scrape', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ route_code: routeCode, advance_days: advanceDays })
    });

    const data = await res.json();
    if (data.status === 'success') {
      feedback.textContent = `✅ Successfully extracted and unbundled ${data.scraped_count} airline quotes for ${routeCode}! Laspeyres APIx updated to ${Number(data.updated_index.headline).toFixed(2)}.`;
      // Refresh dashboard components
      await Promise.all([
        loadIndexMetrics(),
        loadTrendChart(),
        loadElasticityChart(),
        loadQuotes()
      ]);
    } else {
      feedback.textContent = `❌ Error during scraping: ${data.message || 'Unknown error'}`;
    }
  } catch (err) {
    feedback.textContent = `❌ Scraping request failed: ${err.message}`;
  } finally {
    btn.disabled = false;
    scrapeIcon.textContent = '🔍';
    scrapeText.textContent = 'Scrape Fares As Needed';
  }
}
