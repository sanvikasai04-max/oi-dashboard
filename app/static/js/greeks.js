console.log("NEW GREEKS JS LOADED");
async function fetchGreeksData(strike = null) {

    try {

        let url = "/api/greeks?interval=5m";

        if (strike) {
            url += `&strike=${strike}`;
        }

        const response = await fetch(url);

        const data = await response.json();

        if (data.error) {
            console.error(data.error);
            return;
        }

        document.getElementById("spot-price").innerText =
            Number(data.spot).toFixed(2);

        document.getElementById("opening-atm").innerText =
            data.opening_atm;

        populateStrikeDropdown(
            data.strike_options,
            data.strike
        );

        fillSpikeTable(
            "ce-spikes-body",
            data.ce_spikes
        );

        fillSpikeTable(
            "pe-spikes-body",
            data.pe_spikes
        );

    }
    catch (error) {

        console.error(
            "Greeks Page Error:",
            error
        );

    }

}

function populateStrikeDropdown(
    strikes,
    selectedStrike
) {

    const dropdown =
        document.getElementById(
            "strike-select"
        );

    dropdown.innerHTML = "";

    strikes.forEach(strike => {

        const option =
            document.createElement(
                "option"
            );
        console.log("Dropdown found:", dropdown);
        console.log("Strikes:", strikes);
        option.value = strike;
        option.textContent = strike;

        if (
            Number(strike) === Number(selectedStrike)
        ) {
            option.selected = true;
        }

        dropdown.appendChild(option);

    });

    dropdown.onchange = function() {

        fetchGreeksData(
            this.value
        );

    };

}

function fillSpikeTable(
    tbodyId,
    rows
) {

    const tbody =
        document.getElementById(
            tbodyId
        );

    tbody.innerHTML = "";

    if (!rows || rows.length === 0) {

        tbody.innerHTML = `
            <tr>
                <td colspan="6">
                    No spikes found
                </td>
            </tr>
        `;

        return;

    }

    rows.forEach(row => {

        const tr =
            document.createElement(
                "tr"
            );

        tr.innerHTML = `
            <td>${row.time}</td>
            <td>${row.ltp}</td>
            <td>${row.delta}</td>
            <td>${row.delta_change}%</td>
            <td>${row.gamma}</td>
            <td>${row.gamma_change}%</td>
        `;

        tbody.appendChild(
            tr
        );

    });

}

window.addEventListener(
    "DOMContentLoaded",
    () => {
        fetchGreeksData();
    }
);