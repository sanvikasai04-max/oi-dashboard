async function fetchSignalsData() {
    try {
        const timeframe = document.getElementById("timeframe")?.value || "5m";
        const response = await fetch(`/api/signals?interval=${timeframe}`);
        const data = await response.json();

        if (data.error) {
            console.error("SIGNALS PAGE ERROR:", data.error);
            return;
        }

        document.getElementById("spot-price").innerText = Number(data.spot).toFixed(2);
        document.getElementById("atm-strike").innerText = data.atm;
        document.getElementById("last-update").innerText = data.last_update;

        renderSignalTable("ce-signals-body", data.ce_signals, "CE");
        renderSignalTable("pe-signals-body", data.pe_signals, "PE");
    }
    catch (error) {
        console.error("SIGNALS PAGE ERROR:", error);
    }
}

function renderSignalTable(bodyId, rows, optionType) {
    const tbody = document.getElementById(bodyId);
    if (!tbody) {
        return;
    }

    tbody.innerHTML = "";

    const sortedRows = rows.slice().sort((a, b) => {
        return b.oi_change - a.oi_change;
    });

    function fmtLtp(v){ return (v===null||v===undefined||isNaN(Number(v)))? '': Number(v).toFixed(2); }
    function fmtDelta(v){ return (v===null||v===undefined||isNaN(Number(v)))? '': Number(v).toFixed(5); }
    function fmtGamma(v){ return (v===null||v===undefined||isNaN(Number(v)))? '': Number(v).toFixed(4); }
    function withCommas(x){ return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
    function fmtOI(v){
        if (v===null||v===undefined||isNaN(Number(v))) return '';
        const n = Number(v);
        const abs = Math.abs(n);
        if (abs >= 10000000) { // crore
            return (n/10000000).toFixed(2) + ' cr';
        }
        if (abs >= 100000) { // lakh
            return (n/100000).toFixed(2) + ' L';
        }
        return withCommas(Math.round(n));
    }

    sortedRows.slice(0, 15).forEach(row => {
        const tr = document.createElement("tr");
        const formatted = {
            time: row.time || '',
            close_time: row.close_time || '',
            strike: row.strike || '',
            ltp: fmtLtp(row.ltp),
            delta: fmtDelta(row.delta),
            gamma: fmtGamma(row.gamma),
            oi_change: fmtOI(row.oi_change),
            buildup: row.buildup || '',
            signal: row.signal || '',
            profit: (row.profit !== null && row.profit !== undefined) ? Number(row.profit).toFixed(2) : '',
            status: row.status || ''
        };
        tr.innerHTML = `
            <td>${formatted.time}</td>
            <td>${formatted.close_time}</td>
            <td>${formatted.strike}</td>
            <td>${formatted.ltp}</td>
            <td>${formatted.delta}</td>
            <td>${formatted.gamma}</td>
            <td>${formatted.oi_change}</td>
            <td class="${getBuildClass(formatted.buildup, optionType)}">${formatted.buildup}</td>
            <td><button class="btn btn-sm btn-outline-light history-toggle">Show</button></td>
            <td>${formatted.signal}</td>
            <td class="${getProfitClass(formatted.profit)}">${formatted.profit}</td>
            <td class="${getSignalClass(formatted.status)}">${formatted.status}</td>
        `;
        tbody.appendChild(tr);

        // history row (hidden by default)
        const histTr = document.createElement('tr');
        const histTd = document.createElement('td');
        histTd.colSpan = 12;
        histTd.style.display = 'none';
        if (row.history && Array.isArray(row.history) && row.history.length > 0) {
            let inner = '<div class="history-table p-2"><table class="table table-sm table-dark mb-0"><thead><tr><th>Time</th><th>LTP</th><th>Delta</th><th>OI</th><th>Build-up</th></tr></thead><tbody>';
            row.history.forEach(h => {
                inner += `<tr><td>${h.time||''}</td><td>${fmtLtp(h.ltp)}</td><td>${fmtDelta(h.delta)}</td><td>${fmtOI(h.oi_change)}</td><td>${h.buildup||''}</td></tr>`;
            });
            inner += '</tbody></table></div>';
            histTd.innerHTML = inner;
        } else {
            histTd.innerHTML = '<div class="text-muted p-2">No history available</div>';
        }
        histTr.appendChild(histTd);
        tbody.appendChild(histTr);

        // toggle handler
        tr.querySelector('.history-toggle')?.addEventListener('click', function(){
            if (histTd.style.display === 'none') histTd.style.display = '';
            else histTd.style.display = 'none';
        });
    });
}

function getSignalClass(status) {
    if (status === "BUY CE" || status === "BUY PE") {
        return "badge-green";
    }
    if (status === "NO TRADE") {
        return "badge-yellow";
    }
    return "badge-blue";
}

function getProfitClass(profit) {
    if (profit === null || profit === undefined) return '';
    const p = Number(profit);
    if (isNaN(p)) return '';
    return p > 0 ? 'text-success' : (p < 0 ? 'text-danger' : '');
}

function getBuildClass(buildup, optionType) {
    if (optionType === "CE") {
        if (buildup === "Long Build-up" || buildup === "Short Covering") {
            return "bullish-build";
        }
        if (buildup === "Short Build-up" || buildup === "Long Unwinding") {
            return "bearish-build";
        }
    }
    if (optionType === "PE") {
        if (buildup === "Long Build-up" || buildup === "Short Covering") {
            return "bearish-build";
        }
        if (buildup === "Short Build-up" || buildup === "Long Unwinding") {
            return "bullish-build";
        }
    }
    return "";
}

window.addEventListener("DOMContentLoaded", () => {
    fetchSignalsData();
    document.getElementById("timeframe")?.addEventListener("change", fetchSignalsData);
    setInterval(fetchSignalsData, 5 * 60 * 1000);
});
