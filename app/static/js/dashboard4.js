let dashboard4Signals = [];
let dashboard4Candles = [];
let selectedSignalId = null;

async function loadDashboard4() {
    const response = await fetch("/api/dashboard4");
    const data = await response.json();

    if (data.error) {
        document.getElementById("d4-signals-body").innerHTML =
            `<tr><td colspan="20" style="padding:30px;color:#ef4444;">${data.error}</td></tr>`;
        return;
    }

    dashboard4Signals = data.signals || [];
    dashboard4Candles = data.candles || [];
    selectedSignalId = data.selected ? data.selected.id : null;

    fillDashboard4Summary(data);
    renderDashboard4Table();

    if (data.selected) {
        renderSelectedChart(data.selected, dashboard4Candles);
    } else {
        drawEmptyChart("No entries found");
    }
}

function fillDashboard4Summary(data) {
    document.getElementById("d4-spot").innerText = data.spot ?? "--";
    document.getElementById("d4-atm").innerText = data.atm ?? "--";
    document.getElementById("d4-date").innerText = data.data_date ?? "--";
    document.getElementById("d4-total").innerText = data.summary?.total ?? "--";
    document.getElementById("d4-wins").innerText = data.summary?.wins ?? "--";
    document.getElementById("d4-losses").innerText = data.summary?.losses ?? "--";
    document.getElementById("d4-open").innerText = data.summary?.open ?? "--";

    const pnl = data.summary?.net_pnl_pct ?? 0;
    const pnlEl = document.getElementById("d4-pnl");
    pnlEl.innerText = `${pnl >= 0 ? "+" : ""}${pnl}%`;
    pnlEl.style.color = pnl >= 0 ? "#22c55e" : "#ef4444";
}

function renderDashboard4Table() {
    const tbody = document.getElementById("d4-signals-body");

    if (!dashboard4Signals.length) {
        tbody.innerHTML = `<tr><td colspan="20" style="padding:30px;color:#9ca3af;">No entries found.</td></tr>`;
        return;
    }

    tbody.innerHTML = "";

    dashboard4Signals.forEach(signal => {
        const row = document.createElement("tr");
        row.dataset.id = signal.id;
        if (signal.id === selectedSignalId) row.classList.add("active-signal");

        row.innerHTML = `
            <td>${signal.time}</td>
            <td>${directionTag(signal.direction)}</td>
            <td><span class="tag tag-blue">${signal.zone}</span></td>
            <td>${signal.setup}</td>
            <td>${signal.strike} ${signal.option}</td>
            <td><strong>${signal.entry_ltp}</strong></td>
            <td style="color:#ef4444">${signal.sl}</td>
            <td style="color:#eab308">${signal.target1}</td>
            <td style="color:#22c55e">${signal.target2}</td>
            <td>${outcomeTag(signal.outcome)} ${signal.exit_ltp}</td>
            <td>${signal.exit_time}</td>
            <td class="${numClass(signal.pnl_pct)}">${signed(signal.pnl_pct)}%</td>
            <td>${signal.delta}</td>
            <td class="${numClass(signal.delta_chg)}">${signed(signal.delta_chg)}%</td>
            <td>${signal.gamma}</td>
            <td class="${numClass(signal.gamma_chg)}">${signed(signal.gamma_chg)}%</td>
            <td class="${numClass(signal.oi_change)}">${formatOI(signal.oi_change)}</td>
            <td class="${numClass(signal.oi_change_pct)}">${signed(signal.oi_change_pct)}%</td>
            <td><span class="tag tag-mid">${signal.score} ${signal.confidence}</span></td>
            <td style="font-size:11px;color:#9ca3af;">${signal.reason}</td>
        `;

        row.addEventListener("click", () => selectDashboard4Signal(signal));
        tbody.appendChild(row);
    });
}

async function selectDashboard4Signal(signal) {
    selectedSignalId = signal.id;
    renderDashboard4Table();

    const response = await fetch(`/api/dashboard4/candles?strike=${signal.strike}&option=${signal.option}`);
    const data = await response.json();
    renderSelectedChart(signal, data.candles || []);
}

function renderSelectedChart(signal, candles) {
    document.getElementById("chart-title").innerText =
        `${signal.strike} ${signal.option} | ${signal.direction} | ${signal.zone}`;
    document.getElementById("chart-plan").innerText =
        `Entry ${signal.entry_ltp} | SL ${signal.sl} | T1 ${signal.target1} | T2 ${signal.target2} | Exit ${signal.exit_ltp}`;

    drawCandles(candles, signal);
}

function drawCandles(candles, signal) {
    const canvas = document.getElementById("entry-chart");
    const ctx = canvas.getContext("2d");
    const width = canvas.width = canvas.clientWidth * window.devicePixelRatio;
    const height = canvas.height = canvas.clientHeight * window.devicePixelRatio;
    const scale = window.devicePixelRatio;
    ctx.scale(scale, scale);

    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#0b1120";
    ctx.fillRect(0, 0, w, h);

    if (!candles.length) {
        drawEmptyChart("No candle data");
        return;
    }

    const pad = { left: 54, right: 58, top: 20, bottom: 32 };
    const maxPrice = Math.max(...candles.map(c => c.high), signal.target2, signal.entry_ltp);
    const minPrice = Math.min(...candles.map(c => c.low), signal.sl, signal.entry_ltp);
    const range = Math.max(1, maxPrice - minPrice);
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;
    const step = plotW / candles.length;
    const bodyW = Math.max(3, Math.min(12, step * 0.58));
    const y = price => pad.top + ((maxPrice - price) / range) * plotH;

    ctx.strokeStyle = "rgba(148,163,184,0.16)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const yy = pad.top + (plotH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, yy);
        ctx.lineTo(w - pad.right, yy);
        ctx.stroke();

        const price = maxPrice - (range / 4) * i;
        ctx.fillStyle = "#94a3b8";
        ctx.font = "11px Arial";
        ctx.fillText(price.toFixed(1), w - pad.right + 8, yy + 3);
    }

    candles.forEach((candle, i) => {
        const x = pad.left + i * step + step / 2;
        const up = candle.close >= candle.open;
        const color = up ? "#14b8a6" : "#ef4444";
        const highY = y(candle.high);
        const lowY = y(candle.low);
        const openY = y(candle.open);
        const closeY = y(candle.close);
        const top = Math.min(openY, closeY);
        const bottom = Math.max(openY, closeY);

        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();
        ctx.fillRect(x - bodyW / 2, top, bodyW, Math.max(2, bottom - top));

        if (i % Math.ceil(candles.length / 8) === 0) {
            ctx.fillStyle = "#94a3b8";
            ctx.font = "10px Arial";
            ctx.fillText(candle.time, x - 14, h - 12);
        }
    });

    drawPriceLine(ctx, pad, plotW, y(signal.entry_ltp), "#60a5fa", `Entry ${signal.entry_ltp}`);
    drawPriceLine(ctx, pad, plotW, y(signal.sl), "#ef4444", `SL ${signal.sl}`);
    drawPriceLine(ctx, pad, plotW, y(signal.target1), "#eab308", `T1 ${signal.target1}`);
    drawPriceLine(ctx, pad, plotW, y(signal.target2), "#22c55e", `T2 ${signal.target2}`);

    const entryIndex = candles.findIndex(c => c.time >= signal.bucket);
    if (entryIndex >= 0) {
        const x = pad.left + entryIndex * step + step / 2;
        ctx.fillStyle = "#60a5fa";
        ctx.beginPath();
        ctx.arc(x, y(signal.entry_ltp), 5, 0, Math.PI * 2);
        ctx.fill();
    }
}

function drawPriceLine(ctx, pad, plotW, y, color, label) {
    ctx.strokeStyle = color;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.font = "11px Arial";
    ctx.fillText(label, pad.left + 8, y - 5);
}

function drawEmptyChart(text) {
    const canvas = document.getElementById("entry-chart");
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#0b1120";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#9ca3af";
    ctx.font = "14px Arial";
    ctx.fillText(text, 24, 36);
}

function directionTag(direction) {
    return `<span class="tag ${direction === "Bullish" ? "tag-bull" : "tag-bear"}">${direction}</span>`;
}

function outcomeTag(outcome) {
    if (outcome.includes("Target")) return `<span class="tag tag-bull">${outcome}</span>`;
    if (outcome.includes("SL")) return `<span class="tag tag-bear">${outcome}</span>`;
    return `<span class="tag tag-mid">${outcome}</span>`;
}

function numClass(value) {
    const n = Number(value);
    if (n > 0) return "pct-green";
    if (n < 0) return "pct-red";
    return "pct-neutral";
}

function signed(value) {
    const n = Number(value);
    if (Number.isNaN(n)) return "--";
    return `${n > 0 ? "+" : ""}${n}`;
}

function formatOI(value) {
    const n = Number(value);
    if (Number.isNaN(n)) return "--";
    const sign = n > 0 ? "+" : n < 0 ? "-" : "";
    const abs = Math.abs(n);
    if (abs >= 10000000) return `${sign}${(abs / 10000000).toFixed(2)} Cr`;
    if (abs >= 100000) return `${sign}${(abs / 100000).toFixed(2)} L`;
    if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(2)} K`;
    return `${n}`;
}

window.addEventListener("DOMContentLoaded", loadDashboard4);
window.addEventListener("resize", () => {
    const signal = dashboard4Signals.find(item => item.id === selectedSignalId);
    if (signal && dashboard4Candles.length) drawCandles(dashboard4Candles, signal);
});
