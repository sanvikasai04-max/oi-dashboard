// =========================================
// FETCH DASHBOARD DATA
// =========================================

async function fetchDashboardData() {

    try {

        const timeframe =
            document.getElementById("timeframe").value;

        const response = await fetch(
            `/api/dashboard?interval=${timeframe}`
        );

        const data = await response.json();

        // =================================
        // SPOT
        // =================================

        document.getElementById(
            "spot-price"
        ).innerText = Number(data.spot).toFixed(2);

        // =================================
        // LAST UPDATE DATE
        // =================================

        console.log("API Response:", data);
        console.log("data_date:", data.data_date);
        console.log("earliest_update:", data.earliest_update);
        console.log("last_update:", data.last_update);

        if (data.data_date) {
            document.getElementById(
                "last-update"
            ).innerText = data.data_date;
        } else if (data.earliest_update && data.last_update) {
            try {
                const earliestDate = new Date(data.earliest_update);
                const latestDate = new Date(data.last_update);
                console.log("Parsed dates:", earliestDate, latestDate);

                if (Number.isNaN(earliestDate.getTime()) || Number.isNaN(latestDate.getTime())) {
                    throw new Error("Invalid date value");
                }

                const earliestFormatted = earliestDate.toLocaleString();
                const latestFormatted = latestDate.toLocaleString();
                document.getElementById(
                    "last-update"
                ).innerText = `${earliestFormatted} to ${latestFormatted}`;
            } catch (e) {
                console.error("Date parsing error:", e);
            }
        } else {
            console.warn("No dates found in response");
        }

        document.getElementById("atm-ce-strike").innerText =
            data.atm;

        document.getElementById("atm-pe-strike").innerText =
            data.atm;

        document.getElementById("otm-ce-strike").innerText =
            data.otm;

        document.getElementById("otm-pe-strike").innerText =
            data.otm;

        // =================================
        // TABLES
        // =================================

        fillTable(
            "atm-ce-body",
            data.atm_ce_data,
            "CE"
        );

        fillTable(
            "atm-pe-body",
            data.atm_pe_data,
            "PE"
        );

        fillTable(
            "otm-ce-body",
            data.otm_ce_data,
            "CE"
        );

        fillTable(
            "otm-pe-body",
            data.otm_pe_data,
            "PE"
        );

    }

    catch (error) {

        console.error(
            "DASHBOARD ERROR:",
            error
        );

    }

}

// =========================================
// FILL TABLE
// =========================================

function fillTable(bodyId, rows, optionType) {

    const tbody =
        document.getElementById(bodyId);

    tbody.innerHTML = "";

    rows.forEach(row => {

        const tr =
            document.createElement("tr");

        tr.innerHTML = `

            <td>${row.time}</td>

            <td class="${getBuildClass(row.buildup, optionType)}">
                ${row.buildup}
            </td>

            <td>${row.volume}</td>

            <td>
                ${formatOIChange(row.oi_change)}
                <br>
                <span class="${getPctClass(row.fresh_entry_ratio)}">
                    (${row.fresh_entry_ratio}%)
                </span>
            </td>

           <td>

                ${row.delta}

                <br>

                <span class="${getPctClass(row.delta_change)}">

                    (${row.delta_change}%)

                </span>

            </td>
            <td>

                ${row.gamma}

                <br>

                <span class="${getPctClass(row.gamma_change)}">

                    (${row.gamma_change}%)

                </span>

            </td>

            <td>

                ${row.iv}

                <br>

                <span class="${getPctClass(row.iv_change)}">

                    (${row.iv_change}%)

                </span>

            </td>

        `;

        tbody.appendChild(tr);

    });

}

// =========================================
// BUILDUP COLORS
// =========================================

function getBuildClass(buildup, optionType) {

    if (optionType === "CE") {

        if (buildup === "Long Build-up") {
            return "bullish-build";
        }

        if (buildup === "Short Covering") {
            return "bullish-build";
        }

        if (buildup === "Short Build-up") {
            return "bearish-build";
        }

        if (buildup === "Long Unwinding") {
            return "bearish-build";
        }

    }

    if (optionType === "PE") {

        if (buildup === "Long Build-up") {
            return "bearish-build";
        }

        if (buildup === "Short Covering") {
            return "bearish-build";
        }

        if (buildup === "Short Build-up") {
            return "bullish-build";
        }

        if (buildup === "Long Unwinding") {
            return "bullish-build";
        }

    }

    return "";

}

function formatOIChange(value) {

    const num = Number(value);

    if (Number.isNaN(num)) {
        return value;
    }

    const absValue = Math.abs(num);
    let formatted;

    if (absValue >= 1e7) {
        formatted = `${(num / 1e7).toFixed(2).replace(/\.00$|\.?0+$/, '')} cr`;
    } else if (absValue >= 1e5) {
        formatted = `${(num / 1e5).toFixed(2).replace(/\.00$|\.?0+$/, '')} lakh`;
    } else {
        formatted = num.toString();
    }

    return formatted;
}

function getPctClass(value) {

    const numericValue = Number(value);

    if (numericValue > 0) {

        return "pct-green";

    }

    if (numericValue < 0) {

        return "pct-red";

    }

    return "pct-neutral";

}

// =========================================
// TIMEFRAME CHANGE
// =========================================

document
    .getElementById("timeframe")
    .addEventListener(
        "change",
        fetchDashboardData
    );

// =========================================
// INITIAL LOAD
// =========================================

fetchDashboardData();

// =========================================
// AUTO REFRESH
// =========================================

setInterval(
    fetchDashboardData,
    5000
);
