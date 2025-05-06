let sensorChart;

document.addEventListener('DOMContentLoaded', () => {
    // Load ML metrics
    fetch('/api/ml_metrics')
        .then(response => response.json())
        .then(data => {
            const tableBody = document.getElementById('metrics-table');
            tableBody.innerHTML = '';
            data.forEach(item => {
                const row = `
                    <tr>
                        <td>${item.collection}</td>
                        <td>${item.final_loss ? item.final_loss.toFixed(4) : '-'}</td>
                        <td>${item.final_val_loss ? item.final_val_loss.toFixed(4) : '-'}</td>
                        <td>${item.threshold ? item.threshold.toFixed(4) : '-'}</td>
                        <td>${new Date(item.timestamp).toLocaleString()}</td>
                    </tr>`;
                tableBody.innerHTML += row;
            });
        })
        .catch(error => console.error('Error fetching ML metrics:', error));

    // Load initial sensor data
    fetch('/api/all-data?limit=100')
        .then(response => response.json())
        .then(data => {
            const tableBody = document.getElementById('data-table');
            tableBody.innerHTML = '';
            data.forEach(item => {
                const row = `
                    <tr>
                        <td>${item.collection}</td>
                        <td>${item.value}</td>
                        <td>${new Date(item.timestamp).toLocaleString()}</td>
                        <td>${item.anomaly ? 'Yes' : 'No'}</td>
                    </tr>`;
                tableBody.innerHTML += row;
            });
        })
        .catch(error => console.error('Error fetching sensor data:', error));

    // Handle dropdown change
    document.getElementById('collection-select').addEventListener('change', (e) => {
        const collection = e.target.value;
        if (collection) {
            fetch(`/api/collection/${collection}`)
                .then(response => response.json())
                .then(data => {
                    const labels = data.map(item => new Date(item.timestamp).toLocaleString());
                    const values = data.map(item => parseFloat(item.value));
                    updateChart(collection, labels, values);
                })
                .catch(error => console.error(`Error fetching data for ${collection}:`, error));
        } else {
            if (sensorChart) sensorChart.destroy();
        }
    });

    // Handle load more button
    document.getElementById('load-more-btn').addEventListener('click', () => {
        const tableBody = document.getElementById('data-table');
        const currentRows = tableBody.children.length;
        fetch(`/api/all-data?skip=${currentRows}&limit=100`)
            .then(response => response.json())
            .then(data => {
                data.forEach(item => {
                    const row = `
                        <tr>
                            <td>${item.collection}</td>
                            <td>${item.value}</td>
                            <td>${new Date(item.timestamp).toLocaleString()}</td>
                            <td>${item.anomaly ? 'Yes' : 'No'}</td>
                        </tr>`;
                    tableBody.innerHTML += row;
                });
            })
            .catch(error => console.error('Error loading more data:', error));
    });
});

function updateChart(collection, labels, values) {
    const ctx = document.getElementById('sensorChart').getContext('2d');
    if (sensorChart) sensorChart.destroy();

    sensorChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.reverse(), // Newest first
            datasets: [{
                label: collection,
                data: values.reverse(),
                borderColor: '#007bff',
                fill: false
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
}