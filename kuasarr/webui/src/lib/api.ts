// API Client for Kuasarr WebUI
import type {
  ApiResponse,
  Category,
  CreateCategoryRequest,
  UpdateCategoryRequest,
  Hoster,
  Package,
  SearchResult,
  SearchRequest,
  DownloadSearchResultRequest,
  JDownloaderStatus,
  JDownloaderConfig,
  VerifyJDownloaderRequest,
  SaveJDownloaderRequest,
  Statistics,
  NotificationSettings,
  TestNotificationRequest,
  PausePackageRequest,
  ResumePackageRequest,
  DeletePackageRequest,
  GeneralSettings,
  CaptchaSettings,
  IntegrationSettings,
  HostnamesSettings,
  HostnamesSaveResponse,
  AdvancedSettings,
  VersionInfo,
  SjdjSettings,
} from '../types';

const API_BASE = '/api';

// API key is fetched from /api/key after browser authentication.
// It is never embedded in the HTML source.
let _resolvedApiKey: string | undefined;
let _keyFetchPromise: Promise<string | undefined> | null = null;

async function _fetchApiKey(): Promise<string | undefined> {
  if (_resolvedApiKey !== undefined) return _resolvedApiKey;
  if (_keyFetchPromise) return _keyFetchPromise;
  _keyFetchPromise = fetch('/api/key', { credentials: 'include' })
    .then((res) => res.ok ? res.json() : null)
    .then((data) => {
      _resolvedApiKey = data?.data?.key || '';
      return _resolvedApiKey;
    })
    .catch(() => {
      _resolvedApiKey = '';
      return _resolvedApiKey;
    });
  return _keyFetchPromise;
}

// CSRF token for state-changing requests. `/api/csrf` sets the `kuasarr_csrf`
// cookie the server compares the header against, so the token is fetched once
// and reused - and the cookie has to travel with every mutating request.
let _resolvedCsrfToken: string | undefined;
let _csrfFetchPromise: Promise<string> | null = null;

async function _fetchCsrfToken(): Promise<string> {
  if (_resolvedCsrfToken !== undefined) return _resolvedCsrfToken;
  if (_csrfFetchPromise) return _csrfFetchPromise;
  _csrfFetchPromise = fetch('/api/csrf', { credentials: 'include' })
    .then((res) => res.ok ? res.json() : null)
    .then((data) => data?.data?.csrf_token || '')
    .catch(() => {
      // Fehlt das Token, ist das kein Grund abzubrechen: der eigentliche
      // API-Aufruf laeuft ohnehin und liefert mit 403 die echte Meldung
      // ("Invalid or missing CSRF token"). Hier zu werfen wuerde sie nur eine
      // generische Fehlermeldung anzeigen.
      return '';
    })
    .then((token) => {
      _resolvedCsrfToken = token;
      return token;
    });
  return _csrfFetchPromise;
}

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Zieht die Meldung aus der Fehlerhuelle. Normalfall ist
 * `{"error": {"message": "..."}}`; einige Handler antworten noch flach mit
 * `{"error": "text"}`, das wird hier mitgelesen, damit nicht jedes Mal nur
 * "HTTP 404" ohne Ursache in der Oberflaeche landet.
 */
async function readErrorMessage(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null);
  const error = payload?.error;
  if (typeof error === 'string' && error) return error;
  if (error?.message) return error.message;
  return `HTTP ${response.status}`;
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const method = (options?.method || 'GET').toUpperCase();
  const isMutating = MUTATING_METHODS.has(method);

  // Beide Tokens unabhaengig voneinander holen: sie duerfen nicht aufeinander
  // warten, und ein GET braucht den CSRF-Token gar nicht erst.
  const [apiKey, csrfToken] = await Promise.all([
    _fetchApiKey(),
    isMutating ? _fetchCsrfToken() : Promise.resolve(''),
  ]);

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(apiKey ? { 'X-API-Key': apiKey } : {}),
    ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    ...(options?.headers as Record<string, string> | undefined),
  };

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    credentials: 'include',
    headers,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return response.json();
}

// Categories API
export async function getCategories(): Promise<Category[]> {
  const response = await fetchApi<Category[]>('/categories');
  return response.data || [];
}

export async function createCategory(data: CreateCategoryRequest): Promise<Category> {
  const response = await fetchApi<Category>('/categories', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!response.data) throw new Error('Failed to create category');
  return response.data;
}

export async function updateCategory(id: string, data: Partial<UpdateCategoryRequest>): Promise<Category> {
  const response = await fetchApi<Category>(`/categories/${id}`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!response.data) throw new Error('Failed to update category');
  return response.data;
}

export async function deleteCategory(id: string): Promise<void> {
  await fetchApi<void>(`/categories/${id}`, {
    method: 'DELETE',
  });
}

// Hosters API
export async function getHosters(): Promise<Hoster[]> {
  const response = await fetchApi<Hoster[]>('/hosters');
  return response.data || [];
}

export async function blockHoster(hosterId: string): Promise<void> {
  await fetchApi<void>('/hosters/block', {
    method: 'POST',
    body: JSON.stringify({ hoster_id: hosterId }),
  });
}

export async function unblockHoster(hosterId: string): Promise<void> {
  await fetchApi<void>('/hosters/unblock', {
    method: 'POST',
    body: JSON.stringify({ hoster_id: hosterId }),
  });
}

export async function blockAllHosters(): Promise<void> {
  await fetchApi<void>('/hosters/block-all', {
    method: 'POST',
  });
}

export async function unblockAllHosters(): Promise<void> {
  await fetchApi<void>('/hosters/unblock-all', {
    method: 'POST',
  });
}

// Packages API
export async function getPackages(status?: string): Promise<Package[]> {
  const endpoint = status ? `/packages?status=${encodeURIComponent(status)}` : '/packages';
  const response = await fetchApi<Package[]>(endpoint);
  return response.data || [];
}

export async function pausePackage(packageId: string): Promise<void> {
  const request: PausePackageRequest = { package_ids: [packageId] };
  await fetchApi<void>('/packages/pause', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function pausePackages(packageIds: string[]): Promise<void> {
  const request: PausePackageRequest = { package_ids: packageIds };
  await fetchApi<void>('/packages/pause', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function resumePackage(packageId: string): Promise<void> {
  const request: ResumePackageRequest = { package_ids: [packageId] };
  await fetchApi<void>('/packages/resume', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function resumePackages(packageIds: string[]): Promise<void> {
  const request: ResumePackageRequest = { package_ids: packageIds };
  await fetchApi<void>('/packages/resume', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function deletePackage(packageId: string, deleteFiles = false): Promise<void> {
  const request: DeletePackageRequest = { package_ids: [packageId], delete_files: deleteFiles };
  await fetchApi<void>('/packages/delete', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function deletePackages(packageIds: string[], deleteFiles = false): Promise<void> {
  const request: DeletePackageRequest = { package_ids: packageIds, delete_files: deleteFiles };
  await fetchApi<void>('/packages/delete', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

// Search API
export async function search(request: SearchRequest): Promise<SearchResult[]> {
  const response = await fetchApi<SearchResult[]>('/search', {
    method: 'POST',
    body: JSON.stringify(request),
  });
  return response.data || [];
}

export async function downloadSearchResult(
  request: DownloadSearchResultRequest
): Promise<void> {
  await fetchApi<void>('/search/download', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

// JDownloader API
export async function getJDownloaderStatus(): Promise<JDownloaderStatus> {
  const response = await fetchApi<JDownloaderStatus>('/jdownloader/status');
  return response.data || {
    connected: false,
    total_downloads: 0,
    active_downloads: 0,
    global_speed: 0,
    reconnect_enabled: false,
  };
}

export async function getJDownloaderConfig(): Promise<JDownloaderConfig | null> {
  const response = await fetchApi<JDownloaderConfig>('/jdownloader/config');
  return response.data || null;
}

export async function verifyJDownloaderCredentials(
  data: VerifyJDownloaderRequest
): Promise<boolean> {
  const response = await fetchApi<{ valid: boolean }>('/jdownloader/verify', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return response.data?.valid || false;
}

export async function saveJDownloaderConfig(data: SaveJDownloaderRequest): Promise<void> {
  // `/api/jdownloader/save` setzt echte Statuscodes: 400 bei Validierung,
  // 502 bei Verbindungsfehler. Deshalb nicht das flache `success`-Feld von
  // `/api/jdownloader/config` auswerten - ein Fehler wirft in fetchApi.
  const response = await fetchApi<{ success: boolean }>('/jdownloader/save', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!response.data?.success) {
    throw new Error('JDownloader settings could not be saved');
  }
}

// Statistics API
export async function getStatistics(): Promise<Statistics | null> {
  const response = await fetchApi<Statistics>('/statistics');
  return response.data || null;
}

// Notifications API
export async function getNotificationSettings(): Promise<NotificationSettings | null> {
  const response = await fetchApi<NotificationSettings>('/notifications');
  return response.data || null;
}

export async function saveNotificationSettings(settings: NotificationSettings): Promise<void> {
  await fetchApi<void>('/notifications', {
    method: 'POST',
    body: JSON.stringify(settings),
  });
}

export async function testNotification(request: TestNotificationRequest): Promise<{ success: boolean; message?: string }> {
  const response = await fetchApi<{ success: boolean; message?: string }>('/notifications/test', {
    method: 'POST',
    body: JSON.stringify(request),
  });
  return response.data || { success: false, message: 'Test failed' };
}

// General Settings API
export async function getGeneralSettings(): Promise<GeneralSettings | null> {
  const response = await fetchApi<GeneralSettings>('/settings/general-config');
  return response.data || null;
}

export async function saveGeneralSettings(data: Partial<GeneralSettings>): Promise<void> {
  await fetchApi<void>('/settings/general-config', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Captcha Settings API
export async function getCaptchaSettings(): Promise<CaptchaSettings | null> {
  const response = await fetchApi<CaptchaSettings>('/settings/captcha-config');
  return response.data || null;
}

export async function saveCaptchaSettings(data: Partial<CaptchaSettings>): Promise<void> {
  await fetchApi<void>('/settings/captcha-config', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Integration Settings API
export async function getIntegrationSettings(): Promise<IntegrationSettings | null> {
  const response = await fetchApi<IntegrationSettings>('/settings/integrations');
  return response.data || null;
}

export async function saveIntegrationSettings(data: Partial<IntegrationSettings>): Promise<void> {
  await fetchApi<void>('/settings/integrations', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Hostnames Settings API
export async function getHostnamesSettings(): Promise<HostnamesSettings | null> {
  const response = await fetchApi<HostnamesSettings>('/settings/hostnames-config');
  return response.data || null;
}

export async function saveHostnamesSettings(
  data: Partial<HostnamesSettings>
): Promise<{ requires_restart: string[] }> {
  // Diese Route legt `requires_restart` flach neben `success`/`message`,
  // nicht in `data` - deshalb wird hier nicht `response.data` ausgewertet.
  const response: HostnamesSaveResponse = await fetchApi<HostnamesSettings>(
    '/settings/hostnames-config',
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  );
  return { requires_restart: response.requires_restart || [] };
}

// SJ/DJ Credentials API
export async function getSjdjSettings(): Promise<SjdjSettings | null> {
  const response = await fetchApi<SjdjSettings>('/settings/sjdj-config');
  return response.data || null;
}

export async function saveSjdjSettings(data: Partial<SjdjSettings>): Promise<void> {
  await fetchApi<void>('/settings/sjdj-config', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Advanced Settings API
export async function getAdvancedSettings(): Promise<AdvancedSettings | null> {
  const response = await fetchApi<AdvancedSettings>('/settings/advanced-config');
  return response.data || null;
}

export async function saveAdvancedSettings(data: Partial<AdvancedSettings>): Promise<void> {
  await fetchApi<void>('/settings/advanced-config', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Version API
export async function getVersion(): Promise<VersionInfo | null> {
  // Bewusst ohne `?refresh=1`: der Live-Check gegen GitHub kann bis zu 10
  // Sekunden blockieren, und das darf die Sidebar nicht ausbremsen. `current`
  // kommt lokal aus `version.json` und ist damit immer vorhanden.
  const response = await fetchApi<VersionInfo>('/version');
  return response.data || null;
}
