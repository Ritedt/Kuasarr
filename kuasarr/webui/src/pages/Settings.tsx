import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Settings,
  User,
  Lock,
  Zap,
  Save,
  Check,
  AlertCircle,
  Eye,
  EyeOff,
  RefreshCw,
  Server,
  Gauge,
} from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Spinner } from '../components/ui/Spinner';
import { Toggle } from '../components/ui/Toggle';
import {
  getJDownloaderStatus,
  getJDownloaderConfig,
  verifyJDownloaderCredentials,
  saveJDownloaderConfig,
} from '../lib/api';
import { useUIStore } from '../stores/uiStore';
import type { JDownloaderStatus } from '../types';

interface SettingsFormData {
  email: string;
  password: string;
  deviceName: string;
  autoReconnect: boolean;
  maxDownloads: number;
  maxSpeed: number;
}

const initialFormData: SettingsFormData = {
  email: '',
  password: '',
  deviceName: '',
  autoReconnect: true,
  maxDownloads: 3,
  maxSpeed: 0,
};

function JDStatusBadge({ status }: { status?: JDownloaderStatus }) {
  if (!status) return <Badge variant="default">Unknown</Badge>;
  return (
    <Badge variant={status.connected ? 'success' : 'error'} dot>
      {status.connected ? 'Connected' : 'Disconnected'}
    </Badge>
  );
}

export default function SettingsPage() {
  const { jdConnected, setJdConnected, setJdStatus } = useUIStore();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'jdownloader' | 'general'>('jdownloader');
  const [formData, setFormData] = useState<SettingsFormData>(initialFormData);
  const [showPassword, setShowPassword] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{ success: boolean; message: string } | null>(null);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof SettingsFormData, string>>>({});

  const { data: jdStatus, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ['jdownloader', 'status'],
    queryFn: getJDownloaderStatus,
    refetchInterval: 30000,
  });

  const { data: jdConfig, isLoading: configLoading } = useQuery({
    queryKey: ['jdownloader', 'config'],
    queryFn: getJDownloaderConfig,
  });

  useEffect(() => {
    if (jdConfig) {
      setFormData({
        email: jdConfig.email || '',
        password: jdConfig.password || '',
        deviceName: jdConfig.device_name || '',
        autoReconnect: jdConfig.auto_reconnect ?? true,
        maxDownloads: jdConfig.max_downloads || 3,
        maxSpeed: jdConfig.max_speed || 0,
      });
    }
  }, [jdConfig]);

  useEffect(() => {
    if (jdStatus) {
      setJdStatus(jdStatus);
      setJdConnected(jdStatus.connected);
    }
  }, [jdStatus, setJdStatus, setJdConnected]);

  const saveMutation = useMutation({
    mutationFn: saveJDownloaderConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jdownloader'] });
      setVerifyResult({ success: true, message: 'Settings saved successfully!' });
      setTimeout(() => setVerifyResult(null), 5000);
    },
    onError: (error) => {
      setVerifyResult({
        success: false,
        message: error instanceof Error ? error.message : 'Failed to save settings',
      });
    },
  });

  const validateForm = (): boolean => {
    const errors: Partial<Record<keyof SettingsFormData, string>> = {};

    if (!formData.email.trim()) {
      errors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      errors.email = 'Please enter a valid email';
    }

    if (!formData.password.trim()) {
      errors.password = 'Password is required';
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleVerify = async () => {
    if (!validateForm()) return;

    setIsVerifying(true);
    setVerifyResult(null);

    try {
      const isValid = await verifyJDownloaderCredentials({
        email: formData.email,
        password: formData.password,
        device_name: formData.deviceName || undefined,
      });

      if (isValid) {
        setVerifyResult({ success: true, message: 'Credentials verified successfully!' });
      } else {
        setVerifyResult({ success: false, message: 'Invalid credentials. Please check your email and password.' });
      }
    } catch (error) {
      setVerifyResult({
        success: false,
        message: error instanceof Error ? error.message : 'Verification failed',
      });
    } finally {
      setIsVerifying(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    saveMutation.mutate({
      email: formData.email,
      password: formData.password,
      device_name: formData.deviceName || undefined,
      auto_reconnect: formData.autoReconnect,
      max_downloads: formData.maxDownloads,
      max_speed: formData.maxSpeed,
    });
  };

  const isLoading = statusLoading || configLoading;

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
            <p className="text-text-secondary mt-1">Configure Kuasarr and JDownloader settings</p>
          </div>
          <JDStatusBadge status={jdStatus || undefined} />
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-2 border-b border-bg-tertiary">
          <button
            onClick={() => setActiveTab('jdownloader')}
            className={`px-4 py-2 text-sm font-medium transition-colors relative ${
              activeTab === 'jdownloader'
                ? 'text-kuasarr-primary'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            <span className="flex items-center gap-2">
              <Zap className="h-4 w-4" />
              JDownloader
            </span>
            {activeTab === 'jdownloader' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-kuasarr-primary" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('general')}
            className={`px-4 py-2 text-sm font-medium transition-colors relative ${
              activeTab === 'general'
                ? 'text-kuasarr-primary'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            <span className="flex items-center gap-2">
              <Settings className="h-4 w-4" />
              General
            </span>
            {activeTab === 'general' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-kuasarr-primary" />
            )}
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : activeTab === 'jdownloader' ? (
          <div className="space-y-6">
            {/* Connection Status Card */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Server className="h-5 w-5" />
                  Connection Status
                </CardTitle>
              </CardHeader>
              <CardContent>
                {jdStatus ? (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 bg-bg-tertiary/50 rounded-lg">
                      <p className="text-text-secondary text-sm">Status</p>
                      <p className={`font-medium ${jdStatus.connected ? 'text-kuasarr-success' : 'text-kuasarr-error'}`}>
                        {jdStatus.connected ? 'Connected' : 'Disconnected'}
                      </p>
                    </div>
                    <div className="p-4 bg-bg-tertiary/50 rounded-lg">
                      <p className="text-text-secondary text-sm">Device</p>
                      <p className="font-medium text-text-primary">{jdStatus.device_name || 'Unknown'}</p>
                    </div>
                    <div className="p-4 bg-bg-tertiary/50 rounded-lg">
                      <p className="text-text-secondary text-sm">Active Downloads</p>
                      <p className="font-medium text-text-primary">{jdStatus.active_downloads}</p>
                    </div>
                    <div className="p-4 bg-bg-tertiary/50 rounded-lg">
                      <p className="text-text-secondary text-sm">Global Speed</p>
                      <p className="font-medium text-text-primary">
                        {jdStatus.global_speed > 0
                          ? `${(jdStatus.global_speed / 1024 / 1024).toFixed(2)} MB/s`
                          : '0 MB/s'}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-text-secondary">
                    <p>Unable to fetch JDownloader status</p>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="mt-4"
                      onClick={() => refetchStatus()}
                      leftIcon={<RefreshCw className="h-4 w-4" />}
                    >
                      Retry
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Configuration Form */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Settings className="h-5 w-5" />
                  JDownloader Configuration
                </CardTitle>
                <CardDescription>
                  Configure your My-JDownloader account credentials
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSave} className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Input
                      label="Email"
                      type="email"
                      placeholder="your@email.com"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      error={formErrors.email}
                      leftIcon={<User className="h-4 w-4" />}
                      required
                    />
                    <div className="relative">
                      <Input
                        label="Password"
                        type={showPassword ? 'text' : 'password'}
                        placeholder="••••••••"
                        value={formData.password}
                        onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                        error={formErrors.password}
                        leftIcon={<Lock className="h-4 w-4" />}
                        rightIcon={
                          <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            className="text-text-secondary hover:text-text-primary"
                          >
                            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        }
                        required
                      />
                    </div>
                  </div>

                  <Input
                    label="Device Name (Optional)"
                    placeholder="My JDownloader"
                    value={formData.deviceName}
                    onChange={(e) => setFormData({ ...formData, deviceName: e.target.value })}
                    helperText="Leave empty to use the default device"
                  />

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Input
                      label="Max Concurrent Downloads"
                      type="number"
                      min={1}
                      max={20}
                      value={formData.maxDownloads.toString()}
                      onChange={(e) => setFormData({ ...formData, maxDownloads: parseInt(e.target.value) || 3 })}
                      leftIcon={<Gauge className="h-4 w-4" />}
                    />
                    <Input
                      label="Max Speed (KB/s, 0 = unlimited)"
                      type="number"
                      min={0}
                      value={formData.maxSpeed.toString()}
                      onChange={(e) => setFormData({ ...formData, maxSpeed: parseInt(e.target.value) || 0 })}
                      leftIcon={<Zap className="h-4 w-4" />}
                    />
                  </div>

                  <Toggle
                    label="Auto Reconnect"
                    description="Automatically reconnect if connection is lost"
                    checked={formData.autoReconnect}
                    onChange={(checked) => setFormData({ ...formData, autoReconnect: checked })}
                  />

                  {verifyResult && (
                    <div
                      className={`p-4 rounded-lg flex items-start gap-3 ${
                        verifyResult.success
                          ? 'bg-kuasarr-success/10 border border-kuasarr-success/30'
                          : 'bg-kuasarr-error/10 border border-kuasarr-error/30'
                      }`}
                    >
                      {verifyResult.success ? (
                        <Check className="h-5 w-5 text-kuasarr-success mt-0.5" />
                      ) : (
                        <AlertCircle className="h-5 w-5 text-kuasarr-error mt-0.5" />
                      )}
                      <p className={verifyResult.success ? 'text-kuasarr-success' : 'text-kuasarr-error'}>
                        {verifyResult.message}
                      </p>
                    </div>
                  )}

                  <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-bg-tertiary">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleVerify}
                      loading={isVerifying}
                      leftIcon={<Check className="h-4 w-4" />}
                    >
                      Test Connection
                    </Button>
                    <Button
                      type="submit"
                      variant="primary"
                      loading={saveMutation.isPending}
                      leftIcon={<Save className="h-4 w-4" />}
                    >
                      Save Settings
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16">
              <Settings className="h-16 w-16 text-text-secondary/50 mb-4" />
              <h3 className="text-lg font-medium text-text-primary">General Settings</h3>
              <p className="text-text-secondary text-sm mt-1 text-center max-w-md">
                Additional general settings will be available in a future update.
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
