# Hosted demonstration

Application: **https://pulsecontinuum.vercel.app**. Sign in using the private credentials supplied separately. The administrator can switch between both profiles; care credentials provide clinical access only.

## Deployment boundary

- **Vercel:** Next.js frontend, sign-in/session middleware and private API proxy. Root directory: `frontend`; Node 22; server region `iad1`. GitHub pushes deploy through the linked Vercel project.
- **AWS Lambda:** Python 3.13, 1 GB memory, 60-second timeout, Mangum ASGI adapter. Every HTTP request requires the private backend service token. No AWS access keys are copied to Vercel; Lambda uses its IAM execution role.
- **DynamoDB:** independent synthetic hosted episodes, an atomic daily model allowance, a workflow lease and durable telemetry. The workflow lease serializes mutations across execution environments and expires after 75 seconds if interrupted.
- **S3:** private discharge, image, audio and audit assets. Local Lambda disk is a cache. Retrieval of an audit also checks current episode state, so a reset episode cannot expose a stale audit through its download route.
- **EventBridge:** a separate hosted event bus avoids mixing hosted judge events with the local integration stack.

The Lambda role permits the required storage, event and Nova Pro inference operations. It has no outbound SES or phone-messaging permission. The previous approved SES integration proof is preserved in the repository; the hosted demo itself sends no additional emails.

## Serverless behavior

The frontend polls bounded endpoints instead of maintaining SSE or WebSocket connections through Vercel/Lambda. The UI labels this as telemetry polling. Resident inbound consumers and in-process delivery timers are not relied on in hosted mode; phone senders remain disconnected. Explicit continuity previews still execute the workflow and publish events.

Hosted uploads must total less than 3 MB per request. Audit/media artifacts persist across cold starts. Telemetry persists workflow execution records, excludes binary bodies, bounds oversized payloads and expires after seven days. Polling reads are not persisted again, avoiding an idle telemetry write loop.

Ten Bedrock inference attempts are allowed per UTC day. Attempts are counted atomically before model invocation, including failures. Resetting an episode does not reset the allowance. This helps constrain demo use; it is not an AWS billing hard cap. No provisioned compute or paid Vercel upgrade was added.

## Rebuild and deploy

1. Install Linux Python wheels into `tmp/lambda-package` using `backend/requirements-lambda.txt`, Python 3.13, and the `manylinux_2_28_x86_64` / `manylinux2014_x86_64` platform tags.
2. Run `python tools/build_lambda.py`.
3. Review `infra/hosted_stack.py`; run `python tools/deploy_hosted_backend.py` only for the confirmed deployment account. The script reuses retained storage from the initial quota-related rollback and creates/updates `PulseContinuumWebBackend`.
4. Authenticate the official Vercel CLI and link the correct project. `tools/configure_vercel.py` writes the private settings through CLI stdin as secrets, without printing their values.
5. Push the reviewed frontend changes to the linked GitHub repository and verify the resulting Vercel deployment.

Local manifests, secret environment files, access instructions and deployment archives are excluded from source control. The deployment scripts are specific to the project owner's confirmed account/workspace; adapt those identifiers for another account.

## Verification evidence

`submission/hosted-backend-verification.json` records the synthetic discharge upload, one real validated Bedrock image analysis, EventBridge action, generated PDF/media retrieval, durable telemetry and reset. It confirms outbound `NOT_SENT`; it does not claim email or handset delivery. The backend regression suite includes file-cache-loss recovery and fail-closed model allowance tests.
