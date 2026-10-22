# Shared operations and storage

The UI and API use the same application use cases and model checks.
One active operation owns the engine. It selects the corresponding UI workspace and locks conflicting controls.
Every connected tab follows its progress, pending gallery item, and result, including when an API client starts it.
This keeps the browser useful as a monitor for scripts and agents.

Models load on demand. Workspace switches release inactive model memory.
Batches reuse supported models and conditioning within one reservation, rather than letting competing requests load different engines.
This reduces repeated setup where measured beneficial; it does not imply all items compute in parallel.
See [Design decisions](design-decisions.md) for the workload-specific results and fallback paths.

Browser persistence and server retention serve different purposes.
**Keep in this browser** controls local drafts, references, and saved media. Its storage belongs to the address and port.
Turning it off clears that local data.

The server retains recent metadata and outputs in memory for API clients and open tabs.
Results expire after one hour, 32 operations, or 256 MiB, whichever limit comes first.
A restart clears them. API results exist before the page opens; opening a page is not required to save them in server memory.
Download outputs you need to keep beyond these limits.
