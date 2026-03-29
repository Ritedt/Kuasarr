import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Bell,
  MessageSquare,
  Send,
  Mail,
  Webhook,
  Smartphone,
  Check,
  AlertCircle,
  Plus,
  Trash2,
  Edit2,
  TestTube,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Spinner } from '../components/ui/Spinner';
import { Modal } from '../components/ui/Modal';
import { Toggle } from '../components/ui/Toggle';
import { useUIStore } from '../stores/uiStore';
import {
  getNotificationSettings,
  saveNotificationSettings,
  testNotification as testNotificationApi,
} from '../lib/api';
import type { NotificationProvider, NotificationConfig, NotificationEvent } from '../types';

const testNotification = async (
  provider: NotificationProvider,
  settings: Record<string, string | number | boolean>
): Promise<void> => {
  const result = await testNotificationApi({ provider, settings });
  if (!result.success) {
    throw new Error(result.message || 'Test failed');
  }
};

const providerIcons: Record<NotificationProvider, React.ElementType> = {
  discord: MessageSquare,
  telegram: Send,
  pushover: Smartphone,
  email: Mail,
  webhook: Webhook,
};

const providerLabels: Record<NotificationProvider, string> = {
  discord: 'Discord',
  telegram: 'Telegram',
  pushover: 'Pushover',
  email: 'Email',
  webhook: 'Webhook',
};

const allEvents: NotificationEvent[] = [
  'download_complete',
  'download_failed',
  'package_added',
  'captcha_required',
  'jd_connected',
  'jd_disconnected',
];

const eventLabels: Record<NotificationEvent, string> = {
  download_complete: 'Download Complete',
  download_failed: 'Download Failed',
  package_added: 'Package Added',
  captcha_required: 'CAPTCHA Required',
  jd_connected: 'JDownloader Connected',
  jd_disconnected: 'JDownloader Disconnected',
};

interface NotificationFormData {
  provider: NotificationProvider;
  enabled: boolean;
  settings: Record<string, string>;
  events: NotificationEvent[];
}

const initialFormData: NotificationFormData = {
  provider: 'discord',
  enabled: true,
  settings: {},
  events: ['download_complete', 'download_failed'],
};

const providerSettings: Record<NotificationProvider, { key: string; label: string; type: string; required: boolean }[]> = {
  discord: [
    { key: 'webhook_url', label: 'Webhook URL', type: 'url', required: true },
    { key: 'username', label: 'Bot Username (Optional)', type: 'text', required: false },
  ],
  telegram: [
    { key: 'bot_token', label: 'Bot Token', type: 'password', required: true },
    { key: 'chat_id', label: 'Chat ID', type: 'text', required: true },
  ],
  pushover: [
    { key: 'app_token', label: 'App Token', type: 'password', required: true },
    { key: 'user_key', label: 'User Key', type: 'password', required: true },
  ],
  email: [
    { key: 'smtp_host', label: 'SMTP Host', type: 'text', required: true },
    { key: 'smtp_port', label: 'SMTP Port', type: 'number', required: true },
    { key: 'username', label: 'Username', type: 'email', required: true },
    { key: 'password', label: 'Password', type: 'password', required: true },
    { key: 'to_address', label: 'To Address', type: 'email', required: true },
    { key: 'use_tls', label: 'Use TLS', type: 'checkbox', required: false },
  ],
  webhook: [
    { key: 'url', label: 'Webhook URL', type: 'url', required: true },
    { key: 'method', label: 'HTTP Method', type: 'select', required: true },
    { key: 'headers', label: 'Custom Headers (JSON)', type: 'textarea', required: false },
  ],
};

function NotificationConfigCard({
  config,
  onEdit,
  onDelete,
  onToggle,
  isPending,
}: {
  config: NotificationConfig;
  onEdit: (config: NotificationConfig) => void;
  onDelete: (config: NotificationConfig) => void;
  onToggle: (config: NotificationConfig, enabled: boolean) => void;
  isPending: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const Icon = providerIcons[config.provider];

  return (
    <div className="border-b border-bg-tertiary last:border-0">
      <div
        className="p-4 hover:bg-bg-tertiary/30 transition-colors cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className={`p-2 rounded-lg ${config.enabled ? 'bg-kuasarr-primary/10' : 'bg-bg-tertiary'}`}>
              <Icon className={`h-5 w-5 ${config.enabled ? 'text-kuasarr-primary' : 'text-text-secondary'}`} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="font-medium text-text-primary">{providerLabels[config.provider]}</h3>
                <Badge variant={config.enabled ? 'success' : 'default'} size="sm">
                  {config.enabled ? 'Enabled' : 'Disabled'}
                </Badge>
              </div>
              <p className="text-sm text-text-secondary mt-1">
                {config.events.length} event{config.events.length !== 1 ? 's' : ''} configured
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Toggle
              checked={config.enabled}
              onChange={(checked) => onToggle(config, checked)}
              disabled={isPending}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onEdit(config);
              }}
              leftIcon={<Edit2 className="h-4 w-4" />}
            >
              Edit
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(config);
              }}
              leftIcon={<Trash2 className="h-4 w-4 text-kuasarr-error" />}
            >
              Delete
            </Button>
            <Button variant="ghost" size="sm">
              {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="px-4 pb-4">
          <div className="bg-bg-tertiary/50 rounded-lg p-4">
            <h4 className="text-sm font-medium text-text-primary mb-2">Configured Events</h4>
            <div className="flex flex-wrap gap-2">
              {config.events.map((event) => (
                <Badge key={event} variant="info" size="sm">
                  {eventLabels[event]}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function NotificationsPage() {
  const { jdConnected } = useUIStore();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState<NotificationConfig | null>(null);
  const [formData, setFormData] = useState<NotificationFormData>(initialFormData);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const { data: settings, isLoading } = useQuery({
    queryKey: ['notifications', 'settings'],
    queryFn: getNotificationSettings,
  });

  const saveMutation = useMutation({
    mutationFn: saveNotificationSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
      closeModal();
    },
  });

  const handleEdit = (config: NotificationConfig) => {
    setEditingConfig(config);
    setFormData({
      provider: config.provider,
      enabled: config.enabled,
      settings: Object.entries(config.settings).reduce((acc, [key, value]) => {
        acc[key] = String(value);
        return acc;
      }, {} as Record<string, string>),
      events: config.events,
    });
    setTestResult(null);
    setIsModalOpen(true);
  };

  const handleCreate = () => {
    setEditingConfig(null);
    setFormData(initialFormData);
    setTestResult(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingConfig(null);
    setFormData(initialFormData);
    setTestResult(null);
  };

  const handleToggle = (config: NotificationConfig, enabled: boolean) => {
    if (!settings) return;
    const updatedConfigs = settings.configs.map((c) =>
      c.provider === config.provider ? { ...c, enabled } : c
    );
    saveMutation.mutate({ ...settings, configs: updatedConfigs });
  };

  const handleDelete = (config: NotificationConfig) => {
    if (!settings) return;
    const updatedConfigs = settings.configs.filter((c) => c.provider !== config.provider);
    saveMutation.mutate({ ...settings, configs: updatedConfigs });
  };

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      await testNotification(formData.provider, formData.settings);
      setTestResult({ success: true, message: 'Test notification sent successfully!' });
    } catch (error) {
      setTestResult({
        success: false,
        message: error instanceof Error ? error.message : 'Test failed',
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings) return;

    const newConfig: NotificationConfig = {
      provider: formData.provider,
      enabled: formData.enabled,
      settings: formData.settings,
      events: formData.events,
    };

    const updatedConfigs = editingConfig
      ? settings.configs.map((c) => (c.provider === editingConfig.provider ? newConfig : c))
      : [...settings.configs, newConfig];

    saveMutation.mutate({ ...settings, configs: updatedConfigs });
  };

  const toggleEvent = (event: NotificationEvent) => {
    setFormData((prev) => ({
      ...prev,
      events: prev.events.includes(event)
        ? prev.events.filter((e) => e !== event)
        : [...prev.events, event],
    }));
  };

  const providerOptions = Object.entries(providerLabels).map(([value, label]) => ({
    value,
    label,
  }));

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Notifications</h1>
            <p className="text-text-secondary mt-1">Configure notifications for download events</p>
          </div>
          <Button
            variant="primary"
            onClick={handleCreate}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add Notification
          </Button>
        </div>

        {/* Global Toggle */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-kuasarr-primary/10 rounded-lg">
                  <Bell className="h-5 w-5 text-kuasarr-primary" />
                </div>
                <div>
                  <h3 className="font-medium text-text-primary">Global Notifications</h3>
                  <p className="text-sm text-text-secondary">Enable or disable all notifications</p>
                </div>
              </div>
              <Toggle
                checked={settings?.global_enabled ?? true}
                onChange={(checked) => {
                  if (settings) {
                    saveMutation.mutate({ ...settings, global_enabled: checked });
                  }
                }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Notification Configs */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5" />
              Configured Notifications ({settings?.configs.length || 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Spinner size="lg" />
              </div>
            ) : settings?.configs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 px-4">
                <Bell className="h-12 w-12 text-text-secondary/50 mb-4" />
                <h3 className="text-lg font-medium text-text-primary">No Notifications Configured</h3>
                <p className="text-text-secondary text-sm mt-1 text-center max-w-md">
                  Add notification providers to receive alerts about your downloads.
                </p>
                <Button variant="primary" className="mt-4" onClick={handleCreate} leftIcon={<Plus className="h-4 w-4" />}>
                  Add Notification
                </Button>
              </div>
            ) : (
              settings?.configs.map((config) => (
                <NotificationConfigCard
                  key={config.provider}
                  config={config}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                  onToggle={handleToggle}
                  isPending={saveMutation.isPending}
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
                <h4 className="font-medium text-text-primary">About Notifications</h4>
                <p className="text-sm text-text-secondary mt-1">
                  Notifications are sent when specific events occur, such as downloads completing or failing.
                  Configure multiple providers to receive alerts through different channels.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={closeModal}
        title={editingConfig ? 'Edit Notification' : 'Add Notification'}
        description={editingConfig ? 'Update notification settings' : 'Configure a new notification provider'}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-6">
          <Select
            label="Provider"
            options={providerOptions}
            value={formData.provider}
            onChange={(value) =>
              setFormData({
                ...formData,
                provider: value as NotificationProvider,
                settings: {},
              })
            }
            disabled={!!editingConfig}
          />

          <div className="space-y-4">
            <h4 className="text-sm font-medium text-text-primary">Provider Settings</h4>
            {providerSettings[formData.provider].map((setting) => (
              <Input
                key={setting.key}
                label={setting.label}
                type={setting.type === 'password' ? 'password' : setting.type === 'number' ? 'number' : 'text'}
                value={formData.settings[setting.key] || ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    settings: { ...formData.settings, [setting.key]: e.target.value },
                  })
                }
                required={setting.required}
              />
            ))}
          </div>

          <div>
            <h4 className="text-sm font-medium text-text-primary mb-3">Events</h4>
            <div className="grid grid-cols-2 gap-3">
              {allEvents.map((event) => (
                <label
                  key={event}
                  className="flex items-center gap-2 p-3 bg-bg-tertiary/50 rounded-lg cursor-pointer hover:bg-bg-tertiary transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={formData.events.includes(event)}
                    onChange={() => toggleEvent(event)}
                    className="w-4 h-4 rounded border-bg-tertiary text-kuasarr-primary focus:ring-kuasarr-primary"
                  />
                  <span className="text-sm text-text-primary">{eventLabels[event]}</span>
                </label>
              ))}
            </div>
          </div>

          <Toggle
            label="Enabled"
            checked={formData.enabled}
            onChange={(checked) => setFormData({ ...formData, enabled: checked })}
          />

          {testResult && (
            <div
              className={`p-4 rounded-lg flex items-start gap-3 ${
                testResult.success
                  ? 'bg-kuasarr-success/10 border border-kuasarr-success/30'
                  : 'bg-kuasarr-error/10 border border-kuasarr-error/30'
              }`}
            >
              {testResult.success ? (
                <Check className="h-5 w-5 text-kuasarr-success mt-0.5" />
              ) : (
                <AlertCircle className="h-5 w-5 text-kuasarr-error mt-0.5" />
              )}
              <p className={testResult.success ? 'text-kuasarr-success' : 'text-kuasarr-error'}>
                {testResult.message}
              </p>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-bg-tertiary">
            <Button type="button" variant="ghost" onClick={closeModal}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={handleTest}
              loading={isTesting}
              leftIcon={<TestTube className="h-4 w-4" />}
            >
              Test
            </Button>
            <Button
              type="submit"
              variant="primary"
              loading={saveMutation.isPending}
              leftIcon={<Check className="h-4 w-4" />}
            >
              {editingConfig ? 'Update' : 'Add'}
            </Button>
          </div>
        </form>
      </Modal>
    </Layout>
  );
}
