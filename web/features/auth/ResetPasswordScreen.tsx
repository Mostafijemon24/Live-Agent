"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, isApiError } from "@/lib/api";
import { passwordOk } from "@/lib/format";
import { TextInput } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";
import { AuthAlert, AuthButton, AuthField, AuthHeading, StateIcon, splitError } from "./parts";

export function ResetPasswordScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  // Read once; the token is a credential, so it is never stored anywhere else.
  const token = useSearchParams().get("token") ?? "";
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [show, setShow] = useState(false);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [formErr, setFormErr] = useState("");
  const [linkBad, setLinkBad] = useState(false);
  const [done, setDone] = useState(false);

  const reset = useMutation({
    mutationFn: () => api.resetPassword(token, pw),
    onSuccess: () => {
      setPw("");
      setPw2("");
      setDone(true);
      // Every session was revoked server-side, including this browser's.
      if (!DEMO_MODE) {
        qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
        void qc.invalidateQueries({ queryKey: ["me"] });
      }
    },
    onError: (e) => {
      const { fields, form } = splitError(e, ["password"]);
      setErrs(fields);
      setFormErr(form);
      setLinkBad(isApiError(e) && !fields.password && e.status !== 429 && e.status < 500);
    },
  });

  function submit(ev: FormEvent) {
    ev.preventDefault();
    const er: Record<string, string> = {};
    if (!passwordOk(pw)) er.password = "Use at least 10 characters, including a number.";
    if (pw !== pw2) er.pw2 = "Passwords do not match.";
    setErrs(er);
    setFormErr("");
    setLinkBad(false);
    if (Object.keys(er).length) return;
    reset.mutate();
  }

  if (!token) {
    return (
      <AuthLayout>
        <div className="flex flex-col gap-4">
          <StateIcon icon="circle-x" tone="danger" />
          <AuthHeading title="This reset link is incomplete">
            Open the link from your email again, or request a new one. Reset links can only be used once.
          </AuthHeading>
          <AuthButton onClick={() => router.push("/forgot-password")}>Request a new link</AuthButton>
          <p className="text-center text-[13.5px]">
            <Link href="/login">Back to sign in</Link>
          </p>
        </div>
      </AuthLayout>
    );
  }

  if (done) {
    return (
      <AuthLayout>
        <div className="flex flex-col gap-4">
          <StateIcon icon="circle-check" tone="success" />
          <AuthHeading title="Password updated">
            {DEMO_MODE
              ? "In production, other sessions would be signed out. Demo: nothing was changed."
              : "For your security, every session was signed out — including this one. Sign in again with your new password."}
          </AuthHeading>
          <AuthButton onClick={() => router.push("/login")}>Continue to sign in</AuthButton>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <AuthHeading title="Choose a new password">
          {DEMO_MODE ? "The reset link would expire after a short time. Demo only." : "Reset links expire after a short time and can only be used once."}
        </AuthHeading>
        <AuthAlert>
          {formErr && (
            <>
              {formErr}
              {linkBad && (
                <>
                  {" "}
                  <Link href="/forgot-password" className="font-medium">
                    Request a new link
                  </Link>
                </>
              )}
            </>
          )}
        </AuthAlert>
        <AuthField label="New password" htmlFor="reset-pw" error={errs.password} errorId="reset-pw-err">
          <TextInput
            id="reset-pw"
            type={show ? "text" : "password"}
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            autoComplete="new-password"
            invalid={!!errs.password}
            aria-describedby={errs.password ? "reset-pw-err" : undefined}
          />
        </AuthField>
        <AuthField label="Confirm new password" htmlFor="reset-pw2" error={errs.pw2} errorId="reset-pw2-err">
          <TextInput
            id="reset-pw2"
            type={show ? "text" : "password"}
            value={pw2}
            onChange={(e) => setPw2(e.target.value)}
            autoComplete="new-password"
            invalid={!!errs.pw2}
            aria-describedby={errs.pw2 ? "reset-pw2-err" : undefined}
          />
        </AuthField>
        <label className="flex cursor-pointer items-center gap-2 text-[13.5px] text-ink-3">
          <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} className="accent-primary" />
          Show passwords
        </label>
        <AuthButton type="submit" loading={reset.isPending}>
          Update password
        </AuthButton>
      </form>
    </AuthLayout>
  );
}
