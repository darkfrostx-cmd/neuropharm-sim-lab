# Custom GPT Action Setup Guide

This guide walks you through, step by step, how to describe an HTTP API so a Custom GPT can call it through Actions. The explanations assume no prior experience with YAML or OpenAI Actions. By the end you will have a working `actions.yaml` file that you can upload in the Custom GPT builder.

## 1. Collect the details about the API you want to call

Before you touch YAML, gather the information you will need:

1. **The base URL**: The root address of your service, for example `https://api.example.com`.
2. **Authentication method**: Whether the API expects an API key in a header, OAuth, or something else. For a simple shared API key, note the header name (commonly `Authorization`).
3. **Endpoints you want to expose**: Write down the HTTP method (`GET`, `POST`, and so on), the endpoint path (such as `/v1/analyze`), and the purpose of each endpoint.
4. **Request and response formats**: Note what JSON fields the endpoint expects and what it returns. If the API already ships an OpenAPI schema, you can reuse parts of it.

Having this checklist prevents bottlenecks later because you will not need to pause to look up details mid-way through the configuration.

## 2. Create the `actions.yaml` skeleton

Open a blank text file and paste the skeleton below. It contains every top-level field the Custom GPT builder expects.

```yaml
schema_version: "v1"
name_for_human: "Example Data Assistant"
name_for_model: "example_data_assistant"
description_for_human: "Retrieves and analyzes domain-specific data."
description_for_model: "Use this when you need fresh domain data or to run complex analytics."
api:
  type: openapi
  url: https://your-domain.com/openapi.yaml
  has_user_authentication: false
authorization:
  type: bearer
actions:
  - name: fetch_insights
    description: "Get the latest insights from the analytics service."
    params:
      type: object
      properties:
        topic:
          type: string
          description: "Subject you want insights about."
      required:
        - topic
```

### How this skeleton works

- `schema_version` must be exactly `"v1"` today.
- `name_for_human` and `description_for_human` show up in the builder UI. Make them clear for teammates.
- `name_for_model` and `description_for_model` tell the GPT when to call your action.
- The `api` block points to an OpenAPI document. You can host it yourself or inline it directly under `api: { type: "openapi", ... }` if you prefer. Inline specs avoid extra network hops.
- The `authorization` block declares how the GPT should authenticate. `bearer` tells the builder to let you paste an API key.
- The `actions` list maps each callable function to a request. In the example we expose one action called `fetch_insights`.

## 3. Describe each action in plain language

Custom GPTs plan their tool usage based on the natural-language descriptions. Invest time here:

1. Start each description with a verb that matches the endpoint ("Get", "Create", "Summarize").
2. Mention the most important parameters and constraints (for example, "Requires a `topic` string up to 100 characters").
3. If an endpoint is resource-intensive, say so ("Only call once per request to avoid rate limits").

Clear descriptions give the model the "mechanistic depth" you want: it understands when the tool is relevant and what arguments it must supply.

## 4. Map parameters to the API specification

Inside each action, you must define the JSON schema for the request body or query parameters:

```yaml
    params:
      type: object
      properties:
        topic:
          type: string
          description: "Subject area, e.g., 'opioid pharmacodynamics'."
        detail_level:
          type: string
          enum: ["summary", "technical"]
          description: "Choose 'summary' for lay explanations or 'technical' for detailed outputs."
      required:
        - topic
```

Tips:

- Use `enum` for constrained choices. The GPT respects the list and you prevent invalid calls.
- Document units and ranges ("time_window_days must be between 1 and 30").
- Mark only truly essential fields as `required`. Optional parameters can still be supplied when helpful.

## 5. Provide or host the OpenAPI document

The builder fetches the OpenAPI document at the URL you supply. You have two options:

1. **Inline spec**: Replace the `url:` field with an `inline_spec:` block.

   ```yaml
   api:
     type: openapi
     has_user_authentication: false
     spec:
       openapi: 3.1.0
       info:
         title: Example Data API
         version: "1.0.0"
       servers:
         - url: https://api.example.com
       paths:
         /v1/insights:
           post:
             summary: Fetch insights
             operationId: fetchInsights
             requestBody:
               required: true
               content:
                 application/json:
                   schema:
                     $ref: "#/components/schemas/FetchInsightsRequest"
             responses:
               "200":
                 description: Successful response
                 content:
                   application/json:
                     schema:
                       $ref: "#/components/schemas/FetchInsightsResponse"
       components:
         schemas:
           FetchInsightsRequest:
             type: object
             properties:
               topic:
                 type: string
               detail_level:
                 type: string
                 enum: ["summary", "technical"]
             required:
               - topic
           FetchInsightsResponse:
             type: object
             properties:
               report:
                 type: string
   ```

2. **Hosted spec**: Upload a `openapi.yaml` file to a web server or object storage bucket (for example, GitHub Pages, Amazon S3, or Cloudflare R2) and set the `url:` field to that location.

The inline approach makes the `actions.yaml` heavier but removes any chance of the GPT being blocked from fetching the spec (no CORS or authentication hurdles).

## 6. Set authentication in the Custom GPT builder

In the builder, go to **Actions → Authentication** and choose the method you declared in the YAML. For a bearer token:

1. Select **API Key**.
2. Enter the header name (commonly `Authorization`).
3. Paste your key (for example, `Bearer sk_example123`).

The builder stores the secret securely and sends it with every request. Avoid hard-coding keys in the YAML file you check into source control.

## 7. Upload and test the action

1. Open the Custom GPT builder.
2. Enable **Actions**, then choose **Upload a file** and select your `actions.yaml`.
3. The builder validates the YAML. Fix any red errors it reports.
4. Open the **Test** tab, prompt the GPT with a scenario, and watch the request log. Confirm that it calls the endpoint with the parameters you expect.
5. Adjust descriptions or parameter hints if the model hesitates or supplies the wrong fields.

## 8. Iterate for more depth

To give the GPT more mechanistic power:

- **Expose granular endpoints**: Instead of one mega action, break the workflow into smaller steps (for example, `fetch_raw_data`, `calculate_dose_response`, `summarize_findings`). The model can chain them.
- **Add validation schemas**: Enrich schemas with `minLength`, `maximum`, and pattern constraints. These guardrails prevent malformed requests.
- **Document edge cases**: In the description, mention when the action should *not* be used ("Only call after `fetch_raw_data` succeeds").
- **Log and refine**: Review the call logs and refine descriptions when you see the model make mistakes.

## 9. Keep the YAML in version control

Store `actions.yaml` (and any referenced OpenAPI files) in your repository so teammates can review changes. Commit messages should explain why you adjusted descriptions or parameters—clarity speeds up code review and reduces bottlenecks.

---

Following these steps ensures your Custom GPT can reliably call your API without getting stuck on missing details. Precise schemas and clear language are the keys to unlocking deeper, more consistent behavior.
