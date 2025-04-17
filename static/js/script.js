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
            const collection = item.collection || (item.train_accelerometer ? 'trainESP' : 'environmentESP');
            return collection === deviceFilter || (deviceFilter === 'trainESP' && ['train_accelerometer', 'train_ultra', 'train_infra'].includes(collection)) ||
                   (deviceFilter === 'environmentESP' && ['tof1', 'tof2', 'dht', 'sw420', 'env_ultra'].includes(collection));
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
        const collectionName = item.collection || (item.train_accelerometer ? 'trainESP' : 'environmentESP');
        const value = item.value || JSON.stringify({
            ...(item.train_accelerometer && { train_accelerometer: item.train_accelerometer }),
            ...(item.train_ultra && { train_ultra: item.train_ultra }),
            ...(item.train_infra && { train_infra: item.train_infra }),
            ...(item.tof1 && { tof1: item.tof1 }),
            ...(item.tof2 && { tof2: item.tof2 }),
            ...(item.dht && { dht: item.dht }),
            ...(item.sw420 && { sw420: item.sw420 }),
            ...(item.env_ultra && { env_ultra: item.env_ultra })
        });
        row.innerHTML = `
            <td>${collectionName}</td>
            <td>${value}</td>
            <td>${new Date(item.timestamp).toLocaleString()}</td>
        `;
        tableBody.appendChild(row);
    });
}

function updateChart(data) {
    const ctx = document.getElementById('sensorChart').getContext('2d');
    const datasets = [
        { collection: 'train_accelerometer', label: 'Train Accelerometer', color: '#d4a5a5' },
        { collection: 'train_ultra', label: 'Train Ultra', color: '#b392ac' },
        { collection: 'train_infra', label: 'Train Infra', color: '#8e7b9b' },
        { collection: 'tof1', label: 'TOF1', color: '#6d8299' },
        { collection: 'tof2', label: 'TOF2', color: '#a3bffa' },
        { collection: 'dht', label: 'DHT', color: '#f4a261' },
        { collection: 'sw420', label: 'SW420', color: '#e76f51' },
        { collection: 'env_ultra', label: 'Env Ultra', color: '#2a9d8f' }
    ].map(sensor => ({
        label: sensor.label,
        data: data.filter(item => item.collection === sensor.collection).slice(0, 10).reverse().map(item => parseFloat(item.value) || 0),
        borderColor: sensor.color,
        backgroundColor: `${sensor.color}40`, // 25% opacity
        fill: true,
        pointHoverRadius: 6,
    }));

    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.filter(item => item.collection === 'train_accelerometer').slice(0, 10).reverse().map(item => new Date(item.timestamp).toLocaleTimeString()),
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
    const latestTrain = data.find(item => item.collection === 'train_accelerometer') || {};
    train.classList.remove('moving', 'alert');
    if (parseFloat(latestTrain.value) > 0) { // Example condition
        train.classList.add('moving');
    }
}

function checkAlerts(data) {
    const latest = data[0] || {};
    const banner = document.getElementById('alert-banner');
    if (latest.collection === 'train_infra' && parseFloat(latest.value) > 1000) { // Example threshold
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