# Degraded-delivery ledger

The ledger is a small JSON file used only when the delivery attempt store misbehaves (flag `BRIEF_DELIVERY_RECORD_V1` paths). It exists to stop a brief
being sent twice, and to remember what was sent while the store could not.

* **Location.** `BRIEF_DEGRADED_LEDGER` (a file path) if set; otherwise `$XDG_STATE_HOME/tjrhq/brief-degraded-ledger.json`, falling back to
  `~/.local/state/tjrhq/brief-degraded-ledger.json`. The default is per-user and persistent (not tmpfs, not a shared or world-writable directory), so it survives
  a restart or reboot of the service.
* **Permissions.** Directory 0700, file 0600, created by the running user. A file owned by another user is not trusted (memory only, an alert says so); loose
  modes on a file the user owns are tightened on read.
* **Blocks and records, never sends.** The ledger holds no message text, no chat id and no token, and nothing in it can cause a message to be sent. It is read
  before every send path (a send for a brief and text it already holds is refused unless an earlier attempt was definitely not delivered) and written after a send.
  `import_ledger` copies its entries into the attempt store when the store is back; `recover_pending` and the recovery job import first and leave alone any brief whose
  ledger state is not yet in the store.
* **Interruption.** An entry is written before the first chunk is sent. A process that dies mid-send leaves a `started` entry; once it is older than five minutes it is
  imported as an attempt whose in-flight chunk is UNKNOWN, so the normal policy (one marked, authorised recovery resend) applies.
* **What it does not do.** It is not a scheduler and does not retry; the recovery job (report-only by default) and an authorised resend remain the only ways a
  second send can happen.
