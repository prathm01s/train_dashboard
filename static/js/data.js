let skip = 0;
const limit = 100;
let charts = {};

async function fetchMetrics() {
    try {
        const response = await fetch('/api/ml_metrics');
        const metrics = await response.json();
        const tableBody = document.getElementById('metrics-table');
        tableBody.innerHTML = '';
        metrics.forEach(metric => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${metric.collection}</td>
                <td>${metric.final_loss.toFixed(4)}</td>
                <td>${metric.final_val_loss.toFixed(4)}</td>
                <td>${metric.threshold.toFixed(2)}</td>
                <td>${new Date(metric.timestamp).toLocaleString()}</td>
            `;
            tableBody.appendChild(row);
        });
    } catch (error) {
        console.error('Error fetching metrics:', error);
    }
}

async function fetchData() {
    try {
        const response = await fetch(`/api/all-data?skip=${skip}&limit=${limit}`);
        const data = await response.json();
        const tableBody = document.getElementById('data-table');
        data.forEach(item => {
            const row = document.createElement('tr');
            const isAnomaly = item.anomaly || false;
            row.innerHTML = `
                <td>${item.collection}</td>
                <td class="${isAnomaly ? 'anomaly-cell' : ''}">${item.value}</td>
                <td>${new Date(item.timestamp).toLocaleString()}</td>
                <td>${isAnomaly ? 'Yes' : 'No'}</td>
            `;
            tableBody.appendChild(row);
        });
        skip += limit;
        if (data.length < limit) document.getElementById('load-more-btn').style.display = 'none';
    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

async function plotSensorData(collection) {
    if (!collection) return;
    try {
        const response = await fetch(`/api/collection/${collection}`);
        const data = await response.json();
        const ctx = document.getElementById('sensorChart').getContext('2d');
        const labels = data.map(item => new Date(item.timestamp).toLocaleTimeString());
        const values = data.map(item => parseFloat(item.value) || 0);

        if (charts[collection]) charts[collection].destroy();

        charts[collection] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: collection,
                    data: values,
                    borderColor: '#d4a5a5',
                    backgroundColor: '#d4a5a540',
                    fill: true
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: { title: { display: true, text: 'Time' } },
                    y: { title: { display: true, text: 'Value' } }
                }
            }
        });
    } catch (error) {
        console.error('Error plotting data:', error);
    }
}

document.add