import React, { useState, useEffect } from 'react';
import Login from './components/Login';
import Playlists from './components/Playlists';
import Analyze from './components/Analyze';
import Insights from './components/Insights';
import { getPlaylists, getSession, logout } from './api';
import './App.css';

function App() {
  const [playlists, setPlaylists] = useState([]);
  const [selectedPlaylistIds, setSelectedPlaylistIds] = useState([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [loadingPlaylists, setLoadingPlaylists] = useState(false);
  const [playlistError, setPlaylistError] = useState(null);
  const [lastSelectedPlaylistId, setLastSelectedPlaylistId] = useState(null);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const session = await getSession();
        setIsAuthenticated(session.authenticated);
      } catch (error) {
        setIsAuthenticated(false);
      } finally {
        setCheckingSession(false);
      }
    };

    checkAuth();
  }, []);

  useEffect(() => {
    const loadPlaylists = async () => {
      if (!isAuthenticated) return;

      setLoadingPlaylists(true);
      setPlaylistError(null);

      try {
        const data = await getPlaylists();
        setPlaylists(data);
      } catch (error) {
        setPlaylistError(error.message || 'Could not load playlists');
      } finally {
        setLoadingPlaylists(false);
      }
    };

    loadPlaylists();
  }, [isAuthenticated]);

  const handleLogout = async () => {
    await logout().catch(() => null);
    setIsAuthenticated(false);
    setSelectedPlaylistIds([]);
    setPlaylists([]);
  };

  const handleTogglePlaylist = (playlistId, visiblePlaylistIds = [], shiftKey = false) => {
    setSelectedPlaylistIds((prev) => {
      if (shiftKey && lastSelectedPlaylistId && visiblePlaylistIds.includes(lastSelectedPlaylistId)) {
        const startIndex = visiblePlaylistIds.indexOf(lastSelectedPlaylistId);
        const endIndex = visiblePlaylistIds.indexOf(playlistId);
        const [start, end] = [startIndex, endIndex].sort((a, b) => a - b);
        const rangeIds = visiblePlaylistIds.slice(start, end + 1);
        const shouldSelectRange = !prev.includes(playlistId);

        if (shouldSelectRange) {
          return Array.from(new Set([...prev, ...rangeIds]));
        }

        return prev.filter((id) => !rangeIds.includes(id));
      }

      if (prev.includes(playlistId)) {
        return prev.filter((id) => id !== playlistId);
      }

      return [...prev, playlistId];
    });
    if (!shiftKey || !lastSelectedPlaylistId || !visiblePlaylistIds.includes(lastSelectedPlaylistId)) {
      setLastSelectedPlaylistId(playlistId);
    }
  };

  const handleRemovePlaylist = (playlistId) => {
    setSelectedPlaylistIds((prev) => prev.filter((id) => id !== playlistId));
  };

  const selectedPlaylists = playlists.filter((playlist) => selectedPlaylistIds.includes(playlist.id));

  if (checkingSession) {
    return <main className="app-shell">Loading...</main>;
  }

  return (
    <main className="app-shell">
      {!isAuthenticated ? (
        <Login />
      ) : (
        <>
          <header className="app-header">
            <div>
              <h1>Gerbert</h1>
              <p>Playlist add-history charts from your Spotify library</p>
            </div>
            <button onClick={handleLogout}>Logout</button>
          </header>
          <section className="workspace">
            <Playlists
              playlists={playlists}
              loading={loadingPlaylists}
              error={playlistError}
              selectedPlaylistIds={selectedPlaylistIds}
              onTogglePlaylist={handleTogglePlaylist}
            />
            <Analyze selectedPlaylists={selectedPlaylists} onRemovePlaylist={handleRemovePlaylist} />
            <Insights selectedPlaylists={selectedPlaylists} />
          </section>
        </>
      )}
    </main>
  );
}

export default App;
