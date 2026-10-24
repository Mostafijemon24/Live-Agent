"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type MouseEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE } from "@/lib/api";
import { emailOk, passwordOk } from "@/lib/format";
import { useSession, useUi } from "@/lib/session";
import { FieldError, TextInput } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";
import { AuthAlert, AuthButton, AuthField, AuthHeading, OrDivider, PLACEHOLDER_LINK, PasswordInput, SsoButton, splitError } from "./parts";

export function RegisterScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { refresh } = useSession();
  const { toast } = useUi();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [terms, setTerms] = useState(false);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [formErr, setFormErr] = useState("");

  const register = useMutation({
    mutationFn: () => api.register({ name: name.trim(), email: email.trim(), password, accept_terms: terms }),
    onSuccess: async () => {
      setPassword("");
      // Real mode: registering never signs in (same response whether or not the
      // email exists). The demo mock may sign in, so pick up its session there.
      if (DEMO_MODE) {
        qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
        await refresh();
      }
      router.push(`/verify-email?email=${encodeURIComponent(email.trim())}`);
    },
    onError: (e) => {
      const { fields, form } = splitError(e, ["name", "email", "password", "accept_terms"]);
      setErrs(fields);
      setFormErr(form);
    },
  });

  const placeholder = (ev: MouseEvent) => {
    ev.preventDefault();
    toast(PLACEHOLDER_LINK, "info");
  };

  function submit(ev: FormEvent) {
    ev.preventDefault();
    const er: Record<string, string> = {};
    if (!name.trim()) er.name = "Enter your name.";
    if (!emailOk(email.trim())) er.email = "Enter a valid email address, like name@example.com.";
    if (!passwordOk(password)) er.password = "Use at least 10 characters, including a number.";
    if (!terms) er.accept_terms = "Please accept the terms to continue.";
    setErrs(er);
    setFormErr("");
    if (Object.keys(er).length) return;
    register.mutate();
  }

  return (
    <AuthLayout>
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <AuthHeading title="Create your workspace">
          {DEMO_MODE ? "Demo sign-up. Nothing you type is stored or sent." : "Your workspace is private to you. We'll email you a link to verify your address before you sign in."}
        </AuthHeading>
        <AuthAlert>{formErr}</AuthAlert>
        <AuthField label="Full name" htmlFor="reg-name" error={errs.name} errorId="reg-name-err">
          <TextInput
            id="reg-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            invalid={!!errs.name}
            aria-describedby={errs.name ? "reg-name-err" : undefined}
            placeholder="e.g. Alex Morgan"
          />
        </AuthField>
        <AuthField label="Work email" htmlFor="reg-email" error={errs.email} errorId="reg-email-err">
          <TextInput
            id="reg-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            invalid={!!errs.email}
            aria-describedby={errs.email ? "reg-email-err" : undefined}
            placeholder="you@example.com"
          />
        </AuthField>
        <AuthField
          label="Password"
          htmlFor="reg-pw"
          hint={<span id="reg-pw-hint">At least 10 characters, including a number.</span>}
          error={errs.password}
          errorId="reg-pw-err"
        >
          <PasswordInput
            id="reg-pw"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            invalid={!!errs.password}
            aria-describedby={errs.password ? "reg-pw-hint reg-pw-err" : "reg-pw-hint"}
          />
        </AuthField>
        <label className="flex cursor-pointer items-start gap-2.5 text-[13.5px] text-ink-3">
          <input
            type="checkbox"
            checked={terms}
            onChange={(e) => setTerms(e.target.checked)}
            aria-invalid={!!errs.accept_terms || undefined}
            className="mt-[3px] h-4 w-4 accent-primary"
          />
          <span>
            I agree to the{" "}
            <a href="#" onClick={placeholder}>
              Terms
            </a>{" "}
            and{" "}
            <a href="#" onClick={placeholder}>
              Privacy policy
            </a>{" "}
            (placeholders).
          </span>
        </label>
        {errs.accept_terms && (
          <div className="-mt-3.5">
            <FieldError>{errs.accept_terms}</FieldError>
          </div>
        )}
        <AuthButton type="submit" loading={register.isPending}>
          {register.isPending ? "Creating workspace…" : "Create workspace"}
        </AuthButton>
        <OrDivider />
        <SsoButton />
        <p className="text-center text-[13.5px] text-muted">
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
