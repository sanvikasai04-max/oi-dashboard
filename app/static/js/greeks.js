const STRIKE_PRESETS = [
    { offset: 0, label: "ATM", id: "atm" },
    { offset: 50, label: "ATM +50", id: "plus50" },
    { offset: 100, label: "ATM +100", id: "plus100" },
    { offset: 150, label: "ATM +150", id: "plus150" },
    { offset: 200, label: "ATM +200", id: "plus200" },
    { offset: -50, label: "ATM -50", id: "minus50" },
    { offset: -100, label: "ATM -100", id: "minus100" },
    { offset: -150, label: "ATM -150", id: "minus150" },
    { offset: -200, label: "ATM -200", id: "minus200" }
];

async function fetchGreeksData() {
    try {
        const baseResponse = await fetch(`/api/greeks?interval=5m`);
        const baseData = await baseResponse.json();

        if (baseData.error) {
            console.error("GREKS PAGE ERROR:", baseData.error);
            return;
        }

        const openingAtm = baseData.opening_atm;
        document.getElementById("spot-price").innerText = Number(baseData.spot).toFixed(2);
        document.getElementById("opening-atm").innerText = openingAtm;

        const chartRequests = STRIKE_PRESETS.map(preset => {
            const strike = openingAtm + preset.offset;
            return fetch(`/api/greeks?interval=5m&strike=${strike}`)
                .then(res => res.json())
                .then(data => ({ preset, strike, data }));
        });

        const strikeResults = await Promise.all(chartRequests);

        strikeResults.forEach(result => {
            if (result.data.error) {
                console.error(`GREKS PAGE ERROR for strike ${result.strike}:`, result.data.error);
                return;
            }

            const ce = result.data.ce_data.slice().reverse();
            const pe = result.data.pe_data.slice().reverse();
            const labels = ce.map(row => row.time);

            const ceTitle = document.getElementById(`ce-${result.preset.id}-title`);
            if (ceTitle) {
                ceTitle.innerText = `CE ${result.preset.label} (${result.strike})`;
            }
            const peTitle = document.getElementById(`pe-${result.preset.id}-title`);
            if (peTitle) {
                peTitle.innerText = `PE ${result.preset.label} (${result.strike})`;
            }

            renderLineChart(`ce-${result.preset.id}-chart`, labels, [
                {
                    label: "CE Delta",
                    data: ce.map(row => row.delta),
                    borderColor: "#22c55e",
                    backgroundColor: "rgba(34, 197, 94, 0.2)",
                    fill: false,
                    tension: 0.3,
                    pointRadius: 2,
                    borderWidth: 2,
                    yAxisID: "delta"
                },
                {
                    label: "CE Gamma",
                    data: ce.map(row => row.gamma),
                    borderColor: "#60a5fa",
                    backgroundColor: "rgba(96, 165, 250, 0.2)",
                    fill: false,
                    tension: 0.3,
                    pointRadius: 2,
                    borderWidth: 3,
                    yAxisID: "gamma"
                }
            ], `CE ${result.preset.label} (${result.strike})`);

            renderLineChart(`pe-${result.preset.id}-chart`, labels, [
                {
                    label: "PE Delta",
                    data: pe.map(row => row.delta),
                    borderColor: "#ef4444",
                    backgroundColor: "rgba(239, 68, 68, 0.2)",
                    fill: false,
                    tension: 0.3,
                    pointRadius: 2,
                    borderWidth: 2,
                    yAxisID: "delta"
                },
                {
                    label: "PE Gamma",
                    data: pe.map(row => row.gamma),
                    borderColor: "#fbbf24",
                    backgroundColor: "rgba(251, 191, 36, 0.2)",
                    fill: false,
                    tension: 0.3,
                    pointRadius: 2,
                    borderWidth: 3,
                    yAxisID: "gamma"
                }
            ], `PE ${result.preset.label} (${result.strike})`);
        });
    }
    catch (error) {
        console.error("GREKS PAGE ERROR:", error);
    }
}

function renderLineChart(canvasId, labels, datasets, title) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        return;
    }

    const existingChart = Chart.getChart(canvas);
    if (existingChart) {
        existingChart.destroy();
    }

    new Chart(canvas, {
        type: "line",
        data: {
            labels,
            datasets
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: false,
                    text: title
                },
                tooltip: {
                    mode: "index",
                    intersect: false
                },
                legend: {
                    position: "bottom"
                }
            },
            interaction: {
                mode: "nearest",
                axis: "x",
                intersect: false
            },
            scales: {
                x: {
                    ticks: {
                        color: "#fff"
                    },
                    grid: {
                        color: "rgba(255,255,255,0.08)"
                    }
                },
                delta: {
                    type: "linear",
                    position: "left",
                    title: {
                        display: true,
                        text: "Delta",
                        color: "#fff"
                    },
                    ticks: {
                        color: "#fff"
                    },
                    grid: {
                        color: "rgba(255,255,255,0.08)"
                    }
                },
                gamma: {
                    type: "linear",
                    position: "right",
                    title: {
                        display: true,
                        text: "Gamma",
                        color: "#fff"
                    },
                    ticks: {
                        color: "#fff"
                    },
                    grid: {
                        drawOnChartArea: false,
                        color: "rgba(255,255,255,0.08)"
                    }
                }
            }
        }
    });
}

window.addEventListener("DOMContentLoaded", () => {
    fetchGreeksData();
    setInterval(fetchGreeksData, 5 * 60 * 1000);
});

