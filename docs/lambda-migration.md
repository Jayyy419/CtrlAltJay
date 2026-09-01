# Elastic Beanstalk → Lambda migration

Moves the site off the `ctrlaltjay-prod` EB environment onto Lambda behind
CloudFront. Targets the $13.33/mo that environment costs:

| Line item | Was | After |
|---|---|---|
| EC2 t3.micro (`APS1-BoxUsage:t3.micro`) | $9.14 | $0 |
| Public IPv4 (`PublicIPv4:InUseAddress`, billed under VPC) | $3.47 | $0 |
| EBS gp3 8GB (`APS1-EBS:VolumeUsage.gp3`) | $0.72 | $0 |
| Secrets Manager (mail password) | $0.40 | $0 — moved to SSM SecureString |
| Lambda + CloudFront + S3 | — | ~$0 at portfolio traffic (free tiers) |

## Architecture

```
ctrlaltjay.dev (Route53 A/AAAA alias)
        ↓
CloudFront  ── /static/*  → S3 (OAC)      23MB of images/fonts, cached at edge
            └─ /*         → Lambda Function URL (OAC, SigV4)
                                ↓
                           Flask via apig-wsgi
                                ↓
                    DynamoDB ×3 · SSM · S3 · SES/SMTP · Anthropic
```

`/static/*` never reaches Lambda, so the images don't cost invocations.

## What changed in the app

- **Uploads go to S3.** Lambda's filesystem is read-only apart from an
  ephemeral `/tmp`, so `save_uploaded_image()` now writes to a scratch file,
  lets Pillow optimise it, uploads to `s3://<bucket>/static/uploads/`, and
  returns `/static/uploads/<name>`. With `STATIC_S3_BUCKET` unset it still
  uses local disk, so local dev is unchanged.
- **`ensure_upload_dir()` is skipped on Lambda.** It ran `mkdir()` on a
  `before_request` hook; on a read-only filesystem that raises on the first
  request and 500s *every* route, not just uploads.
- **Secrets come from SSM.** `_resolve_secret()` now prefers SSM Parameter
  Store, falls back to Secrets Manager, then to a plain env var. All four
  secrets resolve once at import (cold start), not per request.

## Outcome

Done. `ctrlaltjay.dev` is served by CloudFront in front of Lambda; the
Elastic Beanstalk environment is terminated, its CloudFormation stacks are
gone, and the Elastic IP is **released** — `describe-addresses` returns an
empty list, so the account holds no Elastic IP at all. That last point is
the one that matters for the bill: an unattached address is billed *more*
than an attached one, so disassociating without releasing would have made
the spend worse.

Two things behaved differently from the plan and are worth carrying
forward:

- **CloudFront OAC cannot sign a request body.** Lambda function URLs
  reject `UNSIGNED-PAYLOAD`, so under `AuthType: AWS_IAM` every POST fails
  with a SigV4 mismatch while every GET succeeds. The function URL is
  therefore `AuthType: NONE`, with CloudFront injecting `x-origin-verify`
  and the app rejecting anything without it. Nothing about the OAC could
  have been configured to make POST work.
- **A GET-only test suite cannot see that.** The verification passed and
  the site was broken for every form on it. `verify-lambda.yml` now sends a
  POST and distinguishes "never arrived" from "arrived without the header"
  from "works".

Still outstanding, both needing access this automation does not have:

- `CtrlAltJay-HighCPU` still exists — the deploy role lacks
  `cloudwatch:DeleteAlarms`. It watches an instance that no longer exists,
  so it will sit in `INSUFFICIENT_DATA` forever.
- SES will not deliver until `no-reply@ctrlaltjay.dev` is a verified
  identity, and while the account is in the SES sandbox the recipient must
  be verified too.

## Runbook

Nothing here is destructive until step 6. EB keeps serving live traffic
through step 4.

### 1. Populate SSM

The old EB environment held `ANTHROPIC_API_KEY`, `SECRET_KEY` and
`ADMIN_PASSCODE` as **plaintext environment variables**, readable by anyone
with `elasticbeanstalk:DescribeConfigurationSettings`. Treat all three as
disclosed: rotate them now rather than copying the existing values across.

```bash
REGION=ap-southeast-1

# Mail password — copy the existing value out of Secrets Manager
MAIL_PW=$(aws secretsmanager get-secret-value \
  --secret-id ctrlaltjay/mail-password \
  --region $REGION --query SecretString --output text)

aws ssm put-parameter --region $REGION --type SecureString \
  --name /ctrlaltjay/mail-password --value "$MAIL_PW"

# Rotate these rather than reusing the exposed values.
aws ssm put-parameter --region $REGION --type SecureString \
  --name /ctrlaltjay/flask-secret-key --value "$(openssl rand -base64 48)"

aws ssm put-parameter --region $REGION --type SecureString \
  --name /ctrlaltjay/admin-passcode --value '<new passcode>'

# Issue a fresh key in the Anthropic console and revoke the old one.
aws ssm put-parameter --region $REGION --type SecureString \
  --name /ctrlaltjay/anthropic-api-key --value '<new key>'
```

Rotating `flask-secret-key` invalidates existing admin sessions — expected,
just log in again.

### 2. Certificate

CloudFront reads certificates **only from us-east-1**, regardless of where
the rest of the stack lives.

```bash
aws acm request-certificate --region us-east-1 \
  --domain-name ctrlaltjay.dev --validation-method DNS
```

Add the CNAME it returns to zone `Z096666535JC4AOH22XFD` and wait for
`ISSUED`.

### 3. Deploy the stack (DNS untouched)

```bash
sam build --use-container
sam deploy --stack-name ctrlaltjay-app --region ap-southeast-1 \
  --capabilities CAPABILITY_IAM --resolve-s3 \
  --parameter-overrides AcmCertificateArn=<us-east-1 arn> ManageDns=false \
  --tags Project=CtrlAltJay Environment=Production

aws s3 sync static/ "s3://$(aws cloudformation describe-stacks \
  --stack-name ctrlaltjay-app \
  --query "Stacks[0].Outputs[?OutputKey=='StaticBucketName'].OutputValue" \
  --output text)/static/" --exclude "uploads/*"
```

`--use-container` matters: dependencies must resolve against the real Lambda
runtime image, not whatever happens to match the machine running the build.
Pillow is the one that bites — it is pinned to 12.2.0 because 12.3.0 ships no
cp311 x86_64 manylinux wheel, so pip falls back to the sdist and tries to
compile it in a build container with no toolchain. (EB's build image *does*
have a compiler, which is why 12.3.0 worked there and hid the problem.)

The function is x86_64, matching the CI runner, so this builds natively. It
was briefly arm64 — ~20% cheaper per GB-second — but that forces the build
container to run under QEMU on an x86_64 runner, which took >13 minutes
without finishing. At this traffic level the function sits inside the Lambda
free tier, so the saving is 20% of approximately nothing.

### 4. Verify on the CloudFront domain

Use the `CloudFrontDomain` output — EB is still live on the real domain.

- [ ] `/` renders
- [ ] `/static/...` image loads (served from S3, not Lambda)
- [ ] `/api/public-data` returns JSON
- [ ] Admin login works → confirms `/ctrlaltjay/admin-passcode` + rotated `SECRET_KEY`
- [ ] Contact form sends → **confirms the SSM mail password path** (gate for step 7)
- [ ] Chat/semantic search responds → confirms the rotated Anthropic key
- [ ] Admin image upload succeeds and the image renders → confirms S3 uploads

### 5. Cut DNS

`ctrlaltjay.dev` is currently an **A record to `47.128.182.192`**, not an
alias. Redeploying with `ManageDns=true` replaces it with A/AAAA aliases to
the distribution. In CI this is the `manage_dns` input on the deploy
workflow; it defaults to `false`, so a routine deploy cannot move DNS.

```bash
sam deploy --stack-name ctrlaltjay-app --region ap-southeast-1 \
  --capabilities CAPABILITY_IAM --resolve-s3 \
  --parameter-overrides AcmCertificateArn=<arn> ManageDns=true
```

**This is not how the cutover was actually done — see below.** The
CloudFormation path needs Route53 permissions the deploy role does not have.
The scoped `ctrlaltjay-sam-deploy` policy was written when the first deploy
ran with `ManageDns=false`, so it had none, and the cutover failed with
`route53:GetHostedZone ... is not authorized`. That is a safe failure —
CloudFormation checks the permission before writing any record, so
`ApexRecords` went `CREATE_FAILED` and rolled back with DNS untouched — but
it is a wasted build and deploy. To use this path, attach:

```json
{
  "Effect": "Allow",
  "Action": [
    "route53:GetHostedZone",
    "route53:ListResourceRecordSets",
    "route53:ChangeResourceRecordSets"
  ],
  "Resource": "arn:aws:route53:::hostedzone/Z096666535JC4AOH22XFD"
}
```

plus `route53:GetChange` on `arn:aws:route53:::change/*` — CloudFormation
polls that to wait for the change to propagate, and it does not accept a
zone-scoped resource.

#### What was actually done: `cutover-dns.yml`

Rather than granting the above, the apex was moved with a direct Route53
API call, which needs only `ChangeResourceRecordSets` — a permission the
role already had. Run the `Cut ctrlaltjay.dev over to CloudFront` workflow
with `confirm: cutover`; it records the apex as it stands, UPSERTs A and
AAAA aliases, waits for the old 300s TTL to drain, and asserts the live
domain serves. To undo, run it again with `confirm: cutover` **and**
`rollback: yes`.

**Consequence: the apex is managed by that workflow, not by the stack, so
`ManageDns` must stay `false`.** Deploying with `manage_dns=true` now would
fail — CloudFormation would try to *create* records that already exist.
Delete the apex records by hand first if you ever want the stack to own them.

This is the better arrangement regardless: the hosted zone and the apex
record both predate the stack, and records owned by the stack would be
destroyed along with it. It also means **tearing the stack down cannot take
DNS with it.**

The cutover uses UPSERT, so the existing record is replaced in place and the
apex is never without a record — the convergence log showed an unbroken run
of `200`s, transitioning from `HTTP/1.1` (EB) to `HTTP/2 ... cloudfront=True`.

**Leave EB running** until everything below is verified — it is the rollback.

### 6. Tear down EB

Only after the real domain has served from CloudFront for a while.

```bash
aws elasticbeanstalk terminate-environment \
  --environment-id e-z6u7ybmnth --region ap-southeast-1
```

Terminating the environment removes `awseb-e-z6u7ybmnth-stack`, the t3.micro
(`i-010768674237ded28`), the security group and the gp3 volume.

The Elastic IP is the one that needs checking by hand — **disassociating it
does not stop the $3.47; only releasing it does**, and an unattached EIP is
billed at the same rate as an attached one:

```bash
aws ec2 release-address --region ap-southeast-1 \
  --allocation-id eipalloc-0153e2c93a05d19ec

# Must return an empty list:
aws ec2 describe-addresses --region ap-southeast-1 \
  --allocation-ids eipalloc-0153e2c93a05d19ec 2>&1 | head
```

Then the alarm that now watches a dead instance:

```bash
aws cloudwatch delete-alarms --region ap-southeast-1 \
  --alarm-names CtrlAltJay-HighCPU
```

Keep: the three DynamoDB tables, the Route53 zone, and
`github-actions-ctrlaltjay-deploy`. The two `aws-elasticbeanstalk-*` roles
become unused and can go once nothing else references them.

### 7. Retire the Secrets Manager entry

Only once step 4 confirmed the contact form sends via SSM. Recovery window,
never `--force-delete-without-recovery`:

```bash
aws secretsmanager delete-secret --region ap-southeast-1 \
  --secret-id ctrlaltjay/mail-password \
  --recovery-window-in-days 30
```

### 8. Confirm the spend actually stopped

Give it ~24h for Cost Explorer to settle, then check these three usage types
have gone to zero:

- `APS1-BoxUsage:t3.micro`
- `PublicIPv4:InUseAddress`
- `APS1-EBS:VolumeUsage.gp3`

The `TotalMonthlyBillingOver25` alarm (us-east-1) should stop firing on its
own once this lands.

## Rollback

Before step 6, rollback is a DNS change: point the `ctrlaltjay.dev` A record
back at `47.128.182.192`. EB is untouched until then. After step 6 the
environment is gone and rollback means redeploying it from `deploy.yml`,
which is why the EB workflow is kept until teardown is done.

## Known trade-offs

- **Cold starts.** Flask + Pillow + anthropic is a chunky import; first
  request after idle runs ~1–3s. Fine for a portfolio. If it grates, the fix
  is a provisioned-concurrency of 1 — but that costs ~$4/mo and would eat a
  third of the saving, so it is deliberately not configured.
- **`/static/uploads/` is excluded from `aws s3 sync --delete`.** Uploads are
  written at runtime and exist only in S3; syncing them from the repo would
  delete every one.
