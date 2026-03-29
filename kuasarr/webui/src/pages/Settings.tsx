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
  Globe,
  Shield,
  Link2,
  Network,
  SlidersHorizontal,
  Info,
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
  getGeneralSettings,
  saveGeneralSettings,
  getCaptchaSettings,
  saveCaptchaSettings,
  getIntegrationSettings,
  saveIntegrationSettings,
  getHostnamesSettings,
  saveHostnamesSettings,
  getAdvancedSettings,
  saveAdvancedSettings,
} from '../lib/api';
import { useUIStore } from '../stores/uiStore';
import type {
  JDownloaderStatus,
  GeneralSettings,
  CaptchaSettings,
  IntegrationSettings,
  HostnamesSettings,
  AdvancedSettings,
} from '../types';

// ============================================================================
// Types
// ============================================================================

type SettingsTab = 'jdownloader' | 'general' | 'captcha' | 'integrations' | 'hostnames' | 'advanced';

interface JDFormData {
  email: string;
  password: string;
  deviceName: string;
  autoReconnect: boolean;
  maxDownloads: number;
  maxSpeed: number;
}

type FeedbackResult = { success: boolean; message: string } | null;

const HOSTNAME_SITES = [
  'ad', 'al', 'at', 'by', 'dd', 'dl', 'dt', 'dw', 'fx', 'he',
  'hs', 'mb', 'nk', 'nx', 'rm', 'sf', 'sl', 'wd', 'wx', 'sj', 'dj',
] as const;

// ============================================================================
// Helper components
// ============================================================================

function JDStatusBadge({ status }: { status?: JDownloaderStatus }) {
  if (!status) return <Badge variant="default">Unknown</Badge>;
  return (
    <Badge variant={status.connected ? 'success' : 'error'} dot>
      {status.connected ? 'Connected' : 'Disconnected'}
    </Badge>
  );
}

function FeedbackBanner({ result }: { result: FeedbackResult }) {
  if (!result) return null;
  return (
    <div
      className={`p-4 rounded-lg flex items-start gap-3 ${
        result.success
          ? 'bg-kuasarr-success/10 border border-kuasarr-success/30'
          : 'bg-kuasarr-error/10 border border-kuasarr-error/30'
      }`}
    >
      {result.success ? (
        <Check className="h-5 w-5 text-kuasarr-success mt-0.5 shrink-0" />
      ) : (
        <AlertCircle className="h-5 w-5 text-kuasarr-error mt-0.5 shrink-0" />
      )}
      <p className={result.success ? 'text-kuasarr-success' : 'text-kuasarr-error'}>
        {result.message}
      </p>
    </div>
  );
}

function SecretHelper({ isSet }: { isSet: boolean }) {
  if (!isSet) return null;
  return (
    <p className="text-xs text-text-secondary mt-1 flex items-center gap-1">
      <Info className="h-3 w-3" />
      Value is configured. Leave empty to keep existing.
    </p>
  );
}

function PasswordInput({
  label,
  value,
  onChange,
  isSet,
  placeholder,
  helperText,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  isSet?: boolean;
  placeholder?: string;
  helperText?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <Input
        label={label}
        type={show ? 'text' : 'password'}
        placeholder={isSet && !value ? '••••••••  (configured)' : (placeholder ?? '••••••••')}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        helperText={helperText}
        leftIcon={<Lock className="h-4 w-4" />}
        rightIcon={
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="text-text-secondary hover:text-text-primary"
          >
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        }
      />
      <SecretHelper isSet={!!isSet && !value} />
    </div>
  );
}

// ============================================================================
// Tab: JDownloader (unchanged)
// ============================================================================

function JDownloaderTab() {
  const { setJdConnected, setJdStatus } = useUIStore();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<JDFormData>({
    email: '',
    password: '',
    deviceName: '',
    autoReconnect: true,
    maxDownloads: 3,
    maxSpeed: 0,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [result, setResult] = useState<FeedbackResult>(null);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof JDFormData, string>>>({});

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
      setResult({ success: true, message: 'Settings saved successfully!' });
      setTimeout(() => setResult(null), 5000);
    },
    onError: (error) => {
      setResult({ success: false, message: error instanceof Error ? error.message : 'Failed to save settings' });
    },
  });

  const validateForm = (): boolean => {
    const errors: Partial<Record<keyof JDFormData, string>> = {};
    if (!formData.email.trim()) errors.email = 'Email is required';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) errors.email = 'Please enter a valid email';
    if (!formData.password.trim()) errors.password = 'Password is required';
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleVerify = async () => {
    if (!validateForm()) return;
    setIsVerifying(true);
    setResult(null);
    try {
      const isValid = await verifyJDownloaderCredentials({
        email: formData.email,
        password: formData.password,
        device_name: formData.deviceName || undefined,
      });
      setResult(
        isValid
          ? { success: true, message: 'Credentials verified successfully!' }
          : { success: false, message: 'Invalid credentials. Please check your email and password.' }
      );
    } catch (error) {
      setResult({ success: false, message: error instanceof Error ? error.message : 'Verification failed' });
    } finally {
      setIsVerifying(false);
    }
  };

  const handleSave = (e: React.FormEvent) => {
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

  if (statusLoading || configLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
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
              <Button variant="secondary" size="sm" className="mt-4" onClick={() => refetchStatus()} leftIcon={<RefreshCw className="h-4 w-4" />}>
                Retry
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            JDownloader Configuration
          </CardTitle>
          <CardDescription>Configure your My-JDownloader account credentials</CardDescription>
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
                  autoComplete="current-password"
                  leftIcon={<Lock className="h-4 w-4" />}
                  rightIcon={
                    <button type="button" onClick={() => setShowPassword(!showPassword)} className="text-text-secondary hover:text-text-primary">
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
            <FeedbackBanner result={result} />
            <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-bg-tertiary">
              <Button type="button" variant="secondary" onClick={handleVerify} loading={isVerifying} leftIcon={<Check className="h-4 w-4" />}>
                Test Connection
              </Button>
              <Button type="submit" variant="primary" loading={saveMutation.isPending} leftIcon={<Save className="h-4 w-4" />}>
                Save Settings
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================================
// Tab: General
// ============================================================================

function GeneralTab() {
  const [form, setForm] = useState<Omit<GeneralSettings, '_is_set'>>({
    internal_address: '',
    external_address: '',
    timezone: 'Europe/Berlin',
    slow_mode: false,
    flaresolverr_url: '',
    webui_user: '',
    webui_password: '',
  });
  const [isSet, setIsSet] = useState<Record<string, boolean>>({});
  const [result, setResult] = useState<FeedbackResult>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'general'],
    queryFn: getGeneralSettings,
  });

  useEffect(() => {
    if (data) {
      setForm({
        internal_address: data.internal_address,
        external_address: data.external_address,
        timezone: data.timezone,
        slow_mode: data.slow_mode,
        flaresolverr_url: data.flaresolverr_url,
        webui_user: '',
        webui_password: '',
      });
      setIsSet(data._is_set || {});
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: saveGeneralSettings,
    onSuccess: () => {
      setResult({ success: true, message: 'General settings saved successfully!' });
      setTimeout(() => setResult(null), 5000);
    },
    onError: (error) => {
      setResult({ success: false, message: error instanceof Error ? error.message : 'Failed to save settings' });
    },
  });

  if (isLoading) return <div className="flex items-center justify-center py-12"><Spinner size="lg" /></div>;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(form);
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* Connection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            Connection
          </CardTitle>
          <CardDescription>Addresses used by Radarr/Sonarr to reach Kuasarr</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            label="Internal Address"
            placeholder="http://kuasarr:8080"
            value={form.internal_address}
            onChange={(e) => setForm({ ...form, internal_address: e.target.value })}
            helperText="Used by Radarr/Sonarr inside your network (e.g. http://192.168.1.10:8080)"
          />
          <Input
            label="External Address (optional)"
            placeholder="https://kuasarr.example.com"
            value={form.external_address}
            onChange={(e) => setForm({ ...form, external_address: e.target.value })}
            helperText="Public URL if Kuasarr is exposed externally"
          />
          <Input
            label="Timezone"
            placeholder="Europe/Berlin"
            value={form.timezone}
            onChange={(e) => setForm({ ...form, timezone: e.target.value })}
            helperText="IANA timezone identifier, e.g. America/New_York"
          />
          <Toggle
            label="Slow Mode"
            description="Enable 3× timeout multiplier for slow or unstable connections"
            checked={form.slow_mode}
            onChange={(checked) => setForm({ ...form, slow_mode: checked })}
          />
        </CardContent>
      </Card>

      {/* FlareSolverr */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            FlareSolverr
          </CardTitle>
          <CardDescription>Proxy service for bypassing Cloudflare protection</CardDescription>
        </CardHeader>
        <CardContent>
          <Input
            label="FlareSolverr URL"
            placeholder="http://flaresolverr:8191/v1"
            value={form.flaresolverr_url}
            onChange={(e) => setForm({ ...form, flaresolverr_url: e.target.value })}
            helperText="Must include the /v1 path suffix. Requires FlareSolverr ≥ 3.4.4"
          />
        </CardContent>
      </Card>

      {/* WebUI Auth */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            WebUI Authentication
          </CardTitle>
          <CardDescription>Optional HTTP Basic Auth for the web interface</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Input
              label="Username"
              placeholder={isSet['webui_user'] ? '(configured)' : 'Leave empty to disable auth'}
              value={form.webui_user}
              onChange={(e) => setForm({ ...form, webui_user: e.target.value })}
              leftIcon={<User className="h-4 w-4" />}
            />
            <SecretHelper isSet={!!isSet['webui_user'] && !form.webui_user} />
          </div>
          <PasswordInput
            label="Password"
            value={form.webui_password}
            onChange={(v) => setForm({ ...form, webui_password: v })}
            isSet={isSet['webui_password']}
          />
          <p className="text-xs text-text-secondary">
            API endpoints are never protected — auth applies to the web UI only.
          </p>
        </CardContent>
      </Card>

      <FeedbackBanner result={result} />
      <div className="flex justify-end pt-2">
        <Button type="submit" variant="primary" loading={saveMutation.isPending} leftIcon={<Save className="h-4 w-4" />}>
          Save General Settings
        </Button>
      </div>
    </form>
  );
}

// ============================================================================
// Tab: Captcha
// ============================================================================

function CaptchaTab() {
  const [form, setForm] = useState<Omit<CaptchaSettings, '_is_set'>>({
    service: 'dbc',
    dbc_authtoken: '',
    twocaptcha_api_key: '',
    timeout: '120',
    max_retries: '3',
    retry_backoff: '5',
  });
  const [isSet, setIsSet] = useState<Record<string, boolean>>({});
  const [result, setResult] = useState<FeedbackResult>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'captcha'],
    queryFn: getCaptchaSettings,
  });

  useEffect(() => {
    if (data) {
      setForm({
        service: data.service,
        dbc_authtoken: '',
        twocaptcha_api_key: '',
        timeout: data.timeout,
        max_retries: data.max_retries,
        retry_backoff: data.retry_backoff,
      });
      setIsSet(data._is_set || {});
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: saveCaptchaSettings,
    onSuccess: () => {
      setResult({ success: true, message: 'Captcha settings saved successfully!' });
      setTimeout(() => setResult(null), 5000);
    },
    onError: (error) => {
      setResult({ success: false, message: error instanceof Error ? error.message : 'Failed to save settings' });
    },
  });

  if (isLoading) return <div className="flex items-center justify-center py-12"><Spinner size="lg" /></div>;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(form);
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* Service selection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            CAPTCHA Service
          </CardTitle>
          <CardDescription>Select a service and provide credentials for CAPTCHA solving</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-text-primary">Service</label>
            <div className="flex flex-col sm:flex-row gap-3">
              {(['dbc', '2captcha'] as const).map((svc) => (
                <label
                  key={svc}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    form.service === svc
                      ? 'border-kuasarr-primary bg-kuasarr-primary/10'
                      : 'border-bg-tertiary hover:border-text-secondary'
                  }`}
                >
                  <input
                    type="radio"
                    name="captcha_service"
                    value={svc}
                    checked={form.service === svc}
                    onChange={() => setForm({ ...form, service: svc })}
                    className="accent-kuasarr-primary"
                  />
                  <div>
                    <span className="text-sm font-medium text-text-primary">
                      {svc === 'dbc' ? 'DeathByCaptcha' : '2Captcha'}
                    </span>
                    {svc === '2captcha' && (
                      <p className="text-xs text-text-secondary">50% cheaper for CutCaptcha</p>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>

          {form.service === 'dbc' ? (
            <PasswordInput
              label="DBC Auth Token"
              value={form.dbc_authtoken}
              onChange={(v) => setForm({ ...form, dbc_authtoken: v })}
              isSet={isSet['dbc_authtoken']}
              placeholder="your_dbc_auth_token"
              helperText="Get your token at deathbycaptcha.com"
            />
          ) : (
            <PasswordInput
              label="2Captcha API Key"
              value={form.twocaptcha_api_key}
              onChange={(v) => setForm({ ...form, twocaptcha_api_key: v })}
              isSet={isSet['twocaptcha_api_key']}
              placeholder="your_2captcha_api_key"
              helperText="Get your key at 2captcha.com"
            />
          )}
        </CardContent>
      </Card>

      {/* Timing */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gauge className="h-5 w-5" />
            Timing
          </CardTitle>
          <CardDescription>Retry and timeout behaviour for CAPTCHA solving</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Input
              label="Timeout (seconds)"
              type="number"
              min={10}
              value={form.timeout}
              onChange={(e) => setForm({ ...form, timeout: e.target.value })}
            />
            <Input
              label="Max Retries"
              type="number"
              min={1}
              max={10}
              value={form.max_retries}
              onChange={(e) => setForm({ ...form, max_retries: e.target.value })}
            />
            <Input
              label="Retry Backoff (seconds)"
              type="number"
              min={1}
              value={form.retry_backoff}
              onChange={(e) => setForm({ ...form, retry_backoff: e.target.value })}
            />
          </div>
        </CardContent>
      </Card>

      <FeedbackBanner result={result} />
      <div className="flex justify-end pt-2">
        <Button type="submit" variant="primary" loading={saveMutation.isPending} leftIcon={<Save className="h-4 w-4" />}>
          Save Captcha Settings
        </Button>
      </div>
    </form>
  );
}

// ============================================================================
// Tab: Integrations
// ============================================================================

function IntegrationsTab() {
  const [form, setForm] = useState<Omit<IntegrationSettings, '_is_set'>>({
    sonarr_url: '',
    sonarr_api_key: '',
    radarr_url: '',
    radarr_api_key: '',
  });
  const [isSet, setIsSet] = useState<Record<string, boolean>>({});
  const [result, setResult] = useState<FeedbackResult>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'integrations'],
    queryFn: getIntegrationSettings,
  });

  useEffect(() => {
    if (data) {
      setForm({
        sonarr_url: data.sonarr_url,
        sonarr_api_key: '',
        radarr_url: data.radarr_url,
        radarr_api_key: '',
      });
      setIsSet(data._is_set || {});
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: saveIntegrationSettings,
    onSuccess: () => {
      setResult({ success: true, message: 'Integration settings saved successfully!' });
      setTimeout(() => setResult(null), 5000);
    },
    onError: (error) => {
      setResult({ success: false, message: error instanceof Error ? error.message : 'Failed to save settings' });
    },
  });

  if (isLoading) return <div className="flex items-center justify-center py-12"><Spinner size="lg" /></div>;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(form);
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      <p className="text-sm text-text-secondary">
        Kuasarr uses these connections to trigger post-download rescans in Sonarr and Radarr.
      </p>

      {/* Sonarr */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5" />
            Sonarr
          </CardTitle>
          <CardDescription>TV show library manager — Series type must be "Standard"</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            label="Sonarr URL"
            placeholder="http://sonarr:8989"
            value={form.sonarr_url}
            onChange={(e) => setForm({ ...form, sonarr_url: e.target.value })}
          />
          <PasswordInput
            label="API Key"
            value={form.sonarr_api_key}
            onChange={(v) => setForm({ ...form, sonarr_api_key: v })}
            isSet={isSet['sonarr_api_key']}
            helperText="Found in Sonarr → Settings → General → Security"
          />
        </CardContent>
      </Card>

      {/* Radarr */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5" />
            Radarr
          </CardTitle>
          <CardDescription>Movie library manager</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            label="Radarr URL"
            placeholder="http://radarr:7878"
            value={form.radarr_url}
            onChange={(e) => setForm({ ...form, radarr_url: e.target.value })}
          />
          <PasswordInput
            label="API Key"
            value={form.radarr_api_key}
            onChange={(v) => setForm({ ...form, radarr_api_key: v })}
            isSet={isSet['radarr_api_key']}
            helperText="Found in Radarr → Settings → General → Security"
          />
        </CardContent>
      </Card>

      <FeedbackBanner result={result} />
      <div className="flex justify-end pt-2">
        <Button type="submit" variant="primary" loading={saveMutation.isPending} leftIcon={<Save className="h-4 w-4" />}>
          Save Integration Settings
        </Button>
      </div>
    </form>
  );
}

// ============================================================================
// Tab: Hostnames
// ============================================================================

function HostnamesTab() {
  const emptyHostnames = Object.fromEntries(
    HOSTNAME_SITES.map((s) => [s, ''])
  ) as unknown as HostnamesSettings;

  const [form, setForm] = useState<HostnamesSettings>(emptyHostnames);
  const [result, setResult] = useState<FeedbackResult>(null);
  const [restartSites, setRestartSites] = useState<string[]>([]);

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'hostnames'],
    queryFn: getHostnamesSettings,
  });

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: saveHostnamesSettings,
    onSuccess: (res) => {
      const restart = res.requires_restart || [];
      setRestartSites(restart);
      setResult({
        success: true,
        message: restart.length
          ? `Saved! Restart required for changes to: ${restart.join(', ')}`
          : 'Hostname settings saved successfully!',
      });
      setTimeout(() => setResult(null), 8000);
    },
    onError: (error) => {
      setResult({ success: false, message: error instanceof Error ? error.message : 'Failed to save settings' });
    },
  });

  if (isLoading) return <div className="flex items-center justify-center py-12"><Spinner size="lg" /></div>;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setRestartSites([]);
    saveMutation.mutate(form);
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Network className="h-5 w-5" />
            Scraper Hostnames
          </CardTitle>
          <CardDescription>
            Enter the hostname for each DDL site you want to scrape. Leave empty to disable a site.
            Kuasarr never bundles hostnames — you must provide them yourself.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {restartSites.length > 0 && (
            <div className="mb-4 p-3 rounded-lg bg-kuasarr-primary/10 border border-kuasarr-primary/30 flex items-start gap-2">
              <Info className="h-4 w-4 text-kuasarr-primary mt-0.5 shrink-0" />
              <p className="text-sm text-kuasarr-primary">
                A restart is required for changes to: <strong>{restartSites.join(', ')}</strong>
              </p>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {HOSTNAME_SITES.map((site) => (
              <Input
                key={site}
                label={site.toUpperCase()}
                placeholder="example.com"
                value={form[site]}
                onChange={(e) => setForm({ ...form, [site]: e.target.value })}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      <FeedbackBanner result={result} />
      <div className="flex justify-end pt-2">
        <Button type="submit" variant="primary" loading={saveMutation.isPending} leftIcon={<Save className="h-4 w-4" />}>
          Save Hostname Settings
        </Button>
      </div>
    </form>
  );
}

// ============================================================================
// Tab: Advanced
// ============================================================================

function AdvancedTab() {
  const [form, setForm] = useState<Omit<AdvancedSettings, '_is_set'>>({
    flatten_nested_folders: true,
    trigger_rescan: true,
    xrel_enabled: false,
    xrel_filter_nuked: false,
    hidecx_api_key: '',
  });
  const [isSet, setIsSet] = useState<Record<string, boolean>>({});
  const [result, setResult] = useState<FeedbackResult>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'advanced'],
    queryFn: getAdvancedSettings,
  });

  useEffect(() => {
    if (data) {
      setForm({
        flatten_nested_folders: data.flatten_nested_folders,
        trigger_rescan: data.trigger_rescan,
        xrel_enabled: data.xrel_enabled,
        xrel_filter_nuked: data.xrel_filter_nuked,
        hidecx_api_key: '',
      });
      setIsSet(data._is_set || {});
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: saveAdvancedSettings,
    onSuccess: () => {
      setResult({ success: true, message: 'Advanced settings saved successfully!' });
      setTimeout(() => setResult(null), 5000);
    },
    onError: (error) => {
      setResult({ success: false, message: error instanceof Error ? error.message : 'Failed to save settings' });
    },
  });

  if (isLoading) return <div className="flex items-center justify-center py-12"><Spinner size="lg" /></div>;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(form);
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* Post-Processing */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SlidersHorizontal className="h-5 w-5" />
            Post-Processing
          </CardTitle>
          <CardDescription>Actions taken after a download completes</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Toggle
            label="Flatten Nested Folders"
            description="Move files from sub-directories up into the package folder"
            checked={form.flatten_nested_folders}
            onChange={(checked) => setForm({ ...form, flatten_nested_folders: checked })}
          />
          <Toggle
            label="Trigger Rescan"
            description="Notify Radarr/Sonarr to rescan the download folder after completion"
            checked={form.trigger_rescan}
            onChange={(checked) => setForm({ ...form, trigger_rescan: checked })}
          />
        </CardContent>
      </Card>

      {/* XRel */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            xREL
          </CardTitle>
          <CardDescription>Use xREL.to for release size lookups</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Toggle
            label="Enable xREL"
            description="Fetch release sizes from xREL.to to improve Radarr/Sonarr matching"
            checked={form.xrel_enabled}
            onChange={(checked) => setForm({ ...form, xrel_enabled: checked })}
          />
          <Toggle
            label="Filter Nuked Releases"
            description="Hide releases that have been marked as nuked on xREL.to"
            checked={form.xrel_filter_nuked}
            onChange={(checked) => setForm({ ...form, xrel_filter_nuked: checked })}
          />
        </CardContent>
      </Card>

      {/* HideCX */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lock className="h-5 w-5" />
            hide.cx
          </CardTitle>
          <CardDescription>Integration with hide.cx link protection service</CardDescription>
        </CardHeader>
        <CardContent>
          <PasswordInput
            label="API Key"
            value={form.hidecx_api_key}
            onChange={(v) => setForm({ ...form, hidecx_api_key: v })}
            isSet={isSet['hidecx_api_key']}
            helperText="Get your key at hide.cx → Settings → Account → Application API Keys"
          />
        </CardContent>
      </Card>

      <FeedbackBanner result={result} />
      <div className="flex justify-end pt-2">
        <Button type="submit" variant="primary" loading={saveMutation.isPending} leftIcon={<Save className="h-4 w-4" />}>
          Save Advanced Settings
        </Button>
      </div>
    </form>
  );
}

// ============================================================================
// Main Settings Page
// ============================================================================

const TABS: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
  { id: 'jdownloader', label: 'JDownloader', icon: <Zap className="h-4 w-4" /> },
  { id: 'general', label: 'General', icon: <Globe className="h-4 w-4" /> },
  { id: 'captcha', label: 'Captcha', icon: <Shield className="h-4 w-4" /> },
  { id: 'integrations', label: 'Integrations', icon: <Link2 className="h-4 w-4" /> },
  { id: 'hostnames', label: 'Hostnames', icon: <Network className="h-4 w-4" /> },
  { id: 'advanced', label: 'Advanced', icon: <SlidersHorizontal className="h-4 w-4" /> },
];

export default function SettingsPage() {
  const { jdConnected } = useUIStore();
  const [activeTab, setActiveTab] = useState<SettingsTab>('jdownloader');

  const { data: jdStatus } = useQuery({
    queryKey: ['jdownloader', 'status'],
    queryFn: getJDownloaderStatus,
    refetchInterval: 30000,
  });

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
            <p className="text-text-secondary mt-1">Configure Kuasarr and all connected services</p>
          </div>
          <JDStatusBadge status={jdStatus || undefined} />
        </div>

        {/* Tab Navigation */}
        <div className="flex flex-wrap gap-1 border-b border-bg-tertiary">
          {TABS.map(({ id, label, icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`px-4 py-2 text-sm font-medium transition-colors relative ${
                activeTab === id ? 'text-kuasarr-primary' : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <span className="flex items-center gap-2">
                {icon}
                {label}
              </span>
              {activeTab === id && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-kuasarr-primary" />
              )}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'jdownloader' && <JDownloaderTab />}
        {activeTab === 'general' && <GeneralTab />}
        {activeTab === 'captcha' && <CaptchaTab />}
        {activeTab === 'integrations' && <IntegrationsTab />}
        {activeTab === 'hostnames' && <HostnamesTab />}
        {activeTab === 'advanced' && <AdvancedTab />}
      </div>
    </Layout>
  );
}
