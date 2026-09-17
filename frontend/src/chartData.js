const CHART_COLORS = [
  '#7d63e6',
  '#d88a35',
  '#389280',
  '#cf5870',
  '#5f82d2',
  '#a06a35',
  '#925fbd',
  '#71923b',
  '#b85ba3',
  '#4a94ba',
  '#b2733d',
  '#7a7be0',
  '#a57b38',
  '#40949a',
  '#bb6380',
  '#826cb8',
];

function colorForDataset(index) {
  if (index < CHART_COLORS.length) {
    return CHART_COLORS[index];
  }

  const hue = (index * 137.508 + 34) % 360;
  const saturation = index % 2 === 0 ? 64 : 56;
  const lightness = index % 3 === 0 ? 52 : 60;
  return `hsl(${hue} ${saturation}% ${lightness}%)`;
}

export function buildChartData(rawData) {
  const labels = rawData.labels || [];
  const datasets = rawData.datasets || [];

  return {
    labels,
    datasets: datasets.map((dataset, index) => {
      const color = colorForDataset(index);

      return {
        ...dataset,
        backgroundColor: color,
        borderColor: '#130014',
        borderWidth: 1.3,
      };
    }),
  };
}
