"use client";

import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError, type Integration } from "@/lib/api";
import { useUi } from "@/lib/session";
import { Badge, Button, Drawer, FieldError, Icon, Label, TextInput } from "@/components/ui";
import { integrationBadge, isChecking } from "./status";

const HTTPS_SITE = /^https:\/\/[a-z0-9.-]+\.[a-z]{2,63}(\/[^\s?#]*)?$/i;

export function IntegrationDrawer({ integration: i, onClose }: { integration: Integration; onClose: () => void }) {
  const { toast } = useUi();
  const qc = useQueryClient();
  const [site, setSite] = useState(i.site_url ?? "");
  const [siteErr, setSiteErr] = useState("");
  const isWp = i.key === "wordpress";
  const isProvider = i.key === "ai_provider";
  const notBuilt = !i.operational && !isProvider;
  const canRemove = !isProvider && (i.status === "demo" || i.status === "connected" || i.status === "error" || !!i.site_url);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["integrations"] });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
    void qc.invalidateQueries({ queryKey: ["activity"] });
  };

  const connect = useMutation({
    mutationFn: (url: string) => api.connectWordPress(url),
    onSuccess: () => {
      refresh();
      toast(DEMO_MODE ? "Demo connection saved (nothing was contacted)." : "Checking the site… It shows as connected once the check succeeds.", "info");
    },
    onError: (e) => {
      if (isApiError(e) && (e.fieldErrors().site_url || e.code === "domain_not_allowed")) setSiteErr(e.fieldErrors().site_url ?? e.message);
      else toast(errorMessage(e), "danger");
    },
  });
  const disconnect = useMutation({
    mutationFn: () => api.disconnectIntegration(i.key),
    onSuccess: () => {
      refresh();
      toast(`${i.name} disconnected.`, "info");
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const v = site.trim();
    if (!HTTPS_SITE.test(v)) {
      setSiteErr("Enter the site's https:// address, like https://example.com");
      return;
    }
    setSiteErr("");
    connect.mutate(v);
  };

  return (
    <Drawer
      label="Manage integration"
      onClose={onClose}
      header={
        <>
          <Icon name={i.icon} size={18} className="text-ink-3" />
          <h2 className="m-0 min-w-0 flex-1 text-[15px] font-semibold">{i.name}</h2>
          <Badge meta={integrationBadge(i)} />
        </>
      }
      footer={
        canRemove ? (
          <div className="flex w-full flex-wrap justify-end gap-2">
            <Button variant="danger" size="sm" className="h-9!" loading={disconnect.isPending} onClick={() => disconnect.mutate()}>
              Disconnect
            </Button>
          </div>
        ) : undefined
      }
    >
      <p className="m-0 text-ink-2 [text-wrap:pretty]">{i.description}</p>
      {i.mode && (
        <div className="text-[13px] text-muted">
          How it works: <span className="text-ink-2">{i.mode}</span>
        </div>
      )}

      {notBuilt && (
        <div role="note" className="flex gap-2 rounded-lg border border-line bg-subtle px-3.5 py-3 text-[13px] text-ink-3">
          <Icon name="info" size={14} className="mt-0.5 text-primary" />
          <span>Not built yet. This integration can&apos;t be connected, and the Agent can&apos;t use it.</span>
        </div>
      )}

      {isProvider && (
        <div role="note" className="flex gap-2 rounded-lg border border-line bg-subtle px-3.5 py-3 text-[13px] text-ink-3">
          <Icon name="key-round" size={14} className="mt-0.5 text-primary" />
          <span>The AI model is configured by your server administrator. API keys are never entered in the browser, and they are never shown to the model or written to logs.</span>
        </div>
      )}

      {isWp && (
        <form onSubmit={submit} noValidate className="flex flex-col gap-2 rounded-lg border border-line px-3.5 py-3">
          {isChecking(i) && (
            <div role="status" className="flex items-center gap-2 text-[13px] text-info">
              <Icon name="loader" size={14} spin />
              Checking the site…
            </div>
          )}
          {i.status === "error" && i.error_message && (
            <div role="alert" className="flex items-start gap-2 text-[13px] text-danger">
              <Icon name="triangle-alert" size={14} className="mt-0.5" />
              {i.error_message}
            </div>
          )}
          {i.status === "connected" && i.site_url && (
            <div className="flex items-center gap-2 text-[13px] text-success">
              <Icon name="circle-check" size={14} />
              Reading <span className="font-mono">{i.site_url}</span> (read-only)
            </div>
          )}
          <Label htmlFor="wp-site" hint="Read-only, through the site's public REST API. No username, password or key is requested.">
            Site address
          </Label>
          <TextInput
            id="wp-site"
            type="url"
            inputMode="url"
            placeholder="https://example.com"
            value={site}
            onChange={(e) => setSite(e.target.value)}
            invalid={!!siteErr}
            aria-describedby={siteErr ? "wp-site-err" : undefined}
            autoComplete="url"
          />
          <FieldError id="wp-site-err">{siteErr}</FieldError>
          <p className="m-0 text-[12.5px] text-muted [text-wrap:pretty]">
            The site&apos;s domain must be on Settings → Allowed domains first. The Agent only contacts domains on that list, and the site is checked before it shows as connected.
          </p>
          <div>
            <Button type="submit" variant="primary" size="sm" className="h-9!" loading={connect.isPending}>
              {i.site_url ? "Save and re-check" : "Connect (read-only)"}
            </Button>
          </div>
        </form>
      )}

      <div>
        <div className="mb-2 text-[13px] font-medium">Permissions (plain language)</div>
        {i.scopes.length > 0 ? (
          <ul className="m-0 list-none rounded-lg border border-line p-0">
            {i.scopes.map((x) => (
              <li key={x} className="flex gap-2 border-b border-line-soft px-3 py-[9px] text-[13.5px] last:border-b-0">
                <Icon name="check" size={14} className="mt-[3px] text-success" />
                {x}
              </li>
            ))}
          </ul>
        ) : (
          <div className="rounded-lg border border-line px-3 py-[9px] text-[13.5px] text-muted">No permissions requested.</div>
        )}
      </div>
      <div className="flex gap-2 rounded-lg bg-primary-soft px-3.5 py-3 text-[13px] text-[#1F2A7A]">
        <Icon name="send" size={14} className="mt-0.5" />
        <span>Data destination: {i.destination}. Being connected doesn&apos;t allow sharing every file — each step is checked by the policy engine.</span>
      </div>
      <div className="text-[13px] text-muted">Last check: {i.last_activity}</div>
    </Drawer>
  );
}
