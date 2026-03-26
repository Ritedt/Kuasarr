import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Download,
  FolderOpen,
  HardDrive,
  Link,
  Settings,
  Shield,
  Zap,
} from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { getStatistics } from '../lib/api';
import { useUIStore } from '../stores/uiStore';
import type { JDownloaderStatus } from '../types';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function formatDuration(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
}: {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ElementType;
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-text-secondary text-sm">{title}</p>
            <p className="text-2xl font-bold text-text-primary mt-1">{value}</p>
            {subtitle && <p className="text-text-secondary text-xs mt-1">{subtitle}</p>}
          </div>
          <div className="p-3 bg-kuasarr-primary/10 rounded-lg">
            <Icon className="h-5 w-5 text-kuasarr-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function JDStatusCard({ status }: { status?: JDownloaderStatus }) {
  if (!status) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>JDownloader Status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Spinner size="lg" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          JDownloader Status
          <Badge variant={status.connected ? 'success' : 'error'} dot>
            {status.connected ? 'Connected' : 'Disconnected'}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {status.connected ? (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-text-secondary text-sm">Device</p>
                <p className="text-text-primary font-medium">{status.device_name || 'Unknown'}</p>
              </div>
              <div>
                <p className="text-text-secondary text-sm">Account</p>
                <p className="text-text-primary font-medium">{status.email}</p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4 pt-4 border-t border-bg-tertiary">
              <div className="text-center">
                <p className="text-2xl font-bold text-kuasarr-primary">{status.active_downloads}</p>
                <p className="text-text-secondary text-xs">Active</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-kuasarr-secondary">{status.total_downloads}</p>
                <p className="text-text-secondary text-xs">Total</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-kuasarr-accent">
                  {formatBytes(status.global_speed)}/s
                </p>
                <p className="text-text-secondary text-xs">Speed</p>
              </div>
            </div>
          </>
        ) : (
          <div className="text-center py-6">
            <Zap className="h-12 w-12 text-kuasarr-error mx-auto mb-3" />
            <p className="text-text-primary font-medium">Not Connected</p>
            <p className="text-text-secondary text-sm mt-1">
              Configure JDownloader in Settings to get started
            </p>
            <Button variant="primary" className="mt-4" leftIcon={<Settings className="h-4 w-4" />}>
              Configure
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const { jdConnected, jdStatus } = useUIStore();
  const { data: stats } = useQuery({
    queryKey: ['statistics'],
    queryFn: getStatistics,
    refetchInterval: 30000,
  });

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
            <p className="text-text-secondary mt-1">Overview of your Kuasarr instance</p>
          </div>
          <Badge variant={jdConnected ? 'success' : 'error'} dot>
            {jdConnected ? 'System Online' : 'JD Disconnected'}
          </Badge>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Total Packages"
            value={stats?.total_packages?.toString() || '0'}
            subtitle="All time"
            icon={FolderOpen}
          />
          <StatCard
            title="Downloaded"
            value={formatBytes(stats?.total_downloaded || 0)}
            subtitle="Total data"
            icon={HardDrive}
          />
          <StatCard
            title="API Calls"
            value={stats?.api_calls_today?.toString() || '0'}
            subtitle="Today"
            icon={Activity}
          />
          <StatCard
            title="Uptime"
            value={formatDuration(stats?.uptime_seconds || 0)}
            subtitle="Since start"
            icon={Zap}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <JDStatusCard status={jdStatus ?? undefined} />

          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                <Button variant="secondary" leftIcon={<Link className="h-4 w-4" />}>
                  Add Link
                </Button>
                <Button variant="secondary" leftIcon={<Download className="h-4 w-4" />}>
                  View Packages
                </Button>
                <Button variant="secondary" leftIcon={<Shield className="h-4 w-4" />}>
                  Manage Hosters
                </Button>
                <Button variant="secondary" leftIcon={<Settings className="h-4 w-4" />}>
                  Settings
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {stats?.hoster_status && stats.hoster_status.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Hoster Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                {stats.hoster_status.map((hoster) => (
                  <div
                    key={hoster.hoster_id}
                    className="flex items-center gap-2 p-3 bg-bg-tertiary rounded-lg"
                  >
                    <Badge variant={hoster.online ? 'success' : 'error'} dot size="sm" />
                    <span className="text-sm text-text-primary truncate">{hoster.hoster_name}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
