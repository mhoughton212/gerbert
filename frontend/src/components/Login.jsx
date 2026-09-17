import React from 'react';
import { getLoginUrl } from '../api';

function Login() {
  const handleLogin = async () => {
    const data = await getLoginUrl();
    window.location.href = data.url;
  };

  return (
    <section className="login-panel">
      <h1>Gerbert</h1>
      <p>Log in with Spotify to chart when tracks were added to your saved playlists.</p>
      <button onClick={handleLogin}>Login with Spotify</button>
    </section>
  );
}

export default Login;
