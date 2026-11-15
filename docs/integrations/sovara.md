# Sovara integration

Record CodeMie conversations and workflows in Sovara, inspect model and tool calls,
and add relevant lessons to model requests.

## Prerequisites

- A Sovara server with organization API keys and project lifecycle support.
- An organization API key with recording, lesson retrieval, project creation,
  rename and deletion enabled.
- The `sovara-langchain` package installed in the Python environment used by
  CodeMie and its workflow workers:

  ```bash
  python -m pip install sovara-langchain
  ```

See the [Sovara LangChain/LangGraph guide](https://docs.sovara-labs.com/integrations/langchain)
for package requirements.

## Configure CodeMie

Set these environment variables in your CodeMie deployment:

```bash
OBSERVABILITY_PROVIDER=sovara
SOVARA_SERVER_URL=https://sovara.company.com
SOVARA_API_KEY=<organization-api-key>
```

Use your organization's Sovara URL and supply the API key through your deployment's
secret configuration. Restart or redeploy CodeMie and its workflow workers to
apply the settings. CodeMie uses one observability provider at a time.

## Verify the integration

Run a CodeMie conversation that uses a tool, then open Sovara and select the
matching project. Check that the conversation contains the model calls and tool
results. Run a workflow to verify its recording too.

The integration records model calls and tools executed through LangChain,
including agent-invoked MCP tools. Direct workflow tool nodes are not recorded.
Relevant project lessons are added to model input while CodeMie's conversation
history stays unchanged. See [Sovara traces](https://docs.sovara-labs.com/observability/traces)
and [lessons](https://docs.sovara-labs.com/sovaradb/lessons).

## Project lifecycle

CodeMie uses the same project name in Sovara and creates the project on its first
recording. Renaming a CodeMie project also renames its Sovara project, preserving
traces and lessons. Changing only the display name has no effect in Sovara.

Deleting a CodeMie project also permanently deletes its Sovara project, traces
and lessons.
