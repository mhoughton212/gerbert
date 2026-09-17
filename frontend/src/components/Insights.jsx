import React, { useEffect, useMemo, useState } from 'react';
import { getInsights, getWrapped } from '../api';

const emptyInsights = null;
const emptyWrapped = null;

function formatNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function formatSigned(value) {
  if (!value) return '0';
  return value > 0 ? `+${value}` : String(value);
}

function formatTrend(trend) {
  if (!trend) return 'No trend yet';
  return `Recent pace: ${formatRate(trend.recentAverage)}/mo`;
}

function pluralizePlaylist(count) {
  return `${count} playlist${count === 1 ? '' : 's'}`;
}

function formatRate(value) {
  return Number(value || 0).toLocaleString(undefined, {
    maximumFractionDigits: 1,
  });
}

function articleForNumber(value) {
  const rate = formatRate(value).replace(/,/g, '');

  if (rate.startsWith('8') || rate.startsWith('11') || rate.startsWith('18')) {
    return 'an';
  }

  return 'a';
}

function ratePace(value, qualifier) {
  const suffix = qualifier ? ` ${qualifier}` : '';
  return `${articleForNumber(value)} ${formatRate(value)}/month${suffix} pace`;
}

function trendStatus(trend) {
  if (!trend) return 'No trend yet';
  return trend.longTermDirection || trend.label;
}

function trendSlug(trend) {
  return trendStatus(trend).toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

const TREND_DESCRIPTIONS = {
  Increasing: 'The overall add-history trend slopes upward across completed months.',
  Decreasing: 'The overall add-history trend slopes downward across completed months.',
  Flat: 'The overall add-history trend is roughly level across completed months.',
  Irregular: 'The overall history does not fit a clear upward, downward, or flat trend.',
  'Not enough history': 'There is not enough history to classify the long-term direction.',
  'Active recently': "The last three months are above this playlist's normal pace.",
  'Quiet recently': "The last three months are below this playlist's normal pace.",
  'Typical recently': "The last three months are close to this playlist's normal pace.",
  Revived: 'Recent activity returned after a quiet prior window.',
  Dormant: 'There have been no recent adds for a long stretch.',
  'Early spike': 'A large share of adds happened near the beginning.',
  'Spike-driven': 'Activity is concentrated in a few large add months.',
  Steady: 'Adds are spread across many active months without one dominant spike.',
  Mixed: 'The playlist has multiple activity phases without one simple shape.',
};

function trendDescription(label) {
  if (label === 'Active recently') {
    return "The last three months are above this playlist's normal pace.";
  }

  if (label === 'Quiet recently') {
    return "The last three months are below this playlist's normal pace.";
  }

  if (label === 'Typical recently') {
    return "The last three months are close to this playlist's normal pace.";
  }

  return TREND_DESCRIPTIONS[label] || 'Playlist activity classification.';
}

function InfoPill({ children, className = '', description }) {
  const [tooltipPosition, setTooltipPosition] = useState(null);

  const showTooltip = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const tooltipWidth = 230;
    const viewportPadding = 12;
    const left = Math.min(
      Math.max(rect.left + rect.width / 2, viewportPadding + tooltipWidth / 2),
      window.innerWidth - viewportPadding - tooltipWidth / 2,
    );

    setTooltipPosition({
      left,
      top: rect.top - 8,
    });
  };

  const hideTooltip = () => setTooltipPosition(null);

  return (
    <span
      className={`info-pill ${className}`}
      onBlur={hideTooltip}
      onClick={(event) => {
        if (tooltipPosition) {
          hideTooltip();
        } else {
          showTooltip(event);
        }
      }}
      onFocus={showTooltip}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      tabIndex={0}
    >
      {children}
      {tooltipPosition && (
        <span
          className="pill-tooltip"
          role="tooltip"
          style={{
            left: `${tooltipPosition.left}px`,
            top: `${tooltipPosition.top}px`,
          }}
        >
          {description}
        </span>
      )}
    </span>
  );
}

function trendSentence(trend) {
  const direction = trend?.longTermDirection || trend?.label;
  if (!trend || direction === 'Not enough history') {
    return 'Not enough history for a clean trend yet.';
  }

  const launch = formatRate(trend.launchAverage);
  const baseline = formatRate(trend.baselineAverage);
  const recent = formatRate(trend.recentAverage);
  const previous = formatRate(trend.previousAverage);

  if (direction === 'Decreasing') {
    return `Long-term activity is decreasing; recent pace is ${recent}/month versus ${ratePace(trend.baselineAverage, 'lifetime')}.`;
  }

  if (direction === 'Increasing') {
    return `Long-term activity is increasing; recent pace is ${recent}/month versus ${ratePace(trend.baselineAverage, 'lifetime')}.`;
  }

  if (direction === 'Flat') {
    return `Long-term activity is mostly flat around ${baseline} adds/month.`;
  }

  if (trend.recentActivity === 'Revived') {
    return `Recent pace rose to ${recent}/month after ${previous}/month in the previous window.`;
  }

  if (trend.shape === 'Early spike') {
    return `Launch pace was ${launch}/month; recent pace is ${recent}/month.`;
  }

  if (trend.shape === 'Spike-driven') {
    return `Activity is concentrated in a few large add months.`;
  }

  return `Long-term activity is irregular; recent pace is ${recent}/month versus ${ratePace(trend.baselineAverage, 'lifetime')}.`;
}

function peakFacts(playlist) {
  const season = playlist.mostActiveSeason;
  const spike = playlist.biggestSpike;

  return [
    {
      label: 'Peak season',
      value: season?.label ? `${season.label} (${season.count} adds)` : 'No clear season',
    },
    {
      label: 'Peak month',
      value: spike?.label ? `${spike.label} (${spike.count} adds)` : 'No clear month',
    },
  ];
}

function RankingCard({ title, insight, detail }) {
  if (!insight) {
    return (
      <article className="insight-card">
        <span className="insight-label">{title}</span>
        <strong>Not enough data</strong>
      </article>
    );
  }

  return (
    <article className="insight-card">
      <span className="insight-label">{title}</span>
      <strong>{insight.name}</strong>
      <small>{detail(insight)}</small>
    </article>
  );
}

function artistLine(track) {
  return (track.artists || []).join(', ') || 'Unknown artist';
}

function rangeLabel(timeRange) {
  if (timeRange === 'short_term') return 'current';
  if (timeRange === 'long_term') return 'long-term';
  return timeRange;
}

function WrappedTrackList({ title, tracks, emptyText }) {
  return (
    <div className="wrapped-list">
      <h4>{title}</h4>
      {tracks.length > 0 ? (
        <ol>
          {tracks.map((track) => (
            <li key={`${track.timeRange}-${track.id}`}>
              {track.imageUrl && <img src={track.imageUrl} alt="" />}
              <span>
                <strong>{track.name}</strong>
                <small>#{track.rank} in your {rangeLabel(track.timeRange)} top tracks - {artistLine(track)}</small>
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="wrapped-empty">{emptyText}</p>
      )}
    </div>
  );
}

function WrappedArtistList({ artists }) {
  return (
    <div className="wrapped-list">
      <h4>Artist Gravity</h4>
      {artists.length > 0 ? (
        <ol>
          {artists.map((artist) => (
            <li key={artist.id}>
              {artist.imageUrl && <img src={artist.imageUrl} alt="" />}
              <span>
                <strong>{artist.name}</strong>
                <small>
                  #{artist.rank} top artist - {artist.playlistTrackCount} playlist track{artist.playlistTrackCount === 1 ? '' : 's'}
                </small>
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="wrapped-empty">No top-artist overlap in this playlist.</p>
      )}
    </div>
  );
}

function WrappedSection({ wrapped, loading, error }) {
  if (loading) {
    return <p className="empty-state compact-empty">Checking top-track overlap...</p>;
  }

  if (error) {
    return <p className="wrapped-error">{error}</p>;
  }

  if (!wrapped || wrapped.playlists.length === 0) {
    return null;
  }

  return (
    <section className="wrapped-section">
      <div className="wrapped-heading">
        <h3>Wrapped-ish</h3>
        <p>Spotify top tracks and artists that also appear in selected playlists.</p>
      </div>

      {wrapped.playlists.map((playlist) => (
        <article className="wrapped-card" key={playlist.playlistId}>
          <div className="wrapped-card-head">
            <strong>{playlist.name}</strong>
            <span>{playlist.tasteMatch.shortTermMatched} / {playlist.tasteMatch.topTrackLimit} current match</span>
          </div>

          <div className="wrapped-match-grid">
            <div>
              <span>Current Favorites</span>
              <strong>{playlist.tasteMatch.shortTermMatched}</strong>
              <small>of your top {playlist.tasteMatch.topTrackLimit}</small>
            </div>
            <div>
              <span>All-Time-ish Favorites</span>
              <strong>{playlist.tasteMatch.longTermMatched}</strong>
              <small>of your top {playlist.tasteMatch.topTrackLimit}</small>
            </div>
          </div>

          <WrappedTrackList
            title="Current Favorites"
            tracks={playlist.currentFavorites}
            emptyText="None of your current top tracks are in this playlist."
          />
          <WrappedTrackList
            title="All-Time-ish Favorites"
            tracks={playlist.allTimeFavorites}
            emptyText="None of your long-term top tracks are in this playlist."
          />
          <WrappedArtistList artists={playlist.artistGravity} />
        </article>
      ))}
    </section>
  );
}

function InsightsBody({ insights, wrapped, wrappedLoading, wrappedError }) {
  if (!insights) {
    return <p className="empty-state compact-empty">Select playlists to generate insights.</p>;
  }

  const { summary, rankings, playlists } = insights;

  return (
    <div className="insights-view">
      <div className="insight-summary-grid">
        <article className="insight-card">
          <span className="insight-label">Last 90 days</span>
          <strong>{formatNumber(summary.addsLast90Days)}</strong>
          <small>{formatSigned(summary.momentumDelta)} vs previous 90 across {pluralizePlaylist(summary.playlistCount)}</small>
        </article>
      </div>

      <div className="insight-rankings">
        <RankingCard
          title="Most recent activity"
          insight={rankings.mostRecentlyActive}
          detail={(item) => `${item.daysSinceLastAdd} days since last add`}
        />
        <RankingCard
          title="Most dormant"
          insight={rankings.mostDormant}
          detail={(item) => `${item.daysSinceLastAdd} days since last add`}
        />
        <RankingCard
          title="Biggest recent increase"
          insight={rankings.biggestRecentMomentum}
          detail={(item) => `${formatSigned(item.momentumDelta)} tracks vs previous 90`}
        />
        <RankingCard
          title="Biggest falloff"
          insight={rankings.biggestFalloff}
          detail={(item) => formatTrend(item.monthlyTrend)}
        />
        <RankingCard
          title="Biggest monthly spike"
          insight={rankings.biggestSpike}
          detail={(item) => `${item.biggestSpike.count} tracks in ${item.biggestSpike.label}`}
        />
        <RankingCard
          title="Most consistent"
          insight={rankings.mostConsistent}
          detail={(item) => `${Math.round(item.consistencyScore * 100)}% of active span months touched`}
        />
      </div>

      <WrappedSection wrapped={wrapped} loading={wrappedLoading} error={wrappedError} />

      <div className="playlist-insight-table">
        {playlists.map((playlist) => (
          <article className="playlist-insight-row" key={playlist.playlistId}>
            <div className="playlist-insight-head">
              <div className="playlist-insight-title">
                <strong>{playlist.name}</strong>
                <InfoPill
                  className={`trend-pill trend-${trendSlug(playlist.monthlyTrend)}`}
                  description={trendDescription(trendStatus(playlist.monthlyTrend))}
                >
                  {trendStatus(playlist.monthlyTrend)}
                </InfoPill>
              </div>
              <p className="playlist-insight-summary">{trendSentence(playlist.monthlyTrend)}</p>
              <div className="trend-tags" aria-label="Supporting classifications">
                <span>Recent</span>
                <InfoPill description={trendDescription(playlist.monthlyTrend.recentActivity)}>
                  {playlist.monthlyTrend.recentActivity}
                </InfoPill>
                <span>Shape</span>
                <InfoPill description={trendDescription(playlist.monthlyTrend.shape)}>
                  {playlist.monthlyTrend.shape}
                </InfoPill>
              </div>
              <dl className="playlist-insight-facts">
                {peakFacts(playlist).map((fact) => (
                  <div key={fact.label}>
                    <dt>{fact.label}</dt>
                    <dd>{fact.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <dl className="playlist-insight-stats">
              <div>
                <dt>Recent additions</dt>
                <dd>{playlist.addsLast90Days} tracks</dd>
              </div>
              <div>
                <dt>Current pace</dt>
                <dd>{formatRate(playlist.monthlyTrend.recentAverage)} adds/month</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}

function Insights({ selectedPlaylists }) {
  const selectedPlaylistIds = useMemo(
    () => selectedPlaylists.map((playlist) => playlist.id),
    [selectedPlaylists],
  );
  const [insights, setInsights] = useState(emptyInsights);
  const [wrapped, setWrapped] = useState(emptyWrapped);
  const [loading, setLoading] = useState(false);
  const [wrappedLoading, setWrappedLoading] = useState(false);
  const [error, setError] = useState(null);
  const [wrappedError, setWrappedError] = useState(null);

  useEffect(() => {
    let isCurrent = true;

    if (selectedPlaylistIds.length === 0) {
      const clearSelection = async () => {
        await Promise.resolve();
        if (!isCurrent) return;
        setInsights(emptyInsights);
        setWrapped(emptyWrapped);
        setError(null);
        setWrappedError(null);
        setLoading(false);
        setWrappedLoading(false);
      };
      clearSelection();
      return () => {
        isCurrent = false;
      };
    }

    setLoading(true);
    setWrappedLoading(true);
    setError(null);
    setWrappedError(null);

    const loadInsights = async () => {
      try {
        const nextInsights = await getInsights({ playlistIds: selectedPlaylistIds });
        if (isCurrent) setInsights(nextInsights);
      } catch (err) {
        if (isCurrent) {
          setError(err.message || 'Error loading insights');
          setInsights(emptyInsights);
        }
      } finally {
        if (isCurrent) setLoading(false);
      }
    };

    const loadWrapped = async () => {
      try {
        const nextWrapped = await getWrapped({ playlistIds: selectedPlaylistIds });
        if (isCurrent) setWrapped(nextWrapped);
      } catch (err) {
        if (isCurrent) {
          setWrappedError(err.message || 'Error loading Wrapped-ish data');
          setWrapped(emptyWrapped);
        }
      } finally {
        if (isCurrent) setWrappedLoading(false);
      }
    };

    loadInsights();
    loadWrapped();

    return () => {
      isCurrent = false;
    };
  }, [selectedPlaylistIds]);

  return (
    <aside className="panel insights-panel">
      <div className="panel-heading">
        <div>
          <h2>Insights</h2>
          <p>{selectedPlaylistIds.length} playlist{selectedPlaylistIds.length === 1 ? '' : 's'} selected</p>
        </div>
      </div>

      <div className="insights-scroll">
        {loading && <p className="empty-state compact-empty">Finding patterns...</p>}
        {error && <p className="error-text">Error: {error}</p>}
        {!loading && !error && (
          <InsightsBody
            insights={insights}
            wrapped={wrapped}
            wrappedLoading={wrappedLoading}
            wrappedError={wrappedError}
          />
        )}
      </div>
    </aside>
  );
}

export default Insights;
