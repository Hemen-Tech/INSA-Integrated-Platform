let miniNdviChart = null;
let miniRainChart = null;
let miniSoilChart = null;

document.addEventListener("DOMContentLoaded", () => {
    initializePage();
    loadSampleDashboardData();
    setInterval(loadSampleDashboardData, 300000); // Refresh every 5 minutes with new sample data
});

function initializePage() {
    // Set up mobile menu
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    if (menuToggle && sidebar && overlay) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            overlay.classList.toggle('active');
        });

        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('active');
        });
    }
}

function loadSampleDashboardData() {
    console.log("🔄 Loading sample dashboard data...");
    
    // Generate dynamic sample data
    const sampleData = generateSampleDashboardData();
    
    console.log("✅ Sample dashboard data loaded successfully", sampleData);
    
    // Update stats with sample data
    updateStatElement("modelAccuracy", `${(sampleData.model_accuracy * 100).toFixed(1)}%`);
    updateStatElement("dataPoints", formatNumber(sampleData.data_points));

    const nationalRiskEl = document.getElementById("nationalRisk");
    if (nationalRiskEl) {
        nationalRiskEl.textContent = sampleData.national_risk;
        nationalRiskEl.className = `stat-value stat-${getRiskClass(sampleData.national_risk)}`;
    }

    updateStatElement("highRiskRegions", sampleData.high_risk_regions.length > 0 
        ? sampleData.high_risk_regions.join(", ") 
        : "None");

    // Update charts with sample trend data
    updateMiniCharts(sampleData.trends);
    
    // Hide any error messages
    hideError();
}

function updateStatElement(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = value;
    }
}

function generateSampleDashboardData() {
    // Generate realistic sample data with some randomness
    const riskLevels = ["No Drought", "Mild", "Moderate", "Severe"];
    const regions = ["Afar", "Somali", "Oromia", "Amhara", "Tigray", "SNNPR"];
    
    // Random but realistic values
    const modelAccuracy = 0.75 + Math.random() * 0.15; // 75-90%
    const dataPoints = 120000 + Math.floor(Math.random() * 50000); // 120k-170k
    const nationalRisk = riskLevels[Math.floor(Math.random() * riskLevels.length)];
    
    // Randomly select 0-3 high risk regions
    const numHighRiskRegions = Math.floor(Math.random() * 4);
    const highRiskRegions = regions.slice(0, numHighRiskRegions);
    
    // Generate trend data with some realistic patterns
    const baseNdvi = 0.45 + Math.random() * 0.25;
    const baseRain = 6 + Math.random() * 10;
    const baseSoil = 0.25 + Math.random() * 0.25;
    
    const trends = {
        ndvi: Array.from({length: 7}, (_, i) => {
            // Slight downward trend with noise
            const trend = -0.02 * i;
            const noise = (Math.random() - 0.5) * 0.1;
            return Math.max(0, Math.min(1, baseNdvi + trend + noise));
        }),
        rain: Array.from({length: 7}, (_, i) => {
            // Seasonal variation with noise
            const seasonal = Math.sin(i * 0.5) * 3;
            const noise = (Math.random() - 0.5) * 4;
            return Math.max(0, baseRain + seasonal + noise);
        }),
        soil: Array.from({length: 7}, (_, i) => {
            // Gradual decline with noise
            const trend = -0.01 * i;
            const noise = (Math.random() - 0.5) * 0.08;
            return Math.max(0, Math.min(0.6, baseSoil + trend + noise));
        })
    };
    
    return {
        model_accuracy: modelAccuracy,
        data_points: dataPoints,
        national_risk: nationalRisk,
        high_risk_regions: highRiskRegions,
        trends: trends
    };
}

function hideError() {
    const errorDiv = document.getElementById("errorMessage");
    if (errorDiv) {
        errorDiv.style.display = "none";
    }
}

function showError(message) {
    const errorDiv = document.getElementById("errorMessage");
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = "block";
    } else {
        console.error("Error message element not found:", message);
    }
}

function showWarning(message) {
    const warningDiv = document.getElementById("warningMessage");
    if (warningDiv) {
        warningDiv.textContent = message;
        warningDiv.style.display = "block";
    }
}

function getRiskClass(risk) {
    const classes = {
        "No Drought": "stat-green",
        "Mild": "stat-green",
        "Moderate": "stat-orange",
        "Severe": "stat-red"
    };
    return classes[risk] || "stat-green";
}

function updateMiniCharts(trends) {
    const labels = Array.from({ length: 7 }, (_, i) => `Day ${i + 1}`);

    // Destroy existing charts if they exist
    if (miniNdviChart) {
        miniNdviChart.destroy();
        miniNdviChart = null;
    }
    if (miniRainChart) {
        miniRainChart.destroy();
        miniRainChart = null;
    }
    if (miniSoilChart) {
        miniSoilChart.destroy();
        miniSoilChart = null;
    }

    const createConfig = (data, color, label) => ({
        type: 'line',
        data: {
            labels,
            datasets: [{
                label,
                data,
                borderColor: color,
                backgroundColor: `${color}22`,
                fill: true,
                tension: 0.4,
                borderWidth: 2,
                pointRadius: 3,
                pointBackgroundColor: color,
                pointBorderColor: '#ffffff',
                pointBorderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { 
                legend: { display: false },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                x: { 
                    display: true,
                    grid: { display: false },
                    ticks: { color: '#6b7280' }
                },
                y: { 
                    display: true,
                    grid: { color: 'rgba(0,0,0,0.1)' },
                    ticks: { color: '#6b7280' }
                }
            },
            animation: {
                duration: 1000,
                easing: 'easeOutQuart'
            }
        }
    });

    // Mini NDVI Chart - check if canvas exists
    const ndviCtx = document.getElementById("miniNdvi");
    if (ndviCtx) {
        miniNdviChart = new Chart(ndviCtx.getContext("2d"), 
            createConfig(trends.ndvi, '#10b981', 'NDVI Trend'));
    } else {
        console.warn("NDVI chart canvas not found");
    }

    // Mini Rain Chart - check if canvas exists
    const rainCtx = document.getElementById("miniRain");
    if (rainCtx) {
        miniRainChart = new Chart(rainCtx.getContext("2d"), 
            createConfig(trends.rain, '#3b82f6', 'Rainfall'));
    } else {
        console.warn("Rain chart canvas not found");
    }

    // Mini Soil Chart - check if canvas exists
    const soilCtx = document.getElementById("miniSoil");
    if (soilCtx) {
        miniSoilChart = new Chart(soilCtx.getContext("2d"), 
            createConfig(trends.soil, '#8b5cf6', 'Soil Moisture'));
    } else {
        console.warn("Soil chart canvas not found");
    }
}

function formatNumber(num) {
    if (num >= 1e6) return (num / 1e6).toFixed(1) + "M";
    if (num >= 1e3) return (num / 1e3).toFixed(1) + "K";
    return num.toLocaleString();
}