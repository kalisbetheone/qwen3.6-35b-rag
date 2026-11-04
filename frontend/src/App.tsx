import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, hasToken, setToken, setUnauthorizedHandler } from './api';
import { Login } from './pages/Login';
import { Welcome } from './pages/Welcome';
import { Workspace } from './pages/Workspace';
import type { User } from './types';

type View = 'boot' | 'welcome' | 'login' | 'app';

export default function App() {
  const [view, setView] = useState<View>(hasToken() ? 'boot' : 'welcome');
  const [user, setUser] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setNotice('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.');
      setView('login');
    });
    if (!hasToken()) return;
    api
      .me()
      .then((u) => {
        setUser(u);
        setView('app');
      })
      .catch(() => setView('welcome'));
  }, []);

  const logout = () => {
    setToken(null);
    setUser(null);
    setNotice(null);
    setView('welcome');
  };

  if (view === 'boot')
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        <Loader2 className="animate-spin" />
      </div>
    );
  if (view === 'app' && user) return <Workspace key={user.username} user={user} onLogout={logout} />;
  if (view === 'login')
    return (
      <Login
        notice={notice}
        onBack={() => setView('welcome')}
        onSuccess={(u) => {
          setUser(u);
          setNotice(null);
          setView('app');
        }}
      />
    );
  return <Welcome onLogin={() => setView('login')} />;
}
