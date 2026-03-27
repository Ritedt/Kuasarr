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
  NotificationConfig,
  TestNotificationRequest,
  PausePackageRequest,
  ResumePackageRequest,
  DeletePackageRequest,
} from '../types';

const API_BASE = '/api';
const _API_KEY = typeof window !== 'undefined' ? window.KUASARR_API_KEY : undefined;

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(_API_KEY ? { 'X-API-Key': _API_KEY } : {}),
    ...(options?.headers as Record<string, string> | undefined),
  };

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: { message: 'Unknown error' } }));
    throw new Error(error.error?.message || `HTTP ${response.status}`);
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

export async function getPackageById(packageId: string): Promise<Package | null> {
  const response = await fetchApi<Package>(`/packages/${packageId}`);
  return response.data || null;
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

export async function getSearchStatus(searchId: string): Promise<{ status: 'pending' | 'completed' | 'failed'; results?: SearchResult[] }> {
  const response = await fetchApi<{ status: 'pending' | 'completed' | 'failed'; results?: SearchResult[] }>(`/search/status/${searchId}`);
  return response.data || { status: 'failed' };
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
  await fetchApi<void>('/jdownloader/config', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Statistics API
export async function getStatistics(): Promise<Statistics | null> {
  const response = await fetchApi<Statistics>('/statistics');
  return response.data || null;
}

export async function getStatisticsHistory(days = 30): Promise<Statistics['daily_stats']> {
  const response = await fetchApi<Statistics['daily_stats']>(`/statistics/history?days=${days}`);
  return response.data || [];
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

export async function addNotificationConfig(config: NotificationConfig): Promise<NotificationConfig> {
  const response = await fetchApi<NotificationConfig>('/notifications/configs', {
    method: 'POST',
    body: JSON.stringify(config),
  });
  if (!response.data) throw new Error('Failed to add notification config');
  return response.data;
}

export async function updateNotificationConfig(configId: string, config: Partial<NotificationConfig>): Promise<NotificationConfig> {
  const response = await fetchApi<NotificationConfig>(`/notifications/configs/${configId}`, {
    method: 'POST',
    body: JSON.stringify(config),
  });
  if (!response.data) throw new Error('Failed to update notification config');
  return response.data;
}

export async function deleteNotificationConfig(configId: string): Promise<void> {
  await fetchApi<void>(`/notifications/configs/${configId}`, {
    method: 'DELETE',
  });
}
