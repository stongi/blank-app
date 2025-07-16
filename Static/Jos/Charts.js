document.addEventListener('DOMContentLoaded', function() {
    const ctx = document.getElementById('profitChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Profit 1 zi',
                    data: profit1d.map(d => ({ x: d.timestamp, y: d.balance })),
                    borderColor: 'blue',
                    fill: false
                },
                {
                    label: 'Profit 1 săptămână',
                    data: profit1w.map(d => ({ x: d.timestamp, y: d.balance })),
                    borderColor: 'green',
                    fill: false,
                    hidden: true
                },
                {
                    label: 'Profit 1 lună',
                    data: profit1m.map(d => ({ x: d.timestamp, y: d.balance })),
                    borderColor: 'red',
                    fill: false,
                    hidden: true
                }
            ]
        },
        options: {
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour'
                    }
                },
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: 'Balans (USDT)'
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    onClick: (e, legendItem, legend) => {
                        const index = legendItem.datasetIndex;
                        const ci = legend.chart;
                        ci.data.datasets.forEach((dataset, i) => {
                            dataset.hidden = i !== index;
                        });
                        ci.update();
                    }
                }
            }
        }
    });
});
