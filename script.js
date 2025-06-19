// Global variables
let chart = null;
let currentMetric = 'pulse-pressure';

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function () {
    initializeChart();
    loadPatientData();
    setupMetricButtons();

    // Load data every 30 seconds
    setInterval(loadPatientData, 30000);
});

// Initialize Chart.js
function initializeChart() {
    const ctx = document.getElementById('mainChart');
    if (!ctx) return;

    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Pulse Pressure',
                data: [],
                borderColor: '#003A6B',
                backgroundColor: 'rgba(0, 58, 107, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            }
        }
    });
}

// Load patient data from server
async function loadPatientData() {
    try {
        showLoading(true);
        const response = await fetch('/api/patient-data');
        const data = await response.json();

        if (data.error) {
            showError('Error loading data: ' + data.error);
            return;
        }

        updateChart(data);
        updateSummaryStats(data);

    } catch (error) {
        console.error('Error fetching data:', error);
        showError('Failed to load patient data');
    } finally {
        showLoading(false);
    }
}

// Update chart with new data
function updateChart(data) {
    if (!chart || !data) return;

    const metricMap = {
        'pulse-pressure': { data: data.pulse_pressure, label: 'Pulse Pressure', color: '#003A6B' },
        'temperature': { data: data.temperature, label: 'Temperature (°F)', color: '#1B5886' },
        'spo2': { data: data.spo2, label: 'SpO2 (%)', color: '#3776A1' },
        'respiratory': { data: data.respiratory_rate, label: 'Respiratory Rate', color: '#5293B8' }
    };

    const metric = metricMap[currentMetric];
    if (!metric) return;

    chart.data.labels = data.timestamps;
    chart.data.datasets[0].data = metric.data;
    chart.data.datasets[0].label = metric.label;
    chart.data.datasets[0].borderColor = metric.color;
    chart.data.datasets[0].backgroundColor = metric.color + '20';
    chart.update();
}

// Update summary statistics
function updateSummaryStats(data) {
    const summaryContainer = document.getElementById('summary-stats');
    if (!summaryContainer) return;

    const metricData = {
        'pulse-pressure': data.pulse_pressure,
        'temperature': data.temperature,
        'spo2': data.spo2,
        'respiratory': data.respiratory_rate
    }[currentMetric];

    if (!metricData || metricData.length === 0) return;

    const avg = (metricData.reduce((a, b) => a + b, 0) / metricData.length).toFixed(1);
    const min = Math.min(...metricData);
    const max = Math.max(...metricData);
    const latest = metricData[metricData.length - 1];

    summaryContainer.innerHTML = `
        <div class="col-md-3">
            <div class="summary-stat">
                <p class="stat-label">Current</p>
                <p class="stat-value">${latest}</p>
            </div>
        </div>
        <div class="col-md-3">
            <div class="summary-stat">
                <p class="stat-label">Average</p>
                <p class="stat-value">${avg}</p>
            </div>
        </div>
        <div class="col-md-3">
            <div class="summary-stat">
                <p class="stat-label">Minimum</p>
                <p class="stat-value">${min}</p>
            </div>
        </div>
        <div class="col-md-3">
            <div class="summary-stat">
                <p class="stat-label">Maximum</p>
                <p class="stat-value">${max}</p>
            </div>
        </div>
    `;
}

// Setup metric button click handlers
function setupMetricButtons() {
    const buttons = document.querySelectorAll('.metric-card');
    buttons.forEach(button => {
        button.addEventListener('click', function () {
            // Remove active class from all buttons
            buttons.forEach(btn => btn.classList.remove('active'));

            // Add active class to clicked button
            this.classList.add('active');

            // Update current metric
            currentMetric = this.dataset.chart;

            // Reload data for new metric
            loadPatientData();
        });
    });

    // Set initial active button
    const firstButton = document.querySelector('.metric-card[data-chart="pulse-pressure"]');
    if (firstButton) {
        firstButton.classList.add('active');
    }
}

// Show/hide loading indicator
function showLoading(show) {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = show ? 'flex' : 'none';
    }
}

// Show error message
function showError(message) {
    const chartArea = document.getElementById('chart-area');
    if (chartArea) {
        chartArea.innerHTML = `<div class="error-message">${message}</div>`;
    }
}

// WebSocket connection for voice commands - moved to HTML files
