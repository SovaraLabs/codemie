# Sovara integration

Install `sovara-langchain` and select `OBSERVABILITY_PROVIDER=sovara`. Configure
`SOVARA_SERVER_URL` with the common origin serving both the app and exec APIs and
`SOVARA_API_KEY` with an organization key. Recording needs `traces:write`; lessons
need `lessons:retrieve`. First-use provisioning needs `projects:create`, and
technical project renames need `projects:rename`. Deploy the companion Sovara
project lifecycle API before enabling this integration version.

On the first recording for a project in each worker, the adapter resolves the
CodeMie project name and explicitly creates it if absent. The recording SDK does
not create projects. A provisioning failure leaves the CodeMie execution running
without Sovara recording, with a metadata-only warning. The next attempt retries.

Technical name changes in the project service resolve the old Sovara name once,
then rename that ID before committing the CodeMie change. Repeated HTTP attempts
use that same ID and an expected-name precondition. Renaming the display label
alone does not rename the Sovara project. A missing Sovara project needs no rename;
it is provisioned under the new name on first recording.

A rejected remote rename aborts the local transaction. A failed local transaction
attempts to restore the remote name; failure reports an explicit reconciliation
error. These commits are not atomic: a process crash or ambiguous database commit
can still require an operator to reconcile the names. Keep recording stopped for
that project until reconciliation is complete. There is no persisted ID mapping,
new database field, or background synchronization service.

Deleting a CodeMie project does not delete its Sovara history. Names remain the
integration identity: recreating a CodeMie project with a retained Sovara name
reuses that history. Explicitly rename or delete the old Sovara project before
reusing a name when a separate history is required. Sovara deletion requires the
separate `projects:delete` permission, which is disabled by default.
