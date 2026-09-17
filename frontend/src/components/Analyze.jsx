import React, { useEffect, useMemo, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { analyzePlaylist } from '../api';
import { buildChartData } from '../chartData';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);
ChartJS.defaults.font.family = "'Comic Sans MS', 'Trebuchet MS', Arial, sans-serif";
ChartJS.defaults.color = '#130014';

const emptyChart = { labels: [], datasets: [] };

function Analyze({ selectedPlaylists, onRemovePlaylist }) {
  const selectedPlaylistIds = useMemo(
    () => selectedPlaylists.map((playlist) => playlist.id),
    [selectedPlaylists],
  );
  const [chartData, setChartData] = useState(emptyChart);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('season');
  const [chartMode, setChartMode] = useState('compare');
  const [startDate, setStartDate] = useState('2022-09');
  const [startMode, setStartMode] = useState('earliest');

  const start = useMemo(
    () => (startMode === 'earliest' ? 'start' : startDate),
    [startMode, startDate],
  );

  useEffect(() => {
    let isCurrent = true;

    const loadChartData = async () => {
      if (selectedPlaylistIds.length === 0) {
        setChartData(emptyChart);
        setError(null);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const payload = {
          playlistIds: selectedPlaylistIds,
          viewMode,
          chartMode,
        };

        payload.start = start;

        const result = await analyzePlaylist(payload);
        if (isCurrent) {
          setChartData(buildChartData(result));
        }
      } catch (err) {
        if (isCurrent) {
          setError(err.message || 'Error loading data');
          setChartData(emptyChart);
        }
      } finally {
        if (isCurrent) {
          setLoading(false);
        }
      }
    };

    loadChartData();

    return () => {
      isCurrent = false;
    };
  }, [selectedPlaylistIds, viewMode, chartMode, start]);

  return (
    <section className="panel analysis-panel">
      <div className="analysis-header">
        <div>
          <h2>Track Add History</h2>
          <p>{selectedPlaylistIds.length} playlist{selectedPlaylistIds.length === 1 ? '' : 's'} selected</p>
        </div>
      </div>

      <div className="selected-chips">
        {selectedPlaylists.length === 0 ? (
          <span className="muted-text">Choose playlists from the left.</span>
        ) : (
          selectedPlaylists.map((playlist) => (
            <span className="playlist-chip" key={playlist.id}>
              <span>{playlist.name}</span>
              <button
                type="button"
                aria-label={`Remove ${playlist.name}`}
                onClick={() => onRemovePlaylist(playlist.id)}
              >
                x
              </button>
            </span>
          ))
        )}
      </div>

      <div className="control-grid">
        <div className="control-group">
          <span className="control-label">View by</span>
          <div className="segmented-control" aria-label="View by">
            <button
              type="button"
              aria-pressed={viewMode === 'month'}
              className={viewMode === 'month' ? 'active' : ''}
              onClick={() => setViewMode('month')}
            >
              Month
            </button>
            <button
              type="button"
              aria-pressed={viewMode === 'season'}
              className={viewMode === 'season' ? 'active' : ''}
              onClick={() => setViewMode('season')}
            >
              Season
            </button>
          </div>
        </div>

        <div className="control-group start-control">
          <span className="control-label">Start at</span>
          <div className="start-picker">
            <div className="segmented-control" aria-label="Start at">
              <button
                type="button"
                aria-pressed={startMode === 'earliest'}
                className={startMode === 'earliest' ? 'active' : ''}
              onClick={() => setStartMode('earliest')}
            >
                Earliest
              </button>
              <button
                type="button"
                aria-pressed={startMode === 'custom'}
                className={startMode === 'custom' ? 'active' : ''}
                onClick={() => setStartMode('custom')}
              >
                Custom
              </button>
            </div>
            {startMode === 'custom' && (
              <label className="month-picker">
                <span>Month</span>
                <input
                  type="month"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                />
              </label>
            )}
          </div>
        </div>

        <div className="control-group">
          <span className="control-label">Chart</span>
          <div className="segmented-control" aria-label="Chart mode">
            <button
              type="button"
              aria-pressed={chartMode === 'compare'}
              className={chartMode === 'compare' ? 'active' : ''}
              onClick={() => setChartMode('compare')}
            >
              Compare
            </button>
            <button
              type="button"
              aria-pressed={chartMode === 'sum'}
              className={chartMode === 'sum' ? 'active' : ''}
              onClick={() => setChartMode('sum')}
            >
              Total
            </button>
          </div>
        </div>
      </div>

      <div className="chart-frame">
        {selectedPlaylistIds.length === 0 && <p className="empty-state">Select one or more playlists to build a chart.</p>}
        {loading && <p className="empty-state">Loading chart...</p>}
        {error && <p className="error-text">Error: {error}</p>}
        {selectedPlaylistIds.length > 0 && !loading && !error && (
          <Bar
            data={chartData}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              interaction: {
                intersect: false,
                mode: 'index',
              },
              scales: {
                x: {
                  title: {
                    display: true,
                    text: viewMode === 'season' ? 'Season' : 'Month',
                  },
                },
                y: {
                  title: {
                    display: true,
                    text: 'Number of Tracks',
                },
                beginAtZero: true,
              },
            },
          }}
          />
        )}
      </div>
    </section>
  );
}

export default Analyze;
