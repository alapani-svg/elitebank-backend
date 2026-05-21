import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { NotificationService } from './notification.service';

// ── Interfaces ────────────────────────────────────────────────────────────────

export interface RegisterPayload {
  full_name: string;
  email: string;
  phone_number: string;
  password: string;
  password_confirm: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface UserProfile {
  id: string;
  full_name: string;
  email: string;
  phone_number: string;
  balance_xaf: number;
  is_verified: boolean;
  date_joined: string;
}

export interface AuthResponse {
  message: string;
  user: UserProfile;
  tokens: AuthTokens;
}

/** Server response when a 2FA-enabled user logs in. The frontend then has to
 *  POST `{ challenge_id, code }` to `/api/auth/2fa/verify/` to get tokens.
 *  Delivery channel is EMAIL — `masked_email` is e.g. `co***05@gmail.com`. */
export interface OtpChallengeResponse {
  requires_otp: true;
  challenge_id: string;
  masked_email: string;
  email: string;
  message: string;
}

export type LoginResult = AuthResponse | OtpChallengeResponse;

export function isOtpChallenge(r: LoginResult): r is OtpChallengeResponse {
  return (r as OtpChallengeResponse).requires_otp === true;
}

// ── Token Keys ────────────────────────────────────────────────────────────────

const ACCESS_KEY  = 'elite_access';
const REFRESH_KEY = 'elite_refresh';

// ── Service ───────────────────────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class AuthService {

  private api = environment.apiUrl;

  constructor(
    private http:          HttpClient,
    private router:        Router,
    private notifications: NotificationService,
  ) {}

  // Registration — POST /api/auth/register/
  register(payload: RegisterPayload): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.api}/api/auth/register/`, payload)
      .pipe(tap(res => this.storeTokens(res.tokens)));
  }

  // Login — POST /api/auth/login/
  // May return either AuthResponse (immediate JWT) or OtpChallengeResponse
  // (2FA enabled — caller must follow with verifyOtp()).
  login(payload: LoginPayload): Observable<LoginResult> {
    return this.http.post<LoginResult>(`${this.api}/api/auth/login/`, payload)
      .pipe(tap(res => {
        if (!isOtpChallenge(res)) this.storeTokens(res.tokens);
      }));
  }

  // Step 2 of 2FA login — POST /api/auth/2fa/verify/
  verifyOtp(challenge_id: string, code: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.api}/api/auth/2fa/verify/`,
        { challenge_id, code })
      .pipe(tap(res => this.storeTokens(res.tokens)));
  }

  // Re-send a fresh OTP — POST /api/auth/2fa/resend/
  resendOtp(challenge_id: string): Observable<{ challenge_id: string; masked_email: string; message: string }> {
    return this.http.post<{ challenge_id: string; masked_email: string; message: string }>(
      `${this.api}/api/auth/2fa/resend/`, { challenge_id });
  }

  // Refresh — POST /api/auth/token/refresh/
  refreshAccessToken(): Observable<{ access: string }> {
    const refresh = this.getRefreshToken();
    return this.http.post<{ access: string }>(`${this.api}/api/auth/token/refresh/`, { refresh })
      .pipe(tap(res => localStorage.setItem(ACCESS_KEY, res.access)));
  }

  // ── Password reset ────────────────────────────────────────────────────────

  /** Step 1: ask the server to email a reset link. Always succeeds (won't
   *  reveal whether the email exists). */
  requestPasswordReset(email: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(
      `${this.api}/api/auth/password-reset/request/`,
      { email },
    );
  }

  /** Step 2: submit the signed token + the new password. */
  confirmPasswordReset(
    token: string, new_password: string, confirm_password: string,
  ): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(
      `${this.api}/api/auth/password-reset/confirm/`,
      { token, new_password, confirm_password },
    );
  }

  // ── Token helpers ─────────────────────────────────────────────────────────

  storeTokens(tokens: AuthTokens): void {
    localStorage.setItem(ACCESS_KEY,  tokens.access);
    localStorage.setItem(REFRESH_KEY, tokens.refresh);
  }

  getAccessToken():  string | null { return localStorage.getItem(ACCESS_KEY);  }
  getRefreshToken(): string | null { return localStorage.getItem(REFRESH_KEY); }
  isLoggedIn():      boolean       { return !!this.getAccessToken(); }

  getCurrentUserId(): string | null {
    const token = this.getAccessToken();
    if (!token) return null;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.user_id ?? null;
    } catch {
      return null;
    }
  }

  logout(): void {
    const refresh = this.getRefreshToken();

    // Best-effort: blacklist the refresh token on the server. We don't wait —
    // local cleanup and redirect happen immediately so the UI is responsive.
    if (refresh) {
      this.http.post(`${this.api}/api/auth/logout/`, { refresh }).subscribe({
        next: () => {},
        error: () => {},  // swallow — local logout still proceeds
      });
    }

    // Stop the notification poll and clear the shared list/count.
    this.notifications.stopPolling();

    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    this.router.navigate(['/login']);
  }
}
