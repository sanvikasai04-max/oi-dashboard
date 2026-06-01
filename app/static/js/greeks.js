async function fetchGreeksData() {
    try {
        const response = await fetch("/api/atm?interval=5m");
        const data = await response.json();

        if (data.error) {
            console.error("GREKS PAGE ERROR:", data.error);
            return;
        }

        document.getElementById("spot-price").innerText = Number(data.spot).toFixed(2);
        document.getElementById("last-update").innerText = data.last_update || "--";

        const ceData = data.ce_data.slice().reverse();
        const peData = data.pe_data.slice().reverse();

        const labels = ceData.map(row => row.time);

        const deltaSeries = [
            {
                label: "CE Delta",
                data: ceData.map(row => row.delta),
                borderColor: "#22c55e",
                backgroundColor: "rgba(34, 197, 94, 0.2)",
                fill: false,
                tension: 0.3,
                pointRadius: 2
            },
            {
                label: "PE Delta",
                data: peData.map(row => row.delta),
                borderColor: "#ef4444",
                backgroundColor: "rgba(239, 68, 68, 0.2)",
                fill: false,
                tension: 0.3,
                pointRadius: 2
            }
        ];

        const gammaSeries = [
            {
                label: "CE Gamma",
                data: ceData.map(row => row.gamma),
                borderColor: "#60a5fa",
                backgroundColor: "rgba(96, 165, 250, 0.2)",
                fill: false,
                tension: 0.3,
                pointRadius: 2
            },
            {
                label: "PE Gamma",
                data: peData.map(row => row.gamma),
                borderColor: "#fbbf24",
                backgroundColor: "rgba(251, 191, 36, 0.2)",
                fill: false,
                tension: 0.3,
                pointRadius: 2
            }
        ];

        const ivSeries = [
            {
                label: "CE IV",
                data: ceData.map(row => row.iv),
                borderColor: "#a855f7",
                backgroundColor: "rgba(168, 85, 247, 0.2)",
                fill: false,
                tension: 0.3,
                pointRadius: 2
            },
            {
                label: "PE IV",
                data: peData.map(row => row.iv),
                borderColor: "#22d3ee",
                backgroundColor: "rgba(34, 211, 238, 0.2)",
                fill: false,
                tension: 0.3,
                pointRadius: 2
            }
        ];

        const buildupSeries = [
            {
                label: "CE OI Change",
                data: ceData.map(row => row.oi_change || 0),
                borderColor: "#22c55e",
                backgroundColor: "rgba(34, 197, 94, 0.2)",
                fill: false,
                tension: 0.3,
                pointRadius: 2
            },
            {
                label: "PE OI Change",
                data: peData.map(row => row.oi_change || 0),
                borderColor: "#ef4444",
                backgroundColor: "rgba(239, 68, 68, 0.2)",
                fill: false,
                tension: 0.3,
                pointRadius: 2
            }
        ];

        renderLineChart("delta-chart", labels, deltaSeries, "ATM Delta");
        renderLineChart("gamma-chart", labels, gammaSeries, "ATM Gamma");
        renderLineChart("iv-chart", labels, ivSeries, "ATM IV");
        renderLineChart("buildup-chart", labels, buildupSeries, "ATM CE / PE OI Change");
    }
    catch (error) {
        console.error("GREKS PAGE ERROR:", error);
    }
}

function renderLineChart(canvasId, labels, datasets, title) {
    const ctx = document.getElementById(canvasId).getContext("2d");

    new Chart(ctx, {
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
                y: {
                    ticks: {
                        color: "#fff"
                    },
                    grid: {
                        color: "rgba(255,255,255,0.08)"
                    }
                }
            }
        }
    });
}

window.addEventListener("DOMContentLoaded", fetchGreeksData);
