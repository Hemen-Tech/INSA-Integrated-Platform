let trendChart = null;

/**
 * Run drought forecast when user clicks the button - Frontend simulation
 */
async function runForecast() {
    const runBtn = document.getElementById("runBtn");
    const loading = document.getElementById("loading");
    const results = document.getElementById("results");
    const resultRows = document.getElementById("resultRows");
    
    // Show loading indicator
    runBtn.disabled = true;
    loading.style.display = "block";
    results.style.display = "none";
    resultRows.innerHTML = "";
    
    try {
        // Get form inputs
        const region = document.getElementById("region").value;
        const dateInput = document.getElementById("assessmentDate").value;
        if (!dateInput) {
            alert("Please select an assessment date.");
            return;
        }
        const selectedDate = new Date(dateInput);
        
        // Simulate processing time
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        // Generate simulated multi-horizon predictions
        const mockPredictions = generateMockForecastData(region, selectedDate);
        
        // Hide loading
        loading.style.display = "none";
        results.style.display = "block";
        
        // Process and display results
        const horizons = mockPredictions.map((pred, idx) => {
            const labels = ["0–3 Months", "3–6 Months", "6–9 Months", "9–12 Months"];
            const months = [3, 6, 9, 12];
            const endDate = new Date(selectedDate);
            endDate.setMonth(selectedDate.getMonth() + months[idx]);
            return {
                label: labels[idx],
                date: endDate.toISOString().split('T')[0],
                probabilities: pred.probabilities
            };
        });

        // Render each horizon
        resultRows.innerHTML = ''; // Clear previous results
        horizons.forEach(h => {
            const probs = h.probabilities;
            const maxProbKey = Object.keys(probs).reduce((a, b) => probs[a] > probs[b] ? a : b);
            const confidencePercent = (probs[maxProbKey] * 100).toFixed(1);
            
            const row = document.createElement("div");
            row.className = "result-row";
            row.innerHTML = `
                <div class="result-horizon">${h.label} <span style="color:#6c757d; font-weight:normal;">(End: ${h.date})</span></div>
                <span class="result-category severity-${maxProbKey.toLowerCase().replace(' ', '-')}">${maxProbKey}</span>
                <div class="result-confidence">AI Confidence: ${confidencePercent}%</div>
                <div class="result-probabilities">
                    ${renderProbBar("No Drought", probs["No Drought"] || 0, "#28a745")}
                    ${renderProbBar("Mild", probs["Mild"] || 0, "#ffc107")}
                    ${renderProbBar("Moderate", probs["Moderate"] || 0, "#fd7e14")}
                    ${renderProbBar("Severe", probs["Severe"] || 0, "#dc3545")}
                </div>
            `;
            resultRows.appendChild(row);
        });
        
        // Update trend chart
        updateTrendChart(horizons);
        
    } catch (error) {
        console.error("Forecast simulation failed:", error);
        loading.style.display = "none";
        resultRows.innerHTML = `
            <p style="color: red;">
                ❌ Simulation error: ${error.message}
            </p>`;
        results.style.display = "block";
    } finally {
        runBtn.disabled = false;
    }
}

/**
 * Generate mock forecast data for frontend simulation
 */
function generateMockForecastData(region, selectedDate) {
    // Region-specific drought risk patterns
    const regionRiskProfiles = {
        "Afar": { baseRisk: 0.7, volatility: 0.2 },
        "Somali": { baseRisk: 0.6, volatility: 0.25 },
        "Borena": { baseRisk: 0.5, volatility: 0.3 },
        "Mekele": { baseRisk: 0.4, volatility: 0.2 },
        "Gambela": { baseRisk: 0.3, volatility: 0.15 },
        "Gonder": { baseRisk: 0.35, volatility: 0.2 },
        "Wag-Himra": { baseRisk: 0.45, volatility: 0.25 },
        "Yabello": { baseRisk: 0.55, volatility: 0.3 }
    };
    
    const profile = regionRiskProfiles[region] || { baseRisk: 0.4, volatility: 0.2 };
    const predictions = [];
    
    // Generate 4 horizons (0-3, 3-6, 6-9, 9-12 months)
    for (let horizon = 0; horizon < 4; horizon++) {
        // Add seasonal effects (higher risk in dry seasons)
        const month = (selectedDate.getMonth() + horizon * 3) % 12;
        const seasonalFactor = (month >= 10 || month <= 2) ? 1.3 : 0.8; // Oct-Feb dry season
        
        // Add time uncertainty (risk increases with distance)
        const timeUncertainty = 1 + (horizon * 0.1);
        
        // Calculate base severe drought probability
        let severeProb = profile.baseRisk * seasonalFactor * timeUncertainty;
        severeProb = Math.max(0.05, Math.min(0.85, severeProb + (Math.random() - 0.5) * profile.volatility));
        
        // Generate other probabilities
        let moderateProb = 0.25 + Math.random() * 0.15;
        let mildProb = 0.15 + Math.random() * 0.1;
        let noDroughtProb = 1 - severeProb - moderateProb - mildProb;
        
        // Ensure no drought probability is reasonable
        if (noDroughtProb < 0.05) {
            const excess = 0.05 - noDroughtProb;
            severeProb -= excess * 0.5;
            moderateProb -= excess * 0.3;
            mildProb -= excess * 0.2;
            noDroughtProb = 0.05;
        }
        
        // Normalize probabilities
        const total = severeProb + moderateProb + mildProb + noDroughtProb;
        const probabilities = {
            "No Drought": noDroughtProb / total,
            "Mild": mildProb / total,
            "Moderate": moderateProb / total,
            "Severe": severeProb / total
        };
        
        predictions.push({ probabilities });
    }
    
    return predictions;
}
function renderProbBar(label, prob, color) {
    const width = (prob * 100).toFixed(1);
    return `
        <div class="prob-bar">
            <span class="prob-label">${label}</span>
            <div class="prob-bar-container">
                <div class="prob-bar-fill" style="width: ${width}%; background-color: ${color};"></div>
            </div>
            <span class="prob-value">${width}%</span>
        </div>`;
}

/**
 * Add months to a date string
 */
function addMonths(dateStr, months) {
    const date = new Date(dateStr);
    date.setMonth(date.getMonth() + months);
    return date.toISOString().split('T')[0];
}

// ✅ Optional: Keep only if you want to extrapolate beyond 12 months
function longTermTrend(baseProbs) {
    const p = { ...baseProbs };
    p["No Drought"] = Math.max(p["No Drought"] - 0.15, 0.03);
    p["Mild"] = p["Mild"] - 0.05;
    p["Moderate"] = p["Moderate"] + 0.1;
    p["Severe"] = Math.min(p["Severe"] + 0.1, 0.7);
    return normalizeProbabilities(p);
}

/**
 * Normalize probabilities to sum to 1
 */
function normalizeProbabilities(probs) {
    const total = Object.values(probs).reduce((sum, prob) => sum + prob, 0);
    const normalized = {};
    Object.keys(probs).forEach(key => {
        normalized[key] = probs[key] / total;
    });
    return normalized;
}

/**
 * Update Chart.js trend chart with proper data mapping
 */
function updateTrendChart(horizons) {
    const ctx = document.getElementById('trendChart').getContext('2d');
    
    // Destroy old chart
    if (trendChart) {
        trendChart.destroy();
    }
    
    const severityLevel = {
        "No Drought": 0,
        "Mild": 1,
        "Moderate": 2,
        "Severe": 3
    };
    
    // Calculate data points - get the most probable category for each horizon
    const data = horizons.map(h => {
        let maxProb = 0;
        let maxCategory = "No Drought";
        Object.entries(h.probabilities).forEach(([category, prob]) => {
            if (prob > maxProb) {
                maxProb = prob;
                maxCategory = category;
            }
        });
        return severityLevel[maxCategory];
    });
    
    const labels = horizons.map(h => h.label);
    
    // Create new chart
    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Drought Risk Trend',
                data: data,
                borderColor: '#3498db',
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                borderWidth: 3,
                pointBackgroundColor: data.map(d => {
                    const colors = ['#28a745', '#ffc107', '#fd7e14', '#dc3545'];
                    return colors[d] || '#6c757d';
                }),
                pointBorderColor: '#ffffff',
                pointRadius: 6,
                pointHoverRadius: 8,
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    min: -0.5,
                    max: 3.5,
                    ticks: {
                        stepSize: 1,
                        callback: function(value) {
                            const labels = ['No Drought', 'Mild', 'Moderate', 'Severe'];
                            return labels[value] || '';
                        }
                    },
                    title: {
                        display: true,
                        text: 'Drought Severity Level',
                        font: {
                            weight: 'bold'
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Forecast Horizon',
                        font: {
                            weight: 'bold'
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    }
                }
            },
            plugins: {
                legend: { 
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleFont: {
                        size: 14,
                        weight: 'bold'
                    },
                    bodyFont: {
                        size: 13
                    },
                    callbacks: {
                        label: function(context) {
                            const severityLabels = ['No Drought', 'Mild', 'Moderate', 'Severe'];
                            const currentSeverity = severityLabels[context.parsed.y];
                            const horizon = horizons[context.dataIndex];
                            let tooltipText = [`Severity: ${currentSeverity}`];
                            Object.entries(horizon.probabilities).forEach(([category, prob]) => {
                                tooltipText.push(`${category}: ${(prob * 100).toFixed(1)}%`);
                            });
                            return tooltipText;
                        },
                        title: function(context) {
                            return horizons[context[0].dataIndex].label;
                        }
                    }
                }
            },
            animation: {
                duration: 1000,
                easing: 'easeOutQuart'
            }
        }
    });
}

// Set default date to today when page loads
document.addEventListener("DOMContentLoaded", () => {
    const today = new Date().toISOString().split('T')[0];
    const dateInput = document.getElementById("assessmentDate");
    if (dateInput) dateInput.value = today;
    
    const updateTime = document.getElementById("updateTime");
    if (updateTime) {
        updateTime.textContent = new Date().toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
});

// Export functions for testing (optional)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        runForecast,
        normalizeProbabilities,
        updateTrendChart
    };
}