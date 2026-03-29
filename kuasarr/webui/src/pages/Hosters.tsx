import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Shield,
  Globe,
  AlertCircle,
  RefreshCw,
  Clock,
  Ban,
  Play,
} from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Spinner } from '../components/ui/Spinner';
import { Modal } from '../components/ui/Modal';
import {
  getHosters,
  blockHoster,
  unblockHoster,
  blockAllHosters,
  unblockAllHosters,
} from '../lib/api';
import { useUIStore } from '../stores/uiStore';
import type { Hoster } from '../types';

function formatDuration(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 0) return `${diffDays}d ago`;
  if (diffHours > 0) return `${diffHours}h ago`;
  if (diffMins > 0) return `${diffMins}m ago`;
  return 'Just now';
}

function HosterRow({
  hoster,
  onBlock,
  onUnblock,
  isPending,
}: {
  hoster: Hoster;
  onBlock: (id: string) => void;
  onUnblock: (id: string) => void;
  isPending: boolean;
}) {
  return (
    <div className="p-4 border-b border-bg-tertiary last:border-0 hover:bg-bg-tertiary/30 transition-colors">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div
            className={`p-2 rounded-lg ${
              hoster.blocked
                ? 'bg-kuasarr-error/10'
                : hoster.status === 'online'
                ? 'bg-kuasarr-success/10'
                : hoster.status === 'offline'
                ? 'bg-kuasarr-error/10'
                : 'bg-bg-tertiary'
            }`}
          >
            {hoster.blocked ? (
              <Ban className="h-5 w-5 text-kuasarr-error" />
            ) : hoster.status === 'online' ? (
              <Globe className="h-5 w-5 text-kuasarr-success" />
            ) : hoster.status === 'offline' ? (
              <Globe className="h-5 w-5 text-kuasarr-error" />
            ) : (
              <Globe className="h-5 w-5 text-text-secondary" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-medium text-text-primary">{hoster.name}</h3>
              {hoster.blocked ? (
                <Badge variant="error" size="sm">
                  Blocked
                </Badge>
              ) : hoster.status === 'online' ? (
                <Badge variant="success" size="sm" dot>
                  Online
                </Badge>
              ) : hoster.status === 'offline' ? (
                <Badge variant="error" size="sm" dot>
                  Offline
                </Badge>
              ) : (
                <Badge variant="default" size="sm">
                  Unknown
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-4 text-sm text-text-secondary mt-1">
              <span className="truncate max-w-xs">{hoster.url}</span>
              {hoster.last_checked && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  Checked {formatDuration(hoster.last_checked)}
                </span>
              )}
              <span>Priority: {hoster.priority}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hoster.blocked ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onUnblock(hoster.id)}
              disabled={isPending}
              leftIcon={<Play className="h-4 w-4 text-kuasarr-success" />}
            >
              Unblock
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onBlock(hoster.id)}
              disabled={isPending}
              leftIcon={<Ban className="h-4 w-4 text-kuasarr-error" />}
            >
              Block
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function HostersPage() {
  const { jdConnected } = useUIStore();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [showBlockAllModal, setShowBlockAllModal] = useState(false);
  const [showUnblockAllModal, setShowUnblockAllModal] = useState(false);

  const { data: hosters = [], isLoading, refetch } = useQuery({
    queryKey: ['hosters'],
    queryFn: getHosters,
  });

  const blockMutation = useMutation({
    mutationFn: blockHoster,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hosters'] }),
  });

  const unblockMutation = useMutation({
    mutationFn: unblockHoster,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hosters'] }),
  });

  const blockAllMutation = useMutation({
    mutationFn: blockAllHosters,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosters'] });
      setShowBlockAllModal(false);
    },
  });

  const unblockAllMutation = useMutation({
    mutationFn: unblockAllHosters,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosters'] });
      setShowUnblockAllModal(false);
    },
  });

  const filteredHosters = hosters.filter(
    (hoster) =>
      hoster.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      hoster.url.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const blockedCount = hosters.filter((h) => h.blocked).length;

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Hosters</h1>
            <p className="text-text-secondary mt-1">Manage download hosters and their status</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => refetch()}
              leftIcon={<RefreshCw className="h-4 w-4" />}
            >
              Refresh
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-kuasarr-primary/10 rounded-lg">
                  <Globe className="h-5 w-5 text-kuasarr-primary" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-text-primary">{hosters.length}</p>
                  <p className="text-text-secondary text-sm">Total</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-kuasarr-warning/10 rounded-lg">
                  <Ban className="h-5 w-5 text-kuasarr-warning" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-text-primary">{blockedCount}</p>
                  <p className="text-text-secondary text-sm">Blocked</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Actions Bar */}
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1">
            <Input
              placeholder="Search hosters..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              leftIcon={<Globe className="h-4 w-4" />}
            />
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowBlockAllModal(true)}
              leftIcon={<Ban className="h-4 w-4" />}
            >
              Block All
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowUnblockAllModal(true)}
              leftIcon={<Play className="h-4 w-4" />}
            >
              Unblock All
            </Button>
          </div>
        </div>

        {/* Hosters List */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Hoster List ({filteredHosters.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Spinner size="lg" />
              </div>
            ) : filteredHosters.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 px-4">
                <Globe className="h-12 w-12 text-text-secondary/50 mb-4" />
                <h3 className="text-lg font-medium text-text-primary">
                  {searchQuery ? 'No matching hosters' : 'No hosters configured'}
                </h3>
                <p className="text-text-secondary text-sm mt-1 text-center max-w-md">
                  {searchQuery
                    ? 'Try a different search term'
                    : 'Hosters will appear here once configured in your settings'}
                </p>
              </div>
            ) : (
              filteredHosters.map((hoster) => (
                <HosterRow
                  key={hoster.id}
                  hoster={hoster}
                  onBlock={(id) => blockMutation.mutate(id)}
                  onUnblock={(id) => unblockMutation.mutate(id)}
                  isPending={blockMutation.isPending || unblockMutation.isPending}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card className="bg-kuasarr-primary/5 border-kuasarr-primary/20">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-kuasarr-primary mt-0.5" />
              <div>
                <h4 className="font-medium text-text-primary">About Hoster Management</h4>
                <p className="text-sm text-text-secondary mt-1">
                  Blocked hosters will be skipped during searches and downloads. Use this to temporarily disable
                  problematic hosters or prioritize specific ones. Hosters are checked periodically for availability.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Block All Modal */}
      <Modal
        isOpen={showBlockAllModal}
        onClose={() => setShowBlockAllModal(false)}
        title="Block All Hosters"
        description="Are you sure you want to block all hosters? This will prevent any new downloads from starting."
      >
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="ghost" onClick={() => setShowBlockAllModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => blockAllMutation.mutate()}
            loading={blockAllMutation.isPending}
            leftIcon={<Ban className="h-4 w-4" />}
          >
            Block All
          </Button>
        </div>
      </Modal>

      {/* Unblock All Modal */}
      <Modal
        isOpen={showUnblockAllModal}
        onClose={() => setShowUnblockAllModal(false)}
        title="Unblock All Hosters"
        description="Are you sure you want to unblock all hosters? This will allow downloads from all configured hosters."
      >
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="ghost" onClick={() => setShowUnblockAllModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => unblockAllMutation.mutate()}
            loading={unblockAllMutation.isPending}
            leftIcon={<Play className="h-4 w-4" />}
          >
            Unblock All
          </Button>
        </div>
      </Modal>
    </Layout>
  );
}
