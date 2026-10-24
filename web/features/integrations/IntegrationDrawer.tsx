"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError, type Integration } from "@/lib/api";
import { INTEGRATION_STATUS } from "@/lib/labels";
import { useUi } from "@/lib/session";
import { Badge, Button, Drawer, Icon } from "@/components/ui";

const CONNECT_BODY =
  "Connections use a secure sign-in flow handled by the server, with least-privilege scopes and encrypted credential storage. This app never asks for passwords or API keys. Real connections arrive in Phase 3.";

type Action = "connect" | "disconnect" | "restore";

export function IntegrationDrawer({ integration: i, onClose }: { integration: Integration; onClose: () => void }) {
  const { toast, notice } = useUi();
  const qc = useQueryClient();
  const status = INTEGRATION_STATUS[i.status];
  const canRemove = i.status === "demo" || i.status === "connected";
  const canRestore = DEMO_MODE && i.key === "wordpress" && i.status !== "demo";

  const m = useMutation({
    mutationFn: (action: Action) => (action === "disconnect" ? api.disconnectIntegration(i.key) : api.connectIntegration(i.key)),
    onSuccess: (_res, action) => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["activity"] });
      if (action === "restore") toast("Demo sandbox restored.", "success");
      else if (action === "connect") toast(`${i.name} connected.`, "success");
      else toast(i.status === "demo" ? `${i.name} demo connection removed.` : `${i.name} disconnected.`, "info");
    },
    onError: (e, action) => {
      if (action !== "disconnect" && isApiError(e) && e.code === "integration_not_available") notice("Connecting needs the backend", CONNECT_BODY);
      else toast(errorMessage(e), "danger");
    },
  });
  const busy = (a: Action) => m.isPending && m.variables === a;

  return (
    <Drawer
      label="Manage integration"
      onClose={onClose}
      header={
        <>
          <Icon name={i.icon} size={18} className="text-ink-3" />
          <h2 className="m-0 min-w-0 flex-1 text-[15px] font-semibold">{i.name}</h2>
          <Badge meta={status} />
        </>
      }
      footer={
        <div className="flex w-full flex-wrap justify-end gap-2">
          {canRemove && (
            <Button variant="danger" size="sm" className="h-9!" loading={busy("disconnect")} disabled={m.isPending} onClick={() => m.mutate("disconnect")}>
              {i.status === "demo" ? "Remove demo connection" : "Disconnect"}
            </Button>
          )}
          {canRestore && (
            <Button size="sm" className="h-9!" loading={busy("restore")} disabled={m.isPending} onClick={() => m.mutate("restore")}>
              Restore demo sandbox
            </Button>
          )}
          {i.status !== "connected" && (
            <Button variant="primary" size="sm" icon="server" className="h-9!" loading={busy("connect")} disabled={m.isPending} onClick={() => m.mutate("connect")}>
              Connect — backend required
            </Button>
          )}
        </div>
      }
    >
      <p className="m-0 text-ink-2">{i.description}</p>
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
        <span>Data destination: {i.destination}. Being connected doesn&apos;t allow sharing every file — each transfer is checked separately.</span>
      </div>
      <div className="text-[13px] text-muted">Last check: {i.last_activity}</div>
    </Drawer>
  );
}
