console.log("GREEKS JS v20260606_3 LOADED");

let allEntrySignals = [];

async function fetchGreeksData(strike = null) {
    try {
        let url = "/api/greeks?interval=5m";
        if (strike) url += `&strike=${strike}`;

        const response = await fetch(url);
        const data = await response.json();

        if (data.error) {
            console.error(data.error);
            return;
        }

        document.getElementById("spot-price").innerText = Number(data.spot).toFixed(2);
        document.getElementById("opening-atm").innerText = data.opening_atm;

        populateStrikeDropdown(data.strike_options, data.strike);

        document.getElementById("ce-title").innerText =
            `CE Delta + Gamma Spikes (Strike ${data.strike})`;
        document.getElementById("pe-title").innerText =
            `PE Delta + Gamma Spikes (Strike ${data.strike})`;

        fillSpikeTable("ce-spikes-body", data.ce_spikes);
        fillSpikeTable("pe-spikes-body", data.pe_spikes);

        allEntrySignals = data.entry_signals || [];
        fillScorecard(data.entry_summary || {});
        applyEntryFilters();
    } catch (error) {
        console.error("Greeks Page Error:", error);
    }
}

function populateStrikeDropdown(strikes, selectedStrike) {
    const dropdown = document.getElementById("strike-select");
    dropdown.innerHTML = "";

    strikes.forEach(strike => {
        const option = document.createElement("option");
        option.value = strike;
        option.textContent = strike;
        if (Number(strike) === Number(selectedStrike)) option.selected = true;
        dropdown.appendChild(option);
    });

    dropdown.onchange = function () {
        fetchGreeksData(this.value);
    };
}

function fillSpikeTable(tbodyId, rows) {
    const tbody = document.getElementById(tbodyId);
    tbody.innerHTML = "";

    if (!rows || rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#6b7280;padding:20px;">No spikes found</td></tr>`;
        return;
    }

    rows.forEach(row => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${row.time}</td>
            <td>${row.ltp}</td>
            <td>${row.delta}</td>
            <td>${row.delta_change}%</td>
            <td>${row.gamma}</td>
            <td>${row.gamma_change}%</td>
        `;
        tbody.appendChild(tr);
    });
}

function fillScorecard(s) {
    document.getElementById("esc-total").innerText = s.total ?? "--";
    document.getElementById("esc-hits").innerText = s.target_hits ?? "--";
    document.getElementById("esc-sl").innerText = s.sl_hits ?? "--";
    document.getElementById("esc-delta").innerText = s.delta_exits ?? "--";
    document.getElementById("esc-open").innerText = s.open ?? "--";

    const pnl = s.net_pnl_pct ?? null;
    const pnlEl = document.getElementById("esc-pnl");

    if (pnl !== null) {
        pnlEl.innerText = (pnl >= 0 ? "+" : "") + pnl + "%";
        pnlEl.style.color = pnl >= 0 ? "#22c55e" : "#ef4444";
    } else {
        pnlEl.innerText = "--";
        pnlEl.style.color = "#f9fafb";
    }
}

function applyEntryFilters() {
    const setupFilter = document.getElementById("filter-setup").value;
    const outcomeFilter = document.getElementById("filter-outcome").value;

    let rows = allEntrySignals;

    if (setupFilter !== "all") {
        rows = rows.filter(row => row.setup === setupFilter);
    }

    if (outcomeFilter !== "all") {
        rows = rows.filter(row => row.outcome === outcomeFilter);
    }

    renderEntryTable(rows);
}

function renderEntryTable(rows) {
    const tbody = document.getElementById("entry-signals-body");

    if (!rows || rows.length === 0) {
        tbody.innerHTML = `
            <tr><td colspan="19" style="text-align:center;color:#6b7280;padding:30px;">
                No signals match the selected filters.
            </td></tr>`;
        return;
    }

    tbody.innerHTML = "";

    rows.forEach(row => {
        const tr = document.createElement("tr");

        if (row.outcome === "Target Hit") tr.classList.add("erow-target");
        else if (row.outcome === "SL Hit") tr.classList.add("erow-sl");
        else if (row.outcome === "Open") tr.classList.add("erow-open");

        const pnlLabel = row.outcome === "Open"
            ? `<span class="pnl-n">open</span>`
            : `<span class="${pnlClass(row.pnl_pct)}">${row.pnl_pct >= 0 ? "+" : ""}${row.pnl_pct}%</span>`;

        tr.innerHTML = `
            <td style="font-size:11px">${row.time}</td>
            <td><span class="setup-badge ${setupClass(row.setup)}">${row.setup}</span></td>
            <td><span class="score-badge ${scoreClass(row.score)}">${row.score} ${row.confidence || ""}</span></td>
            <td><strong>${row.entry_ltp}</strong></td>
            <td style="color:#ef4444">${row.sl}</td>
            <td style="color:#22c55e">${row.target}</td>
            <td>${row.delta}</td>
            <td class="${pctCls(row.delta_chg)}">${signedPct(row.delta_chg)}</td>
            <td>${row.gamma}</td>
            <td class="${pctCls(row.gamma_chg)}">${signedPct(row.gamma_chg)}</td>
            <td style="font-size:11px">${row.buildup}</td>
            <td class="${pctCls(row.oi_change)}">${formatOI(row.oi_change)}</td>
            <td class="${pctCls(row.oi_change_pct)}">${signedPct(row.oi_change_pct)}</td>
            <td class="${pctCls(row.price_change)}">${signedNumber(row.price_change)}</td>
            <td style="font-size:11px;color:#9ca3af">${row.reason || "--"}</td>
            <td>${outcomeBadge(row.outcome)}</td>
            <td>${row.exit_ltp !== null ? row.exit_ltp : "--"}</td>
            <td style="color:#9ca3af; font-size:11px">${row.exit_time || "--"}</td>
            <td>${pnlLabel}</td>
        `;

        tbody.appendChild(tr);
    });
}

function setupClass(setup) {
    if (setup === "CE Long") return "sb-ce-long";
    if (setup === "PE Long") return "sb-pe-long";
    if (setup === "CE Short Cover") return "sb-ce-cover";
    if (setup === "PE Short Cover") return "sb-pe-cover";
    return "";
}

function outcomeBadge(outcome) {
    if (outcome === "Target Hit") return `<span class="outcome-badge ob-target">Target</span>`;
    if (outcome === "SL Hit") return `<span class="outcome-badge ob-sl">SL</span>`;
    if (outcome === "Delta Exit") return `<span class="outcome-badge ob-delta">Delta</span>`;
    if (outcome === "Open") return `<span class="outcome-badge ob-open">Open</span>`;
    return outcome;
}

function scoreClass(score) {
    return Number(score) >= 85 ? "score-high" : "score-med";
}

function pctCls(value) {
    const n = Number(value);
    if (n > 0) return "pct-green";
    if (n < 0) return "pct-red";
    return "pct-neutral";
}

function pnlClass(value) {
    const n = Number(value);
    if (n > 0) return "pnl-g";
    if (n < 0) return "pnl-r";
    return "pnl-n";
}

function signedPct(value) {
    const n = Number(value);
    if (Number.isNaN(n)) return "--";
    return `${n > 0 ? "+" : ""}${n}%`;
}

function signedNumber(value) {
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

document.getElementById("filter-setup").addEventListener("change", applyEntryFilters);
document.getElementById("filter-outcome").addEventListener("change", applyEntryFilters);

window.addEventListener("DOMContentLoaded", () => {
    fetchGreeksData();
});
