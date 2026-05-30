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

    // =====================================
    // CE LOGIC
    // =====================================

    if (optionType === "CE") {

        if (
            buildup.includes("Long Build")
            ||
            buildup.includes("Short Cover")
        ) {

            return "bullish-build";

        }

        if (
            buildup.includes("Short Build")
            ||
            buildup.includes("Long Unwind")
        ) {

            return "bearish-build";

        }

    }

    // =====================================
    // PE LOGIC
    // =====================================

    if (optionType === "PE") {

        if (
            buildup.includes("Short Build")
            ||
            buildup.includes("Long Unwind")
        ) {

            return "bullish-build";

        }

        if (
            buildup.includes("Long Build")
            ||
            buildup.includes("Short Cover")
        ) {

            return "bearish-build";

        }

    }

    return "";

}

function getPctClass(value) {

    if (value > 15) {

        return "pct-green";

    }

    if (value < -15) {

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
