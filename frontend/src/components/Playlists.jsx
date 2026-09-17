import React, { useMemo, useState } from 'react';

function playlistMatches(playlist, query) {
  const normalizedQuery = query.trim().toLowerCase();

  if (!normalizedQuery) return true;

  return [playlist.name, playlist.ownerName]
    .filter(Boolean)
    .some((value) => value.toLowerCase().includes(normalizedQuery));
}

function Playlists({ playlists, loading, error, selectedPlaylistIds, onTogglePlaylist }) {
  const [query, setQuery] = useState('');

  const filteredPlaylists = useMemo(
    () => playlists.filter((playlist) => playlistMatches(playlist, query)),
    [playlists, query],
  );
  const filteredPlaylistIds = useMemo(
    () => filteredPlaylists.map((playlist) => playlist.id),
    [filteredPlaylists],
  );

  return (
    <aside className="panel playlist-panel">
      <div className="panel-heading">
        <div>
          <h2>Playlists</h2>
          <p>{selectedPlaylistIds.length} selected</p>
        </div>
      </div>

      <input
        className="playlist-search"
        type="search"
        placeholder="Search playlists"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />

      {loading && <p className="muted-text">Loading playlists...</p>}
      {error && <p className="error-text">{error}</p>}
      {!loading && !error && filteredPlaylists.length === 0 && (
        <p className="muted-text">No playlists match that search.</p>
      )}

      <div className="playlist-list">
        {filteredPlaylists.map((playlist) => {
          const imageLabel = playlist.name.slice(0, 1).toUpperCase();

          return (
            <button
              className="playlist-row"
              key={playlist.id}
              type="button"
              aria-pressed={selectedPlaylistIds.includes(playlist.id)}
              onClick={(event) => onTogglePlaylist(playlist.id, filteredPlaylistIds, event.shiftKey)}
            >
              {playlist.imageUrl ? (
                <img src={playlist.imageUrl} alt="" className="playlist-art" />
              ) : (
                <span className="playlist-art fallback-art">{imageLabel}</span>
              )}
              <span className="playlist-copy">
                <span className="playlist-name">{playlist.name}</span>
                <span className="playlist-meta">
                  {playlist.ownerName} / {playlist.trackCount} tracks
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

export default Playlists;
