"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, DEMO_MODE } from "@/lib/api";
import { emailOk } from "@/lib/format";
import { TextInput } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";
import { AuthAlert, AuthButton, AuthField, AuthHeading, StateIcon, splitError } from "./parts";

export function ForgotPasswordScreen() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [err, setErr] = useState("");
  const [formErr, setFormErr] = useState("");
  const [sent, setSent] = useState(false);

  const forgot = useMutation({
    mutationFn: () => api.forgotPassword(email.trim()),
    // The server answers the same way whether or not the account exists.
    onSuccess: () => setSent(true),
    onError: (e) => {
      const { fields, form } = splitError(e, ["email"]);
      setErr(fields.email ?? "");
      setFormErr(form);
    },
  });

  function submit(ev: FormEvent) {
    ev.preventDefault();
    setFormErr("");
    if (!emailOk(email.trim())) {
      setErr("Enter a valid email address.");
      return;
    }
    setErr("");
    forgot.mutate();
  }

  if (sent) {
    return (
      <AuthLayout>
        <div className="flex flex-col gap-4">
          <StateIcon icon="mail-check" tone="success" />
          <AuthHeading title="Check your email">
            {DEMO_MODE ? (
              <>
                If an account exists for <strong className="text-ink">{email.trim()}</strong>, a reset link would be sent. Demo mode: no email was sent.
              </>
            ) : (
              <>
                If an account exists for <strong className="text-ink">{email.trim()}</strong>, we sent a link to reset your password. It can only be used once.
              </>
            )}
          </AuthHeading>
          {DEMO_MODE ? (
            <AuthButton onClick={() => router.push("/reset-password?token=demo")}>Open the reset link (demo)</AuthButton>
          ) : (
            <AuthButton
              variant="secondary"
              onClick={() => {
                forgot.reset();
                setSent(false);
              }}
            >
              Use a different email
            </AuthButton>
          )}
          <p className="text-center text-[13.5px]">
            <Link href="/login">Back to sign in</Link>
          </p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <AuthHeading title="Reset your password">
          {DEMO_MODE ? "Enter your email and we'll send a reset link. In this demo, no email is sent." : "Enter your email and we'll send a reset link."}
        </AuthHeading>
        <AuthAlert>{formErr}</AuthAlert>
        <AuthField label="Email" htmlFor="forgot-email" error={err} errorId="forgot-email-err">
          <TextInput
            id="forgot-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            invalid={!!err}
            aria-describedby={err ? "forgot-email-err" : undefined}
            placeholder="you@example.com"
          />
        </AuthField>
        <AuthButton type="submit" loading={forgot.isPending}>
          Send reset link
        </AuthButton>
        <p className="text-center text-[13.5px]">
          <Link href="/login">Back to sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
