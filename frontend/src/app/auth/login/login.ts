import { Component, OnInit } from '@angular/core';
import { RouterLink, Router, ActivatedRoute } from '@angular/router';
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService, isOtpChallenge } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [RouterLink, ReactiveFormsModule, CommonModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login implements OnInit {

  // ── Step 1: email + password ──────────────────────────────────────────────
  loginForm!: FormGroup;
  isLoading   = false;
  serverError = '';
  showPassword = false;
  private returnUrl = '/dashboard';

  // ── Step 2: OTP (only shown for 2FA-enabled users) ────────────────────────
  /** When non-empty, the OTP panel is shown instead of the credentials panel. */
  otpChallengeId = '';
  otpMaskedEmail = '';
  otpEmail       = '';
  otpForm!:    FormGroup;
  otpLoading   = false;
  otpError     = '';
  resendCooldown = 0;     // seconds remaining before user can resend
  private resendTimer?: ReturnType<typeof setInterval>;

  constructor(
    private fb: FormBuilder,
    private auth: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    this.returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') || '/dashboard';
    if (this.auth.isLoggedIn()) {
      this.router.navigate([this.returnUrl]);
    }

    this.loginForm = this.fb.group({
      email:    ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(8)]],
    });

    this.otpForm = this.fb.group({
      code: ['', [Validators.required, Validators.pattern(/^\d{6}$/)]],
    });
  }

  get f()  { return this.loginForm.controls; }
  get of() { return this.otpForm.controls; }
  togglePassword(): void { this.showPassword = !this.showPassword; }

  // ── Step 1: submit email/password ─────────────────────────────────────────
  onSubmit(): void {
    if (this.loginForm.invalid || this.isLoading) return;
    this.isLoading   = true;
    this.serverError = '';

    this.auth.login(this.loginForm.value).subscribe({
      next: (res) => {
        this.isLoading = false;
        if (isOtpChallenge(res)) {
          // 2FA required — flip to the OTP panel.
          this.otpChallengeId = res.challenge_id;
          this.otpMaskedEmail = res.masked_email;
          this.otpEmail       = res.email;
          this.startResendCooldown(30);
        } else {
          // Tokens already stored — go to dashboard.
          this.router.navigate([this.returnUrl]);
        }
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading   = false;
        this.serverError = this.parseError(err);
      }
    });
  }

  // ── Step 2: submit OTP code ───────────────────────────────────────────────
  verifyOtp(): void {
    if (this.otpForm.invalid || this.otpLoading) return;
    this.otpLoading = true;
    this.otpError   = '';

    this.auth.verifyOtp(this.otpChallengeId, this.otpForm.value.code).subscribe({
      next: () => {
        this.otpLoading = false;
        this.stopResendCooldown();
        this.router.navigate([this.returnUrl]);
      },
      error: (err: HttpErrorResponse) => {
        this.otpLoading = false;
        this.otpError   = this.parseError(err);
        this.otpForm.patchValue({ code: '' });
      },
    });
  }

  resendOtp(): void {
    if (this.resendCooldown > 0 || this.otpLoading) return;
    this.otpError = '';
    this.auth.resendOtp(this.otpChallengeId).subscribe({
      next: (res) => {
        this.otpChallengeId = res.challenge_id;
        this.otpMaskedEmail = res.masked_email;
        this.startResendCooldown(30);
      },
      error: (err: HttpErrorResponse) => {
        this.otpError = this.parseError(err);
      },
    });
  }

  cancelOtp(): void {
    this.otpChallengeId = '';
    this.otpMaskedEmail = '';
    this.otpEmail       = '';
    this.otpForm.reset();
    this.stopResendCooldown();
  }

  private startResendCooldown(seconds: number): void {
    this.stopResendCooldown();
    this.resendCooldown = seconds;
    this.resendTimer = setInterval(() => {
      this.resendCooldown--;
      if (this.resendCooldown <= 0) this.stopResendCooldown();
    }, 1000);
  }

  private stopResendCooldown(): void {
    if (this.resendTimer) {
      clearInterval(this.resendTimer);
      this.resendTimer = undefined;
    }
    this.resendCooldown = 0;
  }

  private parseError(err: HttpErrorResponse): string {
    if (!err.error) return 'An unexpected error occurred. Please try again.';
    if (err.error.detail)   return err.error.detail;
    if (typeof err.error === 'string') return err.error;
    const messages: string[] = [];
    for (const key of Object.keys(err.error)) {
      const val = err.error[key];
      messages.push(Array.isArray(val) ? val.join(', ') : String(val));
    }
    return messages.join(' | ') || 'Login failed. Please check your credentials.';
  }
}
