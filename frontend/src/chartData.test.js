import { describe, expect, it } from 'vitest';

import { buildChartData } from './chartData';

describe('buildChartData', () => {
  it('preserves values and assigns a distinct color to each dataset', () => {
    const result = buildChartData({
      labels: ['2026-01'],
      datasets: [
        { label: 'One', data: [1] },
        { label: 'Two', data: [2] },
      ],
    });

    expect(result.labels).toEqual(['2026-01']);
    expect(result.datasets[0].data).toEqual([1]);
    expect(result.datasets[0].backgroundColor).not.toBe(result.datasets[1].backgroundColor);
  });

  it('handles an empty response', () => {
    expect(buildChartData({})).toEqual({ labels: [], datasets: [] });
  });
});
