import { useState } from "react";

interface LoginPageProps {
  onRequestOtp: (phone: string) => Promise<void>;
  onVerifyOtp: (phone: string, otp: string) => Promise<void>;
}

export default function LoginPage({
  onRequestOtp,
  onVerifyOtp,
}: LoginPageProps) {
  const [step, setStep] = useState<"phone" | "otp">("phone");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);

  async function handleSendOtp(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    const cleaned = phone.replace(/\s/g, "");
    if (!/^\d{10}$/.test(cleaned)) {
      setError("Enter a valid 10-digit mobile number");
      return;
    }

    setIsSending(true);
    try {
      await onRequestOtp(`+91${cleaned}`);
      setStep("otp");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send OTP");
    } finally {
      setIsSending(false);
    }
  }

  async function handleVerifyOtp(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (otp.length !== 6) {
      setError("Enter the 6-digit OTP");
      return;
    }

    setIsSending(true);
    try {
      await onVerifyOtp(`+91${phone.replace(/\s/g, "")}`, otp);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setIsSending(false);
    }
  }

  async function handleResendOtp() {
    setError("");
    setIsSending(true);
    try {
      await onRequestOtp(`+91${phone.replace(/\s/g, "")}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resend OTP");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm">
        {/* Brand header */}
        <div className="rounded-t-xl bg-brand px-6 py-5 text-center">
          <div className="mb-1 flex items-center justify-center gap-2">
            <span className="h-5 w-1 rounded-full bg-accent" />
            <span className="text-xl font-bold tracking-tight text-white">
              Ask VJ
            </span>
          </div>
          <p className="text-sm text-white/70">Sign in to continue</p>
        </div>

        {/* Form card */}
        <div className="rounded-b-xl border border-t-0 border-gray-200 bg-white px-6 py-6 shadow-sm">
          {step === "phone" ? (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <label className="block text-sm font-medium text-gray-700">
                Mobile Number
              </label>
              <div className="flex items-center gap-2">
                <span className="flex h-10 items-center rounded-md border border-gray-300 bg-surface-alt px-3 text-sm text-gray-600">
                  +91
                </span>
                <input
                  type="tel"
                  inputMode="numeric"
                  maxLength={10}
                  value={phone}
                  onChange={(e) =>
                    setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))
                  }
                  placeholder="10-digit number"
                  className="h-10 flex-1 rounded-md border border-gray-300 px-3 text-sm outline-none transition-colors focus:border-brand focus:ring-1 focus:ring-brand"
                  autoFocus
                />
              </div>

              {error && (
                <p className="text-sm text-error">{error}</p>
              )}

              <button
                type="submit"
                disabled={isSending}
                className="flex h-10 w-full items-center justify-center rounded-md bg-accent font-medium text-brand-dark transition-colors hover:bg-accent/90 disabled:opacity-60"
              >
                {isSending ? "Sending..." : "Send OTP"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <label className="block text-sm font-medium text-gray-700">
                Enter OTP
              </label>
              <p className="text-xs text-gray-500">
                Sent to +91 {phone}
              </p>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={otp}
                onChange={(e) =>
                  setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
                }
                placeholder="6-digit OTP"
                className="h-10 w-full rounded-md border border-gray-300 px-3 text-center text-lg tracking-widest outline-none transition-colors focus:border-brand focus:ring-1 focus:ring-brand"
                autoFocus
              />

              {error && (
                <p className="text-sm text-error">{error}</p>
              )}

              <button
                type="submit"
                disabled={isSending}
                className="flex h-10 w-full items-center justify-center rounded-md bg-accent font-medium text-brand-dark transition-colors hover:bg-accent/90 disabled:opacity-60"
              >
                {isSending ? "Verifying..." : "Verify"}
              </button>

              <div className="flex items-center justify-between text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setStep("phone");
                    setOtp("");
                    setError("");
                  }}
                  className="text-gray-500 hover:text-gray-700"
                >
                  Change number
                </button>
                <button
                  type="button"
                  onClick={handleResendOtp}
                  disabled={isSending}
                  className="font-medium text-brand hover:text-brand-light disabled:opacity-60"
                >
                  Resend OTP
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
