let chartInstance = null;
let allData = [];

async function fetchData() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        allData = data;
        populateTable(data);
        updateChart(data);
        updateTrain(data);
        checkAlerts(data);
    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

function populateTable(data) {
    const tableBody = document.getElementById('data-table');
    const noDataMessage = document.getElementById('no-data-message');
    tableBody.innerHTML = '';
    const deviceFilter = document.getElementById('device-filter').value;

    let filteredData = data;
    if (deviceFilter !== 'all') {
        filteredData = filteredData.filter(item => {
            const collection = item.collection;
            return (deviceFilter === 'trainESP' && collection.startsWith('train/')) ||
                   (deviceFilter === 'environmentESP' && collection.startsWith('env/'));
        });
    }

    filteredData = filteredData.slice(0, 20); // Limit to 20 records

    if (filteredData.length === 0) {
        noDataMessage.style.display = 'block';
        return;
    } else {
        noDataMessage.style.display = 'none';
    }

    filteredData.forEach((item, index) => {
        const row = document.createElement('tr');
        row.style.setProperty('--row-index', index);
        const isAnomaly = item.anomaly || false;
        row.innerHTML = `
            <td>${item.collection}</td>
            <td class="${isAnomaly ? 'anomaly-cell' : ''}">${item.value}</td>
            <td>${new Date(item.timestamp).toLocaleString()}</td>
            <td>${isAnomaly ? 'Yes' : 'No'}</td>
        `;
        tableBody.appendChild(row);
    });
}

function updateChart(data) {
    const ctx = document.getElementById('sensorChart').getContext('2d');
    const datasets = [
        { collection: 'train/accelero', label: 'Train Accelerometer', color: '#d4a5a5' },
        { collection: 'train/ultra1', label: 'Train Ultra1', color: '#b392ac' },
        { collection: 'train/ultra2', label: 'Train Ultra2', color: '#8e7b9b' },
        { collection: 'env/tof1', label: 'TOF1', color: '#6d8299' },
        { collection: 'env/tof2', label: 'TOF2', color: '#a3bffa' },
        { collection: 'env/tof1_pos1', label: 'TOF1 Pos1', color: '#4caf50' },
        { collection: 'env/tof1_pos2', label: 'TOF1 Pos2', color: '#ff9800' },
        { collection: 'env/tof1_pos3', label: 'TOF1 Pos3', color: '#9c27b0' },
        { collection: 'env/tof1_pos4', label: 'TOF1 Pos4', color: '#2196f3' },
        { collection: 'env/tof2_pos1', label: 'TOF2 Pos1', color: '#f44336' },
        { collection: 'env/tof2_pos2', label: 'TOF2 Pos2', color: '#ffeb3b' },
        { collection: 'env/tof2_pos3', label: 'TOF2 Pos3', color: '#795548' },
        { collection: 'env/tof2_pos4', label: 'TOF2 Pos4', color: '#607d8b' },
        { collection: 'env/dht', label: 'DHT', color: '#f4a261' },
        { collection: 'env/sw420', label: 'SW420', color: '#e76f51' },
        { collection: 'env/env_infra', label: 'Env Infra', color: '#2a9d8f' }
    ].map(sensor => ({
        label: sensor.label,
        data: data.filter(item => item.collection === sensor.collection).slice(0, 10).reverse().map(item => parseFloat(item.value) || 0),
        borderColor: sensor.color,
        backgroundColor: `${sensor.color}40`,
        fill: true,
        pointHoverRadius: 6,
    }));

    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.filter(item => item.collection === 'train/accelero').slice(0, 10).reverse().map(item => new Date(item.timestamp).toLocaleTimeString()),
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 1500, easing: 'easeInOutQuad' },
            scales: {
                x: { title: { display: true, text: 'Time', font: { family: 'Poppins', size: 12 } } },
                y: { title: { display: true, text: 'Value', font: { family: 'Poppins', size: 12 } }, beginAtZero: true }
            },
            plugins: {
                legend: {
                    labels: { font: { family: 'Poppins', size: 12 } },
                    onClick: (e, legendItem) => {
                        const dataset = chartInstance.data.datasets[legendItem.datasetIndex];
                        dataset.hidden = !dataset.hidden;
                        chartInstance.update();
                        chartInstance.canvas.style.transform = 'translateX(5px)';
                        setTimeout(() => { chartInstance.canvas.style.transform = 'translateX(0)'; }, 200);
                    }
                }
            }
        }
    });
}

function updateTrain(data) {
    const train = document.getElementById('train');
    const latestTrain = data.find(item => item.collection === 'train/accelero') || {};
    train.classList.remove('moving', 'alert');
    if (parseFloat(latestTrain.value) > 0) {
        train.classList.add('moving');
    }
}

function checkAlerts(data) {
    const latest = data[0] || {};
    const banner = document.getElementById('alert-banner');
    if (latest.collection === 'env/env_infra' && parseFloat(latest.value) > 800) {
        banner.textContent = 'Infrared Alert!';
        banner.classList.add('show');
        setTimeout(() => banner.classList.remove('show'), 3000);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    fetchData();
    setInterval(fetchData, 30000); // Poll every 30 seconds
    document.getElementById('refresh-btn').addEventListener('click', fetchData);
    document.getElementById('toggle-chart-btn').addEventListener('click', () => {
        const chartSection = document.getElementById('chart-section');
        const isHidden = chartSection.style.display === 'none';
        chartSection.style.display = isHidden ? 'block' : 'none';
        document.getElementById('toggle-chart-btn').textContent = isHidden ? 'Hide Chart' : 'Show Chart';
    });
    document.getElementById('device-filter').addEventListener('change', () => populateTable(allData));
});