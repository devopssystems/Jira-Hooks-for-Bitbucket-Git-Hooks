# Jira Hooks for Bitbucket Cloud (Git Hooks)
Python library and ready-to-use git hooks for **Jira Hooks for Bitbucket Cloud**.

Jira Hooks for Bitbucket Cloud is built by [DevOpsSystems](https://www.devopssystems.de/). If you want to learn more about the product and the vendor, see [devopssystems.de](https://www.devopssystems.de/) and the [Atlassian Marketplace vendor page](https://marketplace.atlassian.com/vendors/1211202/devopssystems-gmbh).

Jira Hooks for Bitbucket Cloud helps teams enforce commit and push rules in Bitbucket Cloud and Jira-centered development workflows. It validates commit messages, branch-related processes, and repository rules against centrally managed [Process Guardian](https://help.devopssystems.de/jhfb) checks so teams can improve traceability, compliance, audit trail visibility, and delivery quality directly in their day-to-day Git workflow.

This `local-hooks` package brings those validations to the developer machine. If you want to validate commits locally before `git commit` or `git push` succeeds, this package gives you ready-to-use hook scripts and a simple way to call the validation endpoint yourself.

It is especially useful for teams that use Jira and Bitbucket Cloud together and want earlier feedback on commit conventions, Jira issue references, repository-specific engineering standards, compliance requirements, and audit trail documentation before changes ever reach the remote repository.

<br />
<p align="center">
  <strong>Commit validation</strong><br />
  <img
    src="image/jhfb-commit.gif"
    alt="Jira Hooks for Bitbucket local commit-msg validation demo"
    width="740"
  />
</p>
<br />
<p align="center">
  <strong>Push validation</strong><br />
  <img
    src="image/jhfb-push.gif"
    alt="Jira Hooks for Bitbucket local pre-push validation demo"
    width="740"
  />
</p>
<br />

> [!NOTE]
> Collaboration is welcome. Feedback, bug reports, ideas, and contributions are encouraged.

---

## Requirements

- Python ≥ 3.9
- [`requests`](https://pypi.org/project/requests/) ≥ 2.28

---

## What you can use

- `commit-msg`
  Checks the commit message before Git creates the commit.
- `pre-push`
  Checks all commits that are about to be pushed.
- your own client
  If you do not want to use the provided hooks, you can call the endpoint yourself.

---

## Installation

Change into your Git repository first, then define the hook repository URL once and reuse it for the next steps.

```bash
cd /path/to/your-repository
export JHFB_HOOKS_REPO_URL="https://bitbucket.org/devopssystems-public/jira-hooks-for-bitbucket-githooks.git"
# Alternative:
# export JHFB_HOOKS_REPO_URL="https://github.com/devopssystems/Jira-Hooks-for-Bitbucket-Git-Hooks.git"
```

Then install the Python package:

```bash
pip install "git+${JHFB_HOOKS_REPO_URL}"
```

After that, choose the hook timing you want:

- `commit-msg`
  if you want to validate directly while creating a commit.
- `pre-push`
  if you want to validate right before pushing.
- both
  if you want checks at both points in time.

It is not required to use both `commit-msg` and `pre-push`. Which hook you install depends on the desired test timepoint and is up to the user.

If you want both Git hook wrappers, install them like this:

```bash

curl -L "${JHFB_HOOKS_REPO_URL%*.git}/raw/main/hooks/pre-push" -o .git/hooks/pre-push
curl -L "${JHFB_HOOKS_REPO_URL%*.git}/raw/main/hooks/commit-msg" -o .git/hooks/commit-msg
chmod +x .git/hooks/pre-push .git/hooks/commit-msg
```

The Python package provides the `jhfb_hooks` module. The `hooks/pre-push` and `hooks/commit-msg` files in the Git repository are the ready-to-use Git hook wrappers that call that module.

---

## Configuration

The hooks read their configuration from environment variables or from a `.git/hooks/commit-check.env` file.

Environment variables win over the file. That gives you a simple local default and still lets you override values in a shell session or CI, or maintain a personal configuration for those values.

### Required keys

| Variable | Description |
|---|---|
| `JHFB_ENDPOINT` | Web-trigger URL — Jira → *Jira Hooks for Bitbucket Cloud* → Settings → **Web-trigger URL** |
| `JHFB_SECRET` | HMAC secret — Jira → *Jira Hooks for Bitbucket Cloud* → Settings → **Configure token** |


> Both values can be configured in Bitbucket under: `Repository/Workspace Settings -> Jira Hooks for Bitbucket -> Process Guardian`.

### Optional keys

| Variable | Default | Description |
|---|---|---|
| `JHFB_PRINT_SUMMARY` | `true` | Show the overall validation result plus system messages. If all output flags are `false`, the hook is effectively disabled. |
| `JHFB_PRINT_RULE_TITLE` | `true` | Show rule titles grouped by section. This is automatically enabled when `JHFB_PRINT_RULE_META=true` or `JHFB_PRINT_RULE_SUMMARY=true`. |
| `JHFB_PRINT_RULE_META` | `false` | Show `Error` / `Success` / `Hint` lines. Enabling this also enables rule titles. |
| `JHFB_PRINT_RULE_SUMMARY` | `false` | Show per-rule Branch/Commit summary messages. Enabling this also enables rule titles. |
| `JHFB_PRINT_RULE_DETAIL` | `true` | Show detailed fact messages below the summaries. |
| `JHFB_PRINT_CONDITIONS` | `false` | Show condition facts in a dedicated `Conditions` section in the terminal output. |
| `JHFB_SEVERITY_FILTER` | `SUCCESS` | Which message severities are shown. One of `ERROR`, `WARNING`, `INFO`, `SUCCESS`. |
| `JHFB_LOCALE` | `en-US` | BCP-47 locale for rule messages and local hook terminal output. Currently supports `en-US` and `de-DE` (aliases such as `en_us` and `de_de` are normalized). |
| `JHFB_RICH_OUTPUT` | `true` | Set to `false`, `0`, or `no` to disable rich terminal formatting. |

### Example `.git/hooks/commit-check.env`

Create this file next to your installed hook scripts:

```dotenv
JHFB_ENDPOINT="https://<your-forge-endpoint>?repoSlug=<your-repo-slug>"
JHFB_SECRET="<your-hmac-secret>"

# Optional
JHFB_PRINT_SUMMARY=true
JHFB_PRINT_RULE_TITLE=true
JHFB_PRINT_RULE_META=false
JHFB_PRINT_RULE_SUMMARY=false
JHFB_PRINT_RULE_DETAIL=true
JHFB_SEVERITY_FILTER=SUCCESS
JHFB_LOCALE=en-US
JHFB_PRINT_CONDITIONS=true
JHFB_RICH_OUTPUT=true
```

If the file does not exist and the required environment variables are not set, the hook prints a warning and exits with code `0`. An unconfigured hook does not block your work.

---

## Use it with Husky

If your team uses [Husky](https://typicode.github.io/husky/), you can keep the hooks in the repository and share them with the whole team.

Short setup:

```bash
pip install "git+${JHFB_HOOKS_REPO_URL}"
npm install --save-dev husky
npx husky init
mkdir -p .husky/jhfb
curl -L "${JHFB_HOOKS_REPO_URL%*.git}/raw/main/hooks/pre-push" -o .husky/jhfb/pre-push
curl -L "${JHFB_HOOKS_REPO_URL%*.git}/raw/main/hooks/commit-msg" -o .husky/jhfb/commit-msg
chmod +x .husky/jhfb/pre-push .husky/jhfb/commit-msg
npx husky add .husky/pre-push '.husky/jhfb/pre-push'
npx husky add .husky/commit-msg '.husky/jhfb/commit-msg "$1"'
```

In a Husky setup it is usually easiest to provide the configuration via environment variables such as `JHFB_ENDPOINT`, `JHFB_SECRET`, `JHFB_PRINT_SUMMARY`, `JHFB_PRINT_RULE_TITLE`, `JHFB_PRINT_RULE_META`, `JHFB_PRINT_RULE_SUMMARY`, `JHFB_PRINT_RULE_DETAIL`, `JHFB_PRINT_CONDITIONS`, `JHFB_SEVERITY_FILTER`, `JHFB_LOCALE`, and `JHFB_RICH_OUTPUT`. If you want to use a config file instead, place `commit-check.env` next to the downloaded scripts in `.husky/jhfb/`.

---

## Example output

```text
❌ Blocked by Process Guardian rules:
  ❌ [Issue Key Required]
    ❌ Commit does not contain any issue keys.

✅ Local commit check passed — 3 commits validated.
```

---

## Security hint

This endpoint is only meant for validation.

- It can validate a payload against configured rules.
- It cannot read repository or workspace settings.
- It cannot change settings.
- It cannot access or modify source code through this API.

Even the validation endpoint itself is protected by the HMAC token. That token is not user-specific. It is scoped to a repository or to a workspace, depending on how it was created.

---

## Do it by your own

If you do not want to use the provided hook scripts, you can call the endpoint directly. In that case you need two things:

- the correct JSON payload
- the matching `x-hub-signature-256` header

### Payload shape

The endpoint expects a JSON object with these fields:

- `branchName`
  Optional branch context. The hooks still send it by default, using an empty string if no branch is known.
- `triggerType`
  Required. Must be `COMMIT` or `PUSH`.
- `commits`
  Optional array of commit objects. It may be empty.
- `locale`
  Optional. Defaults to `en-US`.
- `repoSlug` or `repositoryUuid`
  Optional in the body, but useful if you do not already pass the repository in the JHFB_ENDPOINT query.

Validation semantics:

- branch without commits is valid input and is validated as a branch-only case
- commits without branch context are still sent with `branchName: ""`
- if neither branch nor commits are available, the endpoint still returns `200` and answers with `result: "IGNORE"`

Each commit object supports:

- `hash`
- `message`
- `authorDisplayName`
- `url`
  Optional.

### Example payload for `commit-msg`

```json
{
  "branchName": "feature/ABC-123-local-check",
  "triggerType": "COMMIT",
  "locale": "en-US",
  "commits": [
    {
      "hash": "0000000000000000000000000000000000000000",
      "message": "feat(ABC-123): add local validation",
      "authorDisplayName": "Jane Developer"
    }
  ]
}
```

### Example payload for `pre-push`

```json
{
  "branchName": "feature/ABC-123-local-check",
  "triggerType": "PUSH",
  "locale": "en-US",
  "commits": [
    {
      "hash": "f00ba41234abcd1234abcd1234abcd1234abcd12",
      "message": "feat(ABC-123): add local validation",
      "authorDisplayName": "Jane Developer"
    },
    {
      "hash": "0ddba41234abcd1234abcd1234abcd1234abcd34",
      "message": "test(ABC-123): add payload tests",
      "authorDisplayName": "Jane Developer"
    }
  ]
}
```

### Example with `curl`

The endpoint requires an HMAC-SHA256 signature in the `x-hub-signature-256` header. The signature must be calculated over the raw JSON body using your `JHFB_SECRET`.

```bash
BODY='{"branchName":"feature/ABC-123-local-check","triggerType":"PUSH","locale":"en-US","commits":[{"hash":"f00ba41234abcd1234abcd1234abcd1234abcd12","message":"feat(ABC-123): add local validation","authorDisplayName":"Jane Developer"}]}'
SIGNATURE="sha256=$(printf %s "$BODY" | openssl dgst -sha256 -hmac "$JHFB_SECRET" -hex | sed 's/^.* //')"

curl \
  -X POST \
  -H "Content-Type: application/json" \
  -H "x-hub-signature-256: $SIGNATURE" \
  --data "$BODY" \
  "$JHFB_ENDPOINT"
```

If your JHFB_ENDPOINT does not already contain `?repoSlug=...`, pass the repository either as a query parameter or in the JSON body via `repoSlug` or `repositoryUuid`.

### Result payload

The endpoint returns a translated validation result based on `TranslatedRuleValidationCollectionSchema`.

Top-level fields:


- `timestamp`
  Unix timestamp in milliseconds when the result was created.
- `result`
  Overall validation result, typically `PASS`, `WARNING`, `SKIP`, or `BLOCK`.
- `ruleValidations`
  Array of executed rule results.
- `errorValidations`
  Array of non-rule validation errors, for example request-level problems.

Each `ruleValidations` entry contains:

- `rule`
  The resolved rule configuration that was evaluated.
- `ruleStatus`
  Result of that individual rule.
- `conditionFacts`
  Translated condition facts with a ready-to-display `message`.
- `checkFacts`
  Translated check facts with a ready-to-display `message`.
- `issuesUnderReview`
  Optional map of issue keys that were part of the review context.
- `commitsUnderReview`
  Optional map of commit hashes that were part of the review context.

Each translated fact is the normal fact structure plus:

- `message`
  Final localized user-facing text for this fact.

### Fact error and result codes

Inside `conditionFacts` and `checkFacts`, the field `code` describes the semantic meaning of the fact. These codes are independent from the localized `message` text and are useful if you want to post-process the response programmatically.

The currently used fact codes are:

| Code | Meaning |
|---|---|
| `CHECKED` | Summary fact saying that a check or target was evaluated successfully or unsuccessfully at a higher level. |
| `FOUND` | Something expected was found. |
| `NOT_FOUND` | Something expected was not found. |
| `KEYS_PRESENT` | One or more issue keys were found in the validated content. |
| `NO_KEYS` | No issue keys were found where the rule expected them. |
| `VALID` | A single validated item is valid. |
| `INVALID` | A single validated item is invalid. |
| `ALL_VALID` | All validated items passed. |
| `NOT_ALL_VALID` | Not all validated items passed. |
| `ONE_VALID` | At least one item passed. |
| `NONE_VALID` | No validated items passed. |
| `ONE_ENOUGH` | One valid target was enough for the configured strategy, so the overall result can still pass. |
| `ONE_NOT_ENOUGH` | One valid target was not enough for the configured strategy. |
| `MATCH` | A pattern, condition, or query matched. |
| `NOT_MATCH` | A pattern, condition, or query did not match. |

To interpret a fact correctly, combine these fields:

- `code`
  The semantic event, for example `NO_KEYS` or `MATCH`.
- `status`
  The severity or outcome, for example `ERROR`, `WARNING`, `INFO`, `SUCCESS`, `SKIP`, or `NOT_SKIP`.
- `source`
  Which subsystem produced the fact, for example e.g. `ISSUE_KEY` or `JQL`.
- `group`
  Whether the fact is a summary (`MAIN`), detail (`DETAIL`), or target-strategy fact (`TARGET`).

### Error payload

On request-level errors the endpoint returns a smaller error response instead of a translated validation result:

```json
{
  "error": "Unauthorized",
  "errorCode": "HMAC_SIGNATURE_INVALID"
}
```

### HTTP status codes

The local-check endpoint currently uses these HTTP status codes:

| HTTP code | Meaning |
|---|---|
| `200` | The request was valid and a translated validation result was returned. The overall validation outcome is then in the JSON field `result`, for example `PASS`, `BLOCK`, or `IGNORE`. |
| `400` | The request itself was invalid, for example malformed JSON, an invalid payload shape, a missing repository identifier, or an unsupported trigger type. |
| `401` | Authentication failed, for example because the HMAC header was missing, no secret was configured, or the signature was invalid. |
| `404` | The referenced repository could not be resolved. |
| `500` | An internal server-side error occurred. |

The `errorCode` values currently used by the local-check endpoint are:

| Error code | Meaning |
|---|---|
| `WORKSPACE_CONTEXT_MISSING` | The Forge addon context did not contain a workspace UUID, so the request could not be resolved. |
| `JSON_PARSE_ERROR` | The request body was not valid JSON. |
| `PAYLOAD_VALIDATION_ERROR` | The JSON body was syntactically valid, but it did not match the expected payload schema. |
| `REPOSITORY_NOT_FOUND` | The repository could not be resolved from `repositoryUuid` or `repoSlug`. |
| `REPOSITORY_ID_MISSING` | Neither `repositoryUuid` nor `repoSlug` was provided in query parameters or payload. |
| `UNSUPPORTED_TRIGGER_TYPE` | The payload used a trigger type that is not allowed for local checks, for example `PULL_REQUEST`. |
| `HMAC_AUTH_MISSING` | The `x-hub-signature-256` header was missing. |
| `HMAC_SECRET_NOT_CONFIGURED` | No validation secret/token was configured for the resolved workspace or repository scope. |
| `HMAC_SIGNATURE_INVALID` | The provided HMAC signature did not match the raw request body. |
| `INTERNAL_ERROR` | An unexpected server-side error occurred. |

There are also feature-disabled codes in the backend enum:

| Error code | Meaning |
|---|---|
| `FEATURE_DISABLED_GLOBAL` | Reserved for a global/workspace-level disabled state. |
| `FEATURE_DISABLED_REPO` | Reserved for a repository-level disabled state. |

At the moment those two reserved codes are not emitted by the current `LocalCheckEndpoint` implementation.

### Example result payload

```json
{
  "timestamp": 1711111111111,
  "result": "BLOCK",
  "ruleValidations": [
    {
      "ruleStatus": "BLOCK",
      "rule": {
        "id": -1,
        "title": "Issue Key Required",
        "error": "Commit message must include an issue key.",
        "hint": "Add a Jira issue key such as ABC-123 to the commit message.",
        "scope": "REPOSITORY",
        "showRule": true,
        "triggers": ["COMMIT"],
        "variants": ["KEY"],
        "target": ["COMMIT"],
        "strategy": "all",
        "checks": {
          "issue": {
            "key": {
              "enabled": true,
              "strategy": "all"
            }
          }
        }
      },
      "conditionFacts": [],
      "checkFacts": [
        {
          "message": "Commit does not contain any issue keys.",
          "status": "ERROR",
          "source": "ISSUE_KEY",
          "qualifier": "DETAIL",
          "group": "COMMIT",
          "code": "NO_KEYS",
          "contexts": ["COMMIT"]
        }
      ]
    }
  ],
  "errorValidations": []
}
```
