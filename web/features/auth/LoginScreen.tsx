"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError, type Me } from "@/lib/api";
import { emailOk } from "@/lib/format";
import { useSession, useUi } from "@/lib/session";
import { TextInput } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";
import { AuthAlert, AuthButton, AuthField, AuthHeading, PasswordInput, SsoButton, safeNext, splitError } from "./parts";

export function LoginScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const { setMe } = useSession();
  const { toast } = useUi();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [formErr, setFormErr] = useState("");
  const [offerResend, setOfferResend] = useState(false);

  const login = useMutation({
    mutationFn: () => api.login({ email: email.trim(), password }),
    onSuccess: (me: Me) => {
      // Drop anything cached for a previous account before storing the new session.
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      setMe(me);
      setPassword("");
      if (DEMO_MODE) toast("Signed in to the demo workspace. This is not real authentication.", "info");
      const next = safeNext(params.get("next"));
      router.push(next ?? (me.user.onboarding_completed ? "/overview" : "/onboarding"));
    },
    onError: (e) => {
      const { fields, form } = splitError(e, ["email", "password"]);
      setErrs(fields);
      setFormErr(form);
      // The server uses one generic 401 for wrong password, unknown and unverified email.
      setOfferResend(isApiError(e) && e.status === 401);
    },
  });

  const resend = useMutation({
    mutationFn: () => api.resendVerification(email.trim()),
    onSuccess: (r) => toast(r.message || "If that account needs verifying, we sent a new link.", "success"),
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  function submit(ev: FormEvent) {
    ev.preventDefault();
    const er: Record<string, string> = {};
    if (!emailOk(email.trim())) er.email = "Enter a valid email address.";
    if (!password) er.password = "Enter your password.";
    setErrs(er);
    setFormErr("");
    setOfferResend(false);
    if (Object.keys(er).length) return;
    login.mutate();
  }

  return (
    <AuthLayout>
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <AuthHeading title="Sign in">
          {DEMO_MODE ? (
            <>
              Demo sign-in: any email and password works. Use the password <span className="font-mono text-ink">error</span> to preview a failed sign-in.
            </>
          ) : (
            "Welcome back. Sign in to your workspace."
          )}
        </AuthHeading>
        <AuthAlert>{formErr}</AuthAlert>
        {formErr && offerResend && (
          <p className="-mt-2 text-[13px] text-muted">
            Haven&apos;t verified your email yet?{" "}
            <button
              type="button"
              onClick={() => resend.mutate()}
              disabled={resend.isPending || !emailOk(email.trim())}
              className="border-0 bg-transparent p-0 text-[13px] text-primary hover:underline disabled:opacity-60"
            >
              {resend.isPending ? "Sending…" : "Resend the verification link."}
            </button>
          </p>
        )}
        <AuthField label="Email" htmlFor="login-email" error={errs.email} errorId="login-email-err">
          <TextInput
            id="login-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            invalid={!!errs.email}
            aria-describedby={errs.email ? "login-email-err" : undefined}
            placeholder="you@example.com"
          />
        </AuthField>
        <AuthField
          label="Password"
          htmlFor="login-pw"
          labelExtra={
            <Link href="/forgot-password" className="font-normal">
              Forgot password?
            </Link>
          }
          error={errs.password}
          errorId="login-pw-err"
        >
          <PasswordInput
            id="login-pw"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            invalid={!!errs.password}
            aria-describedby={errs.password ? "login-pw-err" : undefined}
          />
        </AuthField>
        <AuthButton type="submit" loading={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </AuthButton>
        <SsoButton />
        <p className="text-center text-[13.5px] text-muted">
          New here? <Link href="/register">{DEMO_MODE ? "Create a demo account" : "Create an account"}</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
