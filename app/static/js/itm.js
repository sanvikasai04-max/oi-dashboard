// =========================================
// FETCH ITM DATA
// =========================================

async function fetchITMData() {

    try {

        const timeframe =
            document.getElementById("timeframe").value;

        const response = await fetch(
            `/api/itm?interval=${timeframe}`
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

        document.getElementById("itm50-pe-strike").innerText =
            data.itm50;

        document.getElementById("itm100-ce-strike").innerText =
            data.itm100;

        document.getElementById("itm100-pe-strike").innerText =
            data.itm100;

        // =================================
        // TABLES
        // =================================

        fillTable(
            "itm50-ce-body",
            data.itm50_ce_data,
            "CE"
        );

        fillTable(
            "itm50-pe-body",
            data.itm50_pe_data,
            "PE"
        );

        fillTable(
            "itm100-ce-body",
            data.itm100_ce_data,
            "CE"
        );

        fillTable(
            "itm100-pe-body",
            data.itm100_pe_data,
            "PE"
        );

    }

    catch (error) {

        console.error(
            "ITM ERROR:",
            error
        );

    }

}

// =========================================
// FILL TABLE
// =========================================

function fillTable(bodyId, rows, optionType){

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
        fetchITMData
    );

// =========================================
// INITIAL LOAD
// =========================================

fetchITMData();

// =========================================
// AUTO REFRESH
// =========================================

setInterval(
    fetchITMData,
    5000
);
