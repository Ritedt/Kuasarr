import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart3,
  Download,
  Package,
  CheckCircle,
  XCircle,
  Activity,
  Clock,
  Zap,
  Globe,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Spinner } from '../components/ui/Spinner';
import { Select } from '../components/ui/Select';
import { getStatistics } from '../lib/api';
import { useUIStore } from '../stores/uiStore';
import type { DailyStat, HosterStatus } from '../types';

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
  trend,
  trendValue,
  variant = 'default',
}: {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ElementType;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'error';
}) {
  const variantStyles = {
    default: 'bg-bg-secondary',
    primary: 'bg-kuasarr-primary/10 border-kuasarr-primary/30',
    success: 'bg-kuasarr-success/10 border-kuasarr-success/30',
    warning: 'bg-kuasarr-warning/10 border-kuasarr-warning/30',
    error: 'bg-kuasarr-error/10 border-kuasarr-error/30',
  };

  const iconColors = {
    default: 'text-kuasarr-primary',
    primary: 'text-kuasarr-primary',
    success: 'text-kuasarr-success',
    warning: 'text-kuasarr-warning',
    error: 'text-kuasarr-error',
  };

  return (
    <Card className={variantStyles[variant]}>
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <p className="text-text-secondary text-sm">{title}</p>
            <p className="text-2xl font-bold text-text-primary mt-1">{value}</p>
            {subtitle && <p className="text-text-secondary text-xs mt-1">{subtitle}</p>}
            {trend && trendValue && (
              <div className={`flex items-center gap-1 mt-2 text-sm ${
                trend === 'up' ? 'text-kuasarr-success' : trend === 'down' ? 'text-kuasarr-error' : 'text-text-secondary'
              }`}>
                {trend === 'up' ? <ArrowUpRight className="h-4 w-4" /> : trend === 'down' ? <ArrowDownRight className="h-4 w-4" /> : null}
                <span>{trendValue}</span>
              </div>
            )}
          </div>
          <div className={`p-3 bg-bg-tertiary/50 rounded-lg ${iconColors[variant]}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function DailyStatsTable({ stats }: { stats: DailyStat[] }) {
  if (stats.length === 0) {
    return (
      <div className="text-center py-8 text-text-secondary">
        <Calendar className="h-12 w-12 mx-auto mb-3 opacity-50" />
        <p>No daily statistics available</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-bg-tertiary">
            <th className="text-left py-3 px-4 text-sm font-medium text-text-secondary">Date</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-text-secondary">Added</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-text-secondary">Completed</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-text-secondary">Failed</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-text-secondary">Downloaded</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-text-secondary">CAPTCHAs</th>
          </tr>
        </thead>
        <tbody>
          {stats.slice().reverse().map((stat) => (
            <tr key={stat.date} className="border-b border-bg-tertiary/50 hover:bg-bg-tertiary/20">
              <td className="py-3 px-4 text-text-primary">{stat.date}</td>
              <td className="py-3 px-4 text-right text-text-primary">{stat.packages_added}</td>
              <td className="py-3 px-4 text-right text-kuasarr-success">{stat.packages_completed}</td>
              <td className="py-3 px-4 text-right text-kuasarr-error">{stat.packages_failed}</td>
              <td className="py-3 px-4 text-right text-text-primary">{formatBytes(stat.bytes_downloaded)}</td>
              <td className="py-3 px-4 text-right text-text-primary">{stat.captchas_solved}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HosterStatusGrid({ hosters }: { hosters: HosterStatus[] }) {
  if (hosters.length === 0) {
    return (
      <div className="text-center py-8 text-text-secondary">
        <Globe className="h-12 w-12 mx-auto mb-3 opacity-50" />
        <p>No hoster status available</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {hosters.map((hoster) => (
        <div
          key={hoster.hoster_id}
          className={`p-3 rounded-lg border ${
            hoster.online
              ? 'bg-kuasarr-success/5 border-kuasarr-success/20'
              : 'bg-kuasarr-error/5 border-kuasarr-error/20'
          }`}
        >
          <div className="flex items-center gap-2">
            <Badge variant={hoster.online ? 'success' : 'error'} dot size="sm" />
            <span className="text-sm text-text-primary truncate">{hoster.hoster_name}</span>
          </div>
          <p className="text-xs text-text-secondary mt-1">
            {hoster.response_time_ms}ms response
          </p>
        </div>
      ))}
    </div>
  );
}

export default function StatisticsPage() {
  const { jdConnected } = useUIStore();
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d' | 'all'>('30d');

  const { data: stats, isLoading, refetch } = useQuery({
    queryKey: ['statistics'],
    queryFn: getStatistics,
    refetchInterval: 60000,
  });

  const timeRangeOptions = [
    { value: '7d', label: 'Last 7 Days' },
    { value: '30d', label: 'Last 30 Days' },
    { value: '90d', label: 'Last 90 Days' },
    { value: 'all', label: 'All Time' },
  ];

  const filteredDailyStats = stats?.daily_stats.filter((stat) => {
    if (timeRange === 'all') return true;
    const days = parseInt(timeRange);
    const statDate = new Date(stat.date);
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - days);
    return statDate >= cutoffDate;
  }) || [];

  const completionRate = stats
    ? stats.total_packages > 0
      ? Math.round((stats.completed_packages / stats.total_packages) * 100)
      : 0
    : 0;

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Statistics</h1>
            <p className="text-text-secondary mt-1">Monitor your download activity and performance</p>
          </div>
          <div className="flex items-center gap-2">
            <Select
              options={timeRangeOptions}
              value={timeRange}
              onChange={(value) => setTimeRange(value as typeof timeRange)}
              className="w-40"
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => refetch()}
              leftIcon={<Activity className="h-4 w-4" />}
            >
              Refresh
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="xl" />
          </div>
        ) : stats ? (
          <>
            {/* Overview Stats */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <StatCard
                title="Total Packages"
                value={stats.total_packages.toString()}
                subtitle="All time"
                icon={Package}
              />
              <StatCard
                title="Completed"
                value={stats.completed_packages.toString()}
                subtitle={`${completionRate}% success rate`}
                icon={CheckCircle}
                variant="success"
              />
              <StatCard
                title="Failed"
                value={stats.failed_packages.toString()}
                subtitle="Failed downloads"
                icon={XCircle}
                variant="error"
              />
              <StatCard
                title="Downloaded"
                value={formatBytes(stats.total_downloaded)}
                subtitle="Total data"
                icon={Download}
                variant="primary"
              />
              <StatCard
                title="Avg Speed"
                value={`${formatBytes(stats.average_speed)}/s`}
                subtitle="Average download speed"
                icon={Zap}
              />
              <StatCard
                title="Uptime"
                value={formatDuration(stats.uptime_seconds)}
                subtitle="Since start"
                icon={Clock}
              />
            </div>

            {/* API & CAPTCHA Stats */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">API Calls Today</p>
                      <p className="text-3xl font-bold text-text-primary mt-1">{stats.api_calls_today}</p>
                    </div>
                    <div className="p-4 bg-kuasarr-secondary/10 rounded-lg">
                      <Activity className="h-6 w-6 text-kuasarr-secondary" />
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-text-secondary text-sm">CAPTCHAs Solved Today</p>
                      <p className="text-3xl font-bold text-text-primary mt-1">{stats.captchas_solved_today}</p>
                    </div>
                    <div className="p-4 bg-kuasarr-warning/10 rounded-lg">
                      <BarChart3 className="h-6 w-6 text-kuasarr-warning" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Daily Statistics */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5" />
                  Daily Statistics
                </CardTitle>
                <CardDescription>
                  Package and download activity over time
                </CardDescription>
              </CardHeader>
              <CardContent>
                <DailyStatsTable stats={filteredDailyStats} />
              </CardContent>
            </Card>

            {/* Hoster Status */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Globe className="h-5 w-5" />
                  Hoster Status
                </CardTitle>
                <CardDescription>
                  Current status of configured hosters
                </CardDescription>
              </CardHeader>
              <CardContent>
                <HosterStatusGrid hosters={stats.hoster_status} />
              </CardContent>
            </Card>
          </>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16">
              <BarChart3 className="h-16 w-16 text-text-secondary/50 mb-4" />
              <h3 className="text-lg font-medium text-text-primary">No Statistics Available</h3>
              <p className="text-text-secondary text-sm mt-1 text-center max-w-md">
                Statistics will appear here once you start using Kuasarr.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
