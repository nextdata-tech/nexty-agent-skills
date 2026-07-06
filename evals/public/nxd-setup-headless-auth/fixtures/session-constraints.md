# Session environment

This session runs inside a sandboxed Linux VM operated by an agent harness.

- Every shell command runs in its own bubblewrap sandbox
  (`bwrap --die-with-parent --unshare-pid`). Each call is an independent
  process tree: when the call returns, every process it started is killed.
  Nothing survives between calls except files on disk.
- Maximum wall-clock time per shell call: 45 seconds.
- No browser is installed inside the VM; `xdg-open` has no handler.
- Outbound network goes through an allowlisting HTTP(S) proxy; the mesh hosts
  used this session are allowlisted and reachable with `curl`.
- The human user interacting with this session has a normal browser on their
  own machine and can open links you send them.
