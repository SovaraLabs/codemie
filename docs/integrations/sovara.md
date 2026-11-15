# Sovara integration

Sovara enriches agents with domain knowledge through lessons: reusable company
policies, conventions and expertise retrieved when relevant to a task. The
CodeMie integration adds these lessons to model requests and records executions
so you can inspect how the agent used them.

## Configure CodeMie

Set these environment variables in your CodeMie deployment:

```bash
OBSERVABILITY_PROVIDER=sovara
SOVARA_SERVER_URL=https://app.sovara-labs.com
SOVARA_API_KEY=<organization-api-key>
```

Use `https://app.sovara-labs.com` for Sovara's hosted service, or your organization's
Sovara URL for an on-premises deployment. Supply an organization API key through
your deployment's secret configuration, then restart or redeploy CodeMie and its
workflow workers. CodeMie uses one observability provider at a time.

## Try your first lesson

1. Run a conversation in CodeMie, then open Sovara and select the matching project.
2. Open **Lessons**, choose **New proposal for changes**, then **New lesson**.
   Try this sample company convention:

   | Field | Example |
   | --- | --- |
   | Title | Priority-one incident updates |
   | When to use | Drafting a status update for a priority-one incident. |
   | Content | At Northstar, a priority-one incident is called a Red Alert. Every update must include customer impact, the incident owner and the time of the next update. |

3. Choose **Save changes**, then **Apply to production**.
4. Start a fresh conversation in the same CodeMie project and ask:
   “Draft a priority-one incident update for checkout failures. Maya owns the
   incident; the next update is at 14:30.”
5. Check whether the response uses **Red Alert** and includes the required fields.
   Open the trace in Sovara to inspect the lesson included in the model input.

The agent can use that company convention even though you did not include it in
your prompt. Add your own domain knowledge using the same flow. See
[creating and managing lessons](https://docs.sovara-labs.com/sovaradb/creating-managing-lessons).

## Recording coverage

Sovara records conversations, workflow model calls and tools executed through
LangChain, including agent-invoked MCP tools. Direct workflow tool nodes are not
recorded. See [Sovara traces](https://docs.sovara-labs.com/observability/traces)
and the [LangChain/LangGraph integration](https://docs.sovara-labs.com/integrations/langchain).
