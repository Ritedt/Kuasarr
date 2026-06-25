/**
 * TypeScript type definitions for Kuasarr WebUI
 */

// ============================================================================
// Category Types
// ============================================================================

export interface Category {
  id: string;
  name: string;
  pattern: string;
  priority: number;
  enabled: boolean;
  // Unix-Timestamp als Zahl. Das Backend schickt hier keinen ISO-String.
  created_at?: number;
}

export interface CreateCategoryRequest {
  name: string;
  pattern: string;
  priority?: number;
  enabled?: boolean;
}

export interface UpdateCategoryRequest {
  id: string;
  name?: string;
  pattern?: string;
  priority?: number;
  enabled?: boolean;
}

// ============================================================================
// Hoster Types
// ============================================================================

export interface Hoster {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  blocked: boolean;
  priority: number;
  last_checked?: string;
  status?: 'online' | 'offline' | 'unknown';
}

export interface BlockHosterRequest {
  hoster_id: string;
  reason?: string;
}

export interface UnblockHosterRequest {
  hoster_id: string;
}

// ============================================================================
// Package Types
// ============================================================================

export type PackageStatus = 'queued' | 'downloading' | 'paused' | 'completed' | 'failed' | 'extracting';

export interface Package {
  id: string;
  name: string;
  status: PackageStatus;
  progress: number;
  size: number;
  downloaded: number;
  speed: number;
  eta: number | null;
  links: PackageLink[];
  category?: string;
  created_at: string;
  updated_at: string;
}

export interface PackageLink {
  id: string;
  url: string;
  filename: string;
  status: 'queued' | 'downloading' | 'completed' | 'failed';
  progress: number;
  size: number;
  downloaded: number;
}

export interface DeletePackageRequest {
  package_ids: string[];
  delete_files?: boolean;
}

export interface PausePackageRequest {
  package_ids: string[];
}

export interface ResumePackageRequest {
  package_ids: string[];
}

// ============================================================================
// Search Types
// ============================================================================

export interface SearchResult {
  id: string;
  title: string;
  /** Groesse in Bytes. 0 heisst "unbekannt". */
  size: number;
  size_bytes: number;
  size_formatted: string;
  category: string;
  hoster: string;
  hostname: string;
  mirror: string;
  url: string;
  /** Der eigentliche Payload-Link, ueber den der Download laeuft. */
  link: string;
  source: string;
  password?: string;
  age: string;
  /** DDL-Portale liefern keine Grab-Zaehlung, der Wert ist immer 0. */
  grabs: number;
  // seeders/leechers/quality/language schickt das Backend bewusst nicht, damit
  // die WebUI sie ausblendet. Deshalb bleiben sie hier optional.
  seeders?: number;
  leechers?: number;
  quality?: string;
  language?: string;
  imdb_id?: string;
}

export interface SearchRequest {
  query: string;
  category?: string;
  limit?: number;
  offset?: number;
  min_size?: number;
  max_size?: number;
  // Das Backend wertet nur "size" und "age" aus; alles andere landet in
  // `unsupported` und wird nicht angewendet.
  sort_by?: 'size' | 'age';
  sort_order?: 'asc' | 'desc';
}

export interface DownloadSearchResultRequest {
  result_id: string;
  package_name?: string;
  category_id?: string;
  password?: string;
}

// ============================================================================
// JDownloader Types
// ============================================================================

export interface JDownloaderConfig {
  email: string;
  // Kommt immer leer zurück - das gespeicherte Passwort wird nie ausgeliefert.
  password: string;
  // Ob überhaupt eines hinterlegt ist. Nur dann darf das Formular beim
  // Speichern ohne Passwort das gespeicherte weiterverwenden.
  password_set: boolean;
  device_name?: string;
}

export interface JDownloaderStatus {
  connected: boolean;
  email?: string;
  device_name?: string;
  total_downloads: number;
  active_downloads: number;
  global_speed: number;
  reconnect_enabled: boolean;
  last_error?: string;
}

export interface VerifyJDownloaderRequest {
  email: string;
  password: string;
  device_name?: string;
}

export interface SaveJDownloaderRequest {
  email: string;
  // Leer lassen heisst "gespeichertes behalten" - das Backend nutzt dann das
  // Passwort aus der Config. Ist keines hinterlegt, antwortet es mit 400.
  password: string;
  device_name?: string;
}

// ============================================================================
// Notification Types
// ============================================================================

// Das Backend kennt genau diese zwei Anbieter; alles andere lehnt es mit 400 ab.
export type NotificationProvider = 'discord' | 'telegram';

export interface NotificationConfig {
  enabled: boolean;
  provider: NotificationProvider;
  settings: Record<string, string | number | boolean>;
  events: NotificationEvent[];
}

// Events ohne Aufrufstelle im Backend werden mit 400 abgelehnt, statt still
// verworfen zu werden. Deshalb stehen hier nur die vier, die wirklich etwas
// ausloesen.
export type NotificationEvent =
  | 'download_complete'
  | 'download_failed'
  | 'package_added'
  | 'captcha_required';

export interface NotificationSettings {
  global_enabled: boolean;
  configs: NotificationConfig[];
}

export interface TestNotificationRequest {
  provider: NotificationProvider;
  settings: Record<string, string | number | boolean>;
}

// ============================================================================
// Statistics Types
// ============================================================================

export interface Statistics {
  total_packages: number;
  completed_packages: number;
  failed_packages: number;
  total_downloaded: number;
  average_speed: number;
  uptime_seconds: number;
  api_calls_today: number;
  captchas_solved_today: number;
  hoster_status: HosterStatus[];
  daily_stats: DailyStat[];
}

export interface HosterStatus {
  hoster_id: string;
  hoster_name: string;
  online: boolean;
  response_time_ms: number;
  last_check: string;
}

export interface DailyStat {
  date: string;
  packages_added: number;
  packages_completed: number;
  packages_failed: number;
  bytes_downloaded: number;
  captchas_solved: number;
}

// ============================================================================
// API Response Types
// ============================================================================

export interface ApiResponse<T = unknown> {
  /** Nicht jede Route fuehrt ein `success` - die Envelope ist `data` oder `error`. */
  success?: boolean;
  data?: T;
  error?: ApiError | string;
  meta?: ApiMeta;
}

export interface ApiError {
  code?: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiMeta {
  page?: number;
  limit?: number;
  total?: number;
  has_more?: boolean;
}

/**
 * `POST /api/settings/hostnames-config` gehoert zu den wenigen Routen, die ihre
 * Statusfelder flach statt in `data` zurueckgeben.
 */
export interface HostnamesSaveResponse extends ApiResponse<HostnamesSettings> {
  message?: string;
  requires_restart?: string[];
}

/** Antwort von `GET /api/version`. */
export interface VersionInfo {
  /** Lokal aus `version.json`, damit immer vorhanden. */
  current: string;
  latest_stable?: string | null;
  latest_prerelease?: string | null;
  update_available?: string | null;
  releases_url?: string;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  meta: Required<Pick<ApiMeta, 'page' | 'limit' | 'total' | 'has_more'>>;
}

// ============================================================================
// UI Types
// ============================================================================

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export type Theme = 'dark';

// ============================================================================
// Settings Types
// ============================================================================

export interface GeneralSettings {
  internal_address: string;
  external_address: string;
  timezone: string;
  slow_mode: boolean;
  flaresolverr_url: string;
  webui_user: string;
  webui_password: string;
  _is_set: Record<string, boolean>;
}

export interface CaptchaSettings {
  service: 'dbc' | '2captcha';
  dbc_authtoken: string;
  twocaptcha_api_key: string;
  timeout: string;
  max_retries: string;
  retry_backoff: string;
  _is_set: Record<string, boolean>;
}

export interface IntegrationSettings {
  sonarr_url: string;
  sonarr_api_key: string;
  radarr_url: string;
  radarr_api_key: string;
  _is_set: Record<string, boolean>;
}

export interface HostnamesSettings {
  ad: string;
  al: string;
  at: string;
  by: string;
  dd: string;
  dl: string;
  dt: string;
  dw: string;
  fx: string;
  he: string;
  hs: string;
  mb: string;
  nk: string;
  nx: string;
  rm: string;
  sf: string;
  sl: string;
  wd: string;
  wx: string;
  sj: string;
  dj: string;
}

export interface SjdjSettings {
  sj_user: string;
  sj_preferred_hoster: string;
  dj_user: string;
  dj_preferred_hoster: string;
  sj_password: string;
  dj_password: string;
  _is_set: Record<string, boolean>;
}

export interface AdvancedSettings {
  flatten_nested_folders: boolean;
  trigger_rescan: boolean;
  xrel_enabled: boolean;
  xrel_filter_nuked: boolean;
  hidecx_api_key: string;
  _is_set: Record<string, boolean>;
}

// ============================================================================
// Window Extensions
// ============================================================================

declare global {
  interface Window {
    KUASARR_API_KEY?: string;
  }
}
