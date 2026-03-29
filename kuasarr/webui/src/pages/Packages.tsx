import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Pause,
  Play,
  Trash2,
  RefreshCw,
  FolderOpen,
  Search,
  Filter,
} from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Spinner } from '../components/ui/Spinner';
import { Modal } from '../components/ui/Modal';
import { getPackages, pausePackage, resumePackage, deletePackage } from '../lib/api';
import { useUIStore } from '../stores/uiStore';
import type { Package, PackageStatus } from '../types';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return '--:--';
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hrs > 0) return `${hrs}h ${mins}m`;
  return `${mins}m`;
}

function getStatusBadge(status: PackageStatus) {
  const variants: Record<PackageStatus, 'default' | 'success' | 'warning' | 'error' | 'info' | 'primary'> = {
    queued: 'default',
    downloading: 'primary',
    paused: 'warning',
    completed: 'success',
    failed: 'error',
    extracting: 'info',
  };
  return <Badge variant={variants[status]}>{status.charAt(0).toUpperCase() + status.slice(1)}</Badge>;
}

function PackageRow({
  pkg,
  onPause,
  onResume,
  onDelete,
  isPending,
}: {
  pkg: Package;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onDelete: (id: string) => void;
  isPending: boolean;
}) {
  const progress = pkg.size > 0 ? (pkg.downloaded / pkg.size) * 100 : 0;

  return (
    <div className="p-4 border-b border-bg-tertiary last:border-0 hover:bg-bg-tertiary/30 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium text-text-primary truncate">{pkg.name}</h3>
            {getStatusBadge(pkg.status)}
          </div>
          <div className="flex items-center gap-4 text-sm text-text-secondary">
            <span>{formatBytes(pkg.downloaded)} / {formatBytes(pkg.size)}</span>
            {pkg.speed > 0 && <span>{formatBytes(pkg.speed)}/s</span>}
            {pkg.eta !== null && <span>ETA: {formatDuration(pkg.eta)}</span>}
            <span>{pkg.links.length} files</span>
          </div>
          <div className="mt-2">
            <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-kuasarr-primary to-kuasarr-secondary transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {pkg.status === 'downloading' && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onPause(pkg.id)}
              disabled={isPending}
              leftIcon={<Pause className="h-4 w-4" />}
            >
              Pause
            </Button>
          )}
          {pkg.status === 'paused' && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onResume(pkg.id)}
              disabled={isPending}
              leftIcon={<Play className="h-4 w-4" />}
            >
              Resume
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(pkg.id)}
            disabled={isPending}
            leftIcon={<Trash2 className="h-4 w-4 text-kuasarr-error" />}
          >
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}

export function Packages() {
  const { jdConnected } = useUIStore();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const { data: packages = [], isLoading } = useQuery<Package[]>({
    queryKey: ['packages'],
    queryFn: () => getPackages(),
    refetchInterval: 5000,
    enabled: jdConnected,
  });

  const pauseMutation = useMutation({
    mutationFn: pausePackage,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['packages'] }),
  });

  const resumeMutation = useMutation({
    mutationFn: resumePackage,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['packages'] }),
  });

  const deleteMutation = useMutation<void, Error, string>({
    mutationFn: (packageId: string) => deletePackage(packageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packages'] });
      setDeleteId(null);
    },
  });

  const filteredPackages = packages.filter((pkg) =>
    pkg.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const activePackages = filteredPackages.filter((p) => p.status === 'downloading');
  const queuedPackages = filteredPackages.filter((p) => p.status === 'queued');
  const completedPackages = filteredPackages.filter((p) => p.status === 'completed');
  const otherPackages = filteredPackages.filter(
    (p) => !['downloading', 'queued', 'completed'].includes(p.status)
  );

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Packages</h1>
            <p className="text-text-secondary mt-1">Manage your downloads</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<RefreshCw className="h-4 w-4" />}
              onClick={() => queryClient.invalidateQueries({ queryKey: ['packages'] })}
            >
              Refresh
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
            <Input
              placeholder="Search packages..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <Button variant="ghost" size="sm" leftIcon={<Filter className="h-4 w-4" />}>
            Filter
          </Button>
        </div>

        {!jdConnected ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <FolderOpen className="h-12 w-12 text-text-secondary mb-4" />
              <h3 className="text-lg font-medium text-text-primary">JDownloader Not Connected</h3>
              <p className="text-text-secondary text-sm mt-1">
                Connect JDownloader to view and manage packages
              </p>
            </CardContent>
          </Card>
        ) : isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : filteredPackages.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <FolderOpen className="h-12 w-12 text-text-secondary mb-4" />
              <h3 className="text-lg font-medium text-text-primary">No Packages</h3>
              <p className="text-text-secondary text-sm mt-1">
                {searchQuery ? 'No packages match your search' : 'Your download queue is empty'}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {activePackages.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Badge variant="primary" dot />
                    Downloading ({activePackages.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {activePackages.map((pkg) => (
                    <PackageRow
                      key={pkg.id}
                      pkg={pkg}
                      onPause={(id) => pauseMutation.mutate(id)}
                      onResume={(id) => resumeMutation.mutate(id)}
                      onDelete={setDeleteId}
                      isPending={pauseMutation.isPending || resumeMutation.isPending}
                    />
                  ))}
                </CardContent>
              </Card>
            )}

            {queuedPackages.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Badge variant="default" dot />
                    Queued ({queuedPackages.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {queuedPackages.map((pkg) => (
                    <PackageRow
                      key={pkg.id}
                      pkg={pkg}
                      onPause={(id) => pauseMutation.mutate(id)}
                      onResume={(id) => resumeMutation.mutate(id)}
                      onDelete={setDeleteId}
                      isPending={pauseMutation.isPending || resumeMutation.isPending}
                    />
                  ))}
                </CardContent>
              </Card>
            )}

            {otherPackages.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Other ({otherPackages.length})</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {otherPackages.map((pkg) => (
                    <PackageRow
                      key={pkg.id}
                      pkg={pkg}
                      onPause={(id) => pauseMutation.mutate(id)}
                      onResume={(id) => resumeMutation.mutate(id)}
                      onDelete={setDeleteId}
                      isPending={pauseMutation.isPending || resumeMutation.isPending}
                    />
                  ))}
                </CardContent>
              </Card>
            )}

            {completedPackages.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Badge variant="success" dot />
                    Completed ({completedPackages.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {completedPackages.map((pkg) => (
                    <PackageRow
                      key={pkg.id}
                      pkg={pkg}
                      onPause={(id) => pauseMutation.mutate(id)}
                      onResume={(id) => resumeMutation.mutate(id)}
                      onDelete={setDeleteId}
                      isPending={pauseMutation.isPending || resumeMutation.isPending}
                    />
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>

      <Modal
        isOpen={!!deleteId}
        onClose={() => setDeleteId(null)}
        title="Delete Package"
        description="Are you sure you want to delete this package? This action cannot be undone."
      >
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="ghost" onClick={() => setDeleteId(null)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => deleteId && deleteMutation.mutate(deleteId)}
            loading={deleteMutation.isPending}
            leftIcon={<Trash2 className="h-4 w-4" />}
          >
            Delete
          </Button>
        </div>
      </Modal>
    </Layout>
  );
}
