import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { Dashboard } from './pages/Dashboard';
import { Packages } from './pages/Packages';
import Search from './pages/Search';
import Categories from './pages/Categories';
import Hosters from './pages/Hosters';
import Settings from './pages/Settings';
import Statistics from './pages/Statistics';
import Notifications from './pages/Notifications';
import NotFound from './pages/NotFound';
import { getJDownloaderStatus } from './lib/api';
import { useUIStore } from './stores/uiStore';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      refetchOnWindowFocus: false,
      retry: 2,
    },
  },
});

function JdStatusSync() {
  const { setJdConnected, setJdStatus } = useUIStore();
  const { data: jdStatus } = useQuery({
    queryKey: ['jdownloader', 'status'],
    queryFn: getJDownloaderStatus,
    refetchInterval: 30000,
  });

  useEffect(() => {
    if (jdStatus) {
      setJdStatus(jdStatus);
      setJdConnected(jdStatus.connected);
    }
  }, [jdStatus, setJdStatus, setJdConnected]);

  return null;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <JdStatusSync />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/packages" element={<Packages />} />
          <Route path="/search" element={<Search />} />
          <Route path="/categories" element={<Categories />} />
          <Route path="/hosters" element={<Hosters />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/statistics" element={<Statistics />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/404" element={<NotFound />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
