"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage } from "@/lib/api";
import { emailOk } from "@/lib/format";
import { useSession, useUi } from "@/lib/session";
import { TextInput } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";
import { AuthAlert, AuthButton, AuthField, AuthHeading, StateIcon } from "./parts";

/**
 * /verify-email
 *  - without ?token: "check your inbox" (address from ?email=), with a resend button.
 *  - with ?token: verifies once and shows success or failure (failure offers a resend).
 * Registration never signs in, so this page works without a session.
 */
export function VerifyEmailScreen() {
  const params = useSearchParams();
  const token = params.get("token");
  const email = params.get("email") ?? "";
  return <AuthLayout>{token ? <VerifyToken token={token} initialEmail={email} /> : <CheckInbox email={email} />}</AuthLayout>;
}

function CheckInbox({ email }: { email: string }) {
  const router = useRouter();
  const { me } = useSession();
  const { toast } = useUi();
  const shown = email && emailOk(email) ? email : "";

  return (
    <div className="flex flex-col gap-4">
      <StateIcon icon="mail" tone="primary" />
      <AuthHeading title="Verify your email">
        {DEMO_MODE ? (
          <>
            We&apos;d send a verification link to <strong className="text-ink">{shown || "your email address"}</strong>. Demo mode: no email is sent and no account exists.
          </>
        ) : (
          <>
            We sent an email to <strong className="text-ink">{shown || "your email address"}</strong>. Open the link inside to confirm your address, then sign in.
            Can&apos;t find it? Check your spam folder or resend it.
          </>
        )}
      </AuthHeading>
      {DEMO_MODE ? (
        <>
          <AuthButton onClick={() => router.push(me ? "/onboarding" : "/login")}>Simulate verified email</AuthButton>
          <AuthButton variant="secondary" onClick={() => toast("Demo: no email was sent.", "info")}>
            Resend link
          </AuthButton>
        </>
      ) : (
        <>
          <AuthButton onClick={() => router.push("/login")}>Continue to sign in</AuthButton>
          <ResendForm initialEmail={shown} />
        </>
      )}
    </div>
  );
}

function VerifyToken({ token, initialEmail }: { token: string; initialEmail: string }) {
  const router = useRouter();
  const { me } = useSession();
  const started = useRef(false);
  const verify = useMutation({ mutationFn: (t: string) => api.verifyEmail(t) });
  const { mutate } = verify;

  useEffect(() => {
    // Tokens are single-use: never send the same one twice (React strict mode runs effects twice).
    if (started.current) return;
    started.current = true;
    mutate(token);
  }, [mutate, token]);

  if (verify.isError) {
    return (
      <div className="flex flex-col gap-4">
        <StateIcon icon="circle-x" tone="danger" />
        <AuthHeading title="This link didn't work">Verification links expire after a while and can only be used once. Send yourself a new one below.</AuthHeading>
        <AuthAlert>{errorMessage(verify.error)}</AuthAlert>
        <ResendForm initialEmail={initialEmail} primary />
        <p className="text-center text-[13.5px]">
          <Link href="/login">Back to sign in</Link>
        </p>
      </div>
    );
  }

  if (verify.isSuccess) {
    return (
      <div className="flex flex-col gap-4">
        <StateIcon icon="circle-check" tone="success" />
        <AuthHeading title="Email verified">{verify.data.message || "Your email address is confirmed. You can sign in now."}</AuthHeading>
        <AuthButton onClick={() => router.push(DEMO_MODE && me ? "/onboarding" : "/login")}>{DEMO_MODE && me ? "Continue to setup" : "Sign in"}</AuthButton>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <StateIcon icon="mail-check" tone="primary" />
      <AuthHeading title="Verifying your email…">This only takes a moment.</AuthHeading>
      <AuthButton loading disabled>
        Verifying…
      </AuthButton>
    </div>
  );
}

/** Resend the verification link. Uses the known address, or asks for one. Response is generic. */
function ResendForm({ initialEmail, primary }: { initialEmail: string; primary?: boolean }) {
  const { toast } = useUi();
  const known = initialEmail && emailOk(initialEmail) ? initialEmail : "";
  const [value, setValue] = useState(known);
  const [err, setErr] = useState("");
  const resend = useMutation({
    mutationFn: (addr: string) => api.resendVerification(addr),
    onSuccess: (r) => toast(r.message || "If that address needs verifying, we sent a new link.", "success"),
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  function send() {
    const addr = value.trim();
    if (!emailOk(addr)) {
      setErr("Enter a valid email address.");
      return;
    }
    setErr("");
    resend.mutate(addr);
  }

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
      className="flex flex-col gap-4"
    >
      {!known && (
        <AuthField label="Email" htmlFor="resend-email" error={err} errorId="resend-email-err">
          <TextInput
            id="resend-email"
            type="email"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoComplete="email"
            invalid={!!err}
            aria-describedby={err ? "resend-email-err" : undefined}
            placeholder="you@example.com"
          />
        </AuthField>
      )}
      <AuthButton type="submit" variant={primary ? "primary" : "secondary"} loading={resend.isPending}>
        {resend.isPending ? "Sending…" : "Resend link"}
      </AuthButton>
    </form>
  );
}
